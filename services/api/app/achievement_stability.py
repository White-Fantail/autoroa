import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from . import achievements as achievement_module
from . import profile_achievements as profile_module
from . import regional_achievements as regional_module
from .achievement_operations import TierReplaceInput, _contributor_count, _rarity
from .achievements import (
    AchievementDefinition,
    AchievementInput,
    AchievementMetric,
    AchievementPatch,
    AchievementTier,
    UserAchievementAward,
    UserAchievementState,
    _definition_payload,
    _progress,
    _criteria_for_tier,
    _metric_values,
    evaluate_criteria,
)
from .auth import Principal, admin_principal
from .contribution_rewards import PointTransaction
from .db import SessionLocal, get_db
from .models import Profile, Station


class AchievementCriteriaError(ValueError):
    pass


stability_router = APIRouter(prefix="/api/v1")
_INSTALLED = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def validate_criteria(criteria: dict[str, Any] | None, path: str = "criteria") -> None:
    if not isinstance(criteria, dict) or not criteria:
        raise AchievementCriteriaError(f"{path} must be a non-empty object")
    structural = [key for key in ("all", "any", "not", "metric", "event") if key in criteria]
    if len(structural) != 1:
        raise AchievementCriteriaError(f"{path} must contain exactly one of all, any, not, metric, or event")
    key = structural[0]
    if key in {"all", "any"}:
        items = criteria[key]
        if not isinstance(items, list) or not items:
            raise AchievementCriteriaError(f"{path}.{key} must be a non-empty list")
        for index, item in enumerate(items):
            validate_criteria(item, f"{path}.{key}[{index}]")
        return
    if key == "not":
        validate_criteria(criteria[key], f"{path}.not")
        return
    field = criteria[key]
    if not isinstance(field, str) or not field.strip():
        raise AchievementCriteriaError(f"{path}.{key} must be a non-empty string")
    operator = criteria.get("op", "gte")
    if operator not in achievement_module.SUPPORTED_OPERATORS:
        raise AchievementCriteriaError(f"{path}.op '{operator}' is not supported")
    if "value" not in criteria:
        raise AchievementCriteriaError(f"{path}.value is required")
    expected = criteria["value"]
    if operator == "between" and (not isinstance(expected, (list, tuple)) or len(expected) != 2):
        raise AchievementCriteriaError(f"{path}.value must contain exactly two values for between")
    if operator in {"in", "not_in"} and not isinstance(expected, (list, tuple, set)):
        raise AchievementCriteriaError(f"{path}.value must be a list for {operator}")


@event.listens_for(UserAchievementState, "init", propagate=True)
def _initialise_achievement_state(target, args, kwargs):
    if kwargs.get("earned_count") is None:
        target.earned_count = 0
    if kwargs.get("progress") is None:
        target.progress = {}


@event.listens_for(AchievementDefinition, "before_insert", propagate=True)
@event.listens_for(AchievementDefinition, "before_update", propagate=True)
def _validate_definition_before_write(mapper, connection, target):
    validate_criteria(target.criteria)


@event.listens_for(AchievementTier, "before_insert", propagate=True)
@event.listens_for(AchievementTier, "before_update", propagate=True)
def _validate_tier_before_write(mapper, connection, target):
    if target.criteria:
        validate_criteria(target.criteria, "tier.criteria")


def _tier_target(db: Session, definition: AchievementDefinition, user_id: uuid.UUID):
    metrics = _metric_values(db, user_id)
    tiers = list(
        db.scalars(
            select(AchievementTier)
            .where(AchievementTier.achievement_id == definition.id)
            .order_by(AchievementTier.sort_order)
        )
    )
    eligible = [tier for tier in tiers if evaluate_criteria(_criteria_for_tier(definition, tier), metrics=metrics)]
    return metrics, tiers, eligible[-1] if eligible else None


def reconcile_definition_states(db: Session, achievement_id: uuid.UUID) -> int:
    definition = db.get(AchievementDefinition, achievement_id)
    if definition is None:
        return 0
    user_ids = set(db.scalars(select(AchievementMetric.user_id).distinct()))
    user_ids.update(db.scalars(select(UserAchievementState.user_id).where(UserAchievementState.achievement_id == achievement_id)))
    changed = 0
    for user_id in user_ids:
        metrics = _metric_values(db, user_id)
        if definition.achievement_type == "TIERED":
            tiers = list(
                db.scalars(
                    select(AchievementTier)
                    .where(AchievementTier.achievement_id == definition.id)
                    .order_by(AchievementTier.sort_order)
                )
            )
            eligible = [tier for tier in tiers if evaluate_criteria(_criteria_for_tier(definition, tier), metrics=metrics)]
            target = eligible[-1] if eligible else None
            state = db.get(UserAchievementState, (user_id, definition.id))
            if state is None and target is None:
                continue
            if state is None:
                state = UserAchievementState(user_id=user_id, achievement_id=definition.id, earned_count=0, progress={})
                db.add(state)
                db.flush()
            next_tier = next((tier for tier in tiers if target is None or tier.sort_order > target.sort_order), None)
            progress_criteria = _criteria_for_tier(definition, next_tier or target) if (next_tier or target) else definition.criteria
            state.progress = _progress(progress_criteria or {}, metrics)
            if target is not None:
                existing = db.scalar(
                    select(UserAchievementAward).where(
                        UserAchievementAward.user_id == user_id,
                        UserAchievementAward.achievement_id == definition.id,
                        UserAchievementAward.tier_id == target.id,
                    )
                )
                if existing is None:
                    achievement_module._award(
                        db,
                        user_id=user_id,
                        definition=definition,
                        tier=target,
                        instance_key=None,
                        source_event_key=f"admin-recalculate:{definition.id}:{target.id}:{user_id}",
                        period_key=None,
                        scope_type=None,
                        scope_key=None,
                        metadata={"source": "admin_recalculation"},
                    )
            state.current_tier_id = target.id if target else None
            state.updated_at = _now()
            changed += 1
        elif definition.achievement_type in {"SINGLE", "STATUS"}:
            try:
                eligible = evaluate_criteria(definition.criteria or {}, metrics=metrics)
            except (AchievementCriteriaError, ValueError, TypeError):
                eligible = False
            if eligible:
                achievement_module._award(
                    db,
                    user_id=user_id,
                    definition=definition,
                    tier=None,
                    instance_key=None,
                    source_event_key=f"admin-recalculate:{definition.id}:{user_id}",
                    period_key=None,
                    scope_type=None,
                    scope_key=None,
                    metadata={"source": "admin_recalculation"},
                )
                changed += 1
    db.flush()
    return changed


def revoke_single_award(
    db: Session,
    *,
    award_id: uuid.UUID,
    reason: str,
    admin_user_id: uuid.UUID | None,
) -> UserAchievementAward:
    award = db.get(UserAchievementAward, award_id)
    if award is None:
        raise HTTPException(404, "Achievement award not found")
    if award.revoked_at is not None:
        return award
    now = _now()
    award.revoked_at = now
    award.revoke_reason = reason
    award.revoked_by_admin_id = admin_user_id
    active = list(
        db.scalars(
            select(UserAchievementAward).where(
                UserAchievementAward.user_id == award.user_id,
                UserAchievementAward.achievement_id == award.achievement_id,
                UserAchievementAward.revoked_at.is_(None),
                UserAchievementAward.id != award.id,
            )
        )
    )
    state = db.get(UserAchievementState, (award.user_id, award.achievement_id))
    if state is not None:
        state.earned_count = len(active)
        state.last_earned_at = max((row.earned_at for row in active), default=state.last_earned_at)
        if active:
            tier_ids = [row.tier_id for row in active if row.tier_id]
            tiers = [db.get(AchievementTier, tier_id) for tier_id in tier_ids]
            tiers = [tier for tier in tiers if tier is not None]
            state.current_tier_id = max(tiers, key=lambda row: row.sort_order).id if tiers else None
            state.revoked_at = None
            state.revoke_reason = None
        else:
            state.current_tier_id = None
            state.revoked_at = now
            state.revoke_reason = reason
        state.updated_at = now
    db.flush()
    return award


def _competition_rows(rows):
    ranked = []
    previous_points = None
    rank = 0
    for position, (user_id, points) in enumerate(rows, start=1):
        numeric_points = int(points)
        if previous_points is None or numeric_points != previous_points:
            rank = position
            previous_points = numeric_points
        ranked.append((rank, user_id, numeric_points))
    return ranked


def stable_finalize_monthly_scope(
    db: Session,
    *,
    period_key: str,
    scope_type: str,
    scope_key: str,
    admin_user_id: uuid.UUID | None = None,
) -> dict:
    regional_module.ensure_regional_achievement_catalog(db)
    normalized_type = scope_type.upper()
    normalized_key = "nz" if normalized_type == "NATIONAL" else scope_key.strip().casefold()
    start, end = regional_module._period_bounds(period_key)
    if end > _now():
        raise HTTPException(409, "Only completed leaderboard months can be finalized")
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("select pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"leaderboard-finalize:{period_key}:{normalized_type}:{normalized_key}"},
        )
    existing = db.scalar(
        select(regional_module.LeaderboardPeriodFinalization).where(
            regional_module.LeaderboardPeriodFinalization.period_key == period_key,
            regional_module.LeaderboardPeriodFinalization.scope_type == normalized_type,
            func.lower(regional_module.LeaderboardPeriodFinalization.scope_key) == normalized_key,
        )
    )
    if existing is not None:
        return {
            "status": "already_finalized",
            "period_key": period_key,
            "scope_type": normalized_type,
            "scope_key": normalized_key,
            "participant_count": existing.participant_count,
        }
    rows = list(db.execute(regional_module._scope_query(normalized_type, normalized_key, start, end)).all())
    label = regional_module._scope_label(normalized_type, scope_key)
    awarded = []
    for rank, user_id, points in _competition_rows(rows):
        definition = regional_module._achievement_for_rank(db, rank)
        if definition is None:
            continue
        event_key = f"leaderboard-final:{period_key}:{normalized_type}:{regional_module._slug(normalized_key)}:{user_id}"
        awards = achievement_module.process_achievement_event(
            db,
            event_key=event_key,
            user_id=user_id,
            event_type="LEADERBOARD_FINALIZED",
            payload={
                "rank": rank,
                "points": points,
                "scope_type": normalized_type,
                "scope_key": normalized_key,
                "scope_label": label,
                "period_key": period_key,
            },
            occurred_at=end,
            instance_key=f"{period_key}:{normalized_type}:{regional_module._slug(normalized_key)}",
            period_key=period_key,
            scope_type=normalized_type,
            scope_key=normalized_key,
        )
        for award in awards:
            if award.achievement_id == definition.id:
                award.metadata_json = {
                    "event_type": "LEADERBOARD_FINALIZED",
                    "rank": rank,
                    "points": points,
                    "scope_label": label,
                }
                awarded.append(
                    {
                        "user_id": str(user_id),
                        "rank": rank,
                        "points": points,
                        "achievement_key": definition.key,
                    }
                )
    db.add(
        regional_module.LeaderboardPeriodFinalization(
            period_key=period_key,
            scope_type=normalized_type,
            scope_key=normalized_key,
            scope_label=label,
            finalized_by_admin_id=admin_user_id,
            participant_count=len(rows),
        )
    )
    db.flush()
    return {
        "status": "finalized",
        "period_key": period_key,
        "scope_type": normalized_type,
        "scope_key": normalized_key,
        "participant_count": len(rows),
        "awarded": awarded,
    }


def stable_current_titles(db: Session, user_id: uuid.UUID) -> list[dict]:
    now = datetime.now(regional_module.NZ_TZ)
    start = datetime(now.year, now.month, 1, tzinfo=regional_module.NZ_TZ).astimezone(timezone.utc)
    end = _now()
    city_rows = list(
        db.scalars(
            select(Station.city)
            .join(PointTransaction, PointTransaction.station_id == Station.id)
            .where(PointTransaction.user_id == user_id, PointTransaction.created_at >= start)
            .distinct()
        )
    )
    region_rows = list(
        db.scalars(
            select(Station.region)
            .join(PointTransaction, PointTransaction.station_id == Station.id)
            .where(
                PointTransaction.user_id == user_id,
                PointTransaction.created_at >= start,
                Station.region.is_not(None),
            )
            .distinct()
        )
    )
    scopes = [("CITY", value) for value in city_rows if value] + [("REGION", value) for value in region_rows if value] + [("NATIONAL", "nz")]
    titles = []
    for scope_type, scope_key in scopes:
        grouped = regional_module._scope_query(scope_type, scope_key, start, end).order_by(None).subquery()
        user_points = db.scalar(select(grouped.c.points).where(grouped.c.user_id == user_id))
        if user_points is None:
            continue
        rank = 1 + int(db.scalar(select(func.count()).select_from(grouped).where(grouped.c.points > user_points)) or 0)
        titles.append(
            {
                "scope_type": scope_type,
                "scope_key": scope_key,
                "scope_label": regional_module._scope_label(scope_type, scope_key),
                "rank": rank,
                "points": int(user_points),
                "is_number_one": rank == 1,
            }
        )
    return titles


def finalize_completed_monthly_leaderboards(db: Session, now: datetime | None = None) -> int:
    local_now = (now or _now()).astimezone(regional_module.NZ_TZ)
    current_start = datetime(local_now.year, local_now.month, 1, tzinfo=regional_module.NZ_TZ)
    previous_end = current_start
    if current_start.month == 1:
        previous_start = datetime(current_start.year - 1, 12, 1, tzinfo=regional_module.NZ_TZ)
    else:
        previous_start = datetime(current_start.year, current_start.month - 1, 1, tzinfo=regional_module.NZ_TZ)
    period_key = previous_start.strftime("%Y-%m")
    start_utc = previous_start.astimezone(timezone.utc)
    end_utc = previous_end.astimezone(timezone.utc)
    cities = list(
        db.scalars(
            select(Station.city)
            .join(PointTransaction, PointTransaction.station_id == Station.id)
            .where(
                PointTransaction.created_at >= start_utc,
                PointTransaction.created_at < end_utc,
                Station.country_code == "NZ",
                Station.city.is_not(None),
            )
            .distinct()
        )
    )
    regions = list(
        db.scalars(
            select(Station.region)
            .join(PointTransaction, PointTransaction.station_id == Station.id)
            .where(
                PointTransaction.created_at >= start_utc,
                PointTransaction.created_at < end_utc,
                Station.country_code == "NZ",
                Station.region.is_not(None),
            )
            .distinct()
        )
    )
    scopes = [("NATIONAL", "nz")] + [("REGION", value) for value in regions if value] + [("CITY", value) for value in cities if value]
    finalized = 0
    for scope_type, scope_key in scopes:
        result = stable_finalize_monthly_scope(
            db,
            period_key=period_key,
            scope_type=scope_type,
            scope_key=scope_key,
            admin_user_id=None,
        )
        if result["status"] == "finalized":
            finalized += 1
    db.commit()
    return finalized


def run_monthly_achievement_maintenance() -> int:
    with SessionLocal() as db:
        return finalize_completed_monthly_leaderboards(db)


def install_achievement_stability() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    regional_module.finalize_monthly_scope = stable_finalize_monthly_scope
    regional_module.current_titles = stable_current_titles
    profile_module.current_titles = stable_current_titles
    original_cards = profile_module._achievement_cards

    def reconciled_cards(db: Session, user_id: uuid.UUID):
        tier_ids = list(
            db.scalars(
                select(AchievementDefinition.id).where(
                    AchievementDefinition.enabled.is_(True),
                    AchievementDefinition.achievement_type == "TIERED",
                )
            )
        )
        for achievement_id in tier_ids:
            reconcile_definition_states(db, achievement_id)
        db.flush()
        return original_cards(db, user_id)

    profile_module._achievement_cards = reconciled_cards
    _INSTALLED = True


@stability_router.get("/admin/achievements/analytics/summary")
def stable_achievement_analytics(
    _: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    contributor_count = _contributor_count(db)
    definitions = list(
        db.scalars(
            select(AchievementDefinition).order_by(
                AchievementDefinition.category,
                AchievementDefinition.sort_order,
                AchievementDefinition.key,
            )
        )
    )
    rows = []
    for definition in definitions:
        active_awards = select(UserAchievementAward).where(
            UserAchievementAward.achievement_id == definition.id,
            UserAchievementAward.revoked_at.is_(None),
        ).subquery()
        earned_users = int(db.scalar(select(func.count(func.distinct(active_awards.c.user_id)))) or 0)
        award_count = int(db.scalar(select(func.count()).select_from(active_awards)) or 0)
        rate = round((earned_users / contributor_count * 100), 2) if contributor_count else 0.0
        first_awards = (
            select(
                UserAchievementAward.user_id,
                func.min(UserAchievementAward.earned_at).label("first_earned_at"),
            )
            .where(
                UserAchievementAward.achievement_id == definition.id,
                UserAchievementAward.revoked_at.is_(None),
            )
            .group_by(UserAchievementAward.user_id)
            .subquery()
        )
        age_rows = list(
            db.execute(
                select(Profile.created_at, first_awards.c.first_earned_at).join(
                    first_awards, first_awards.c.user_id == Profile.id
                )
            ).all()
        )
        days = []
        for created_at, earned_at in age_rows:
            if created_at and earned_at:
                created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
                earned = earned_at if earned_at.tzinfo else earned_at.replace(tzinfo=timezone.utc)
                days.append(max(0.0, (earned - created).total_seconds() / 86400))
        rows.append(
            {
                "achievement_id": str(definition.id),
                "key": definition.key,
                "name": definition.name,
                "category": definition.category,
                "enabled": definition.enabled,
                "earned_users": earned_users,
                "award_count": award_count,
                "completion_rate": rate,
                "rarity": _rarity(rate),
                "average_days_to_unlock": round(sum(days) / len(days), 1) if days else None,
            }
        )
    return {"contributors": contributor_count, "achievements": rows}


@stability_router.post("/admin/achievements", status_code=201)
def stable_create_achievement(
    payload: AchievementInput,
    _: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    validate_criteria(payload.criteria)
    for tier in payload.tiers:
        if tier.criteria:
            validate_criteria(tier.criteria, "tier.criteria")
    if db.scalar(select(AchievementDefinition.id).where(AchievementDefinition.key == payload.key)) is not None:
        raise HTTPException(409, "Achievement key already exists")
    if payload.achievement_type == "TIERED" and not payload.tiers:
        raise HTTPException(422, "Tiered achievements require at least one tier")
    definition = AchievementDefinition(**payload.model_dump(exclude={"tiers"}))
    db.add(definition)
    db.flush()
    for tier in payload.tiers:
        db.add(AchievementTier(achievement_id=definition.id, **tier.model_dump()))
    db.flush()
    reconcile_definition_states(db, definition.id)
    db.commit()
    db.refresh(definition)
    return _definition_payload(definition, db)


@stability_router.patch("/admin/achievements/{achievement_id}")
def stable_update_achievement(
    achievement_id: uuid.UUID,
    payload: AchievementPatch,
    _: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    definition = db.get(AchievementDefinition, achievement_id)
    if definition is None:
        raise HTTPException(404, "Achievement not found")
    changes = payload.model_dump(exclude_unset=True)
    if "criteria" in changes:
        validate_criteria(changes["criteria"])
    for key, value in changes.items():
        setattr(definition, key, value)
    definition.updated_at = _now()
    db.flush()
    reconcile_definition_states(db, achievement_id)
    db.commit()
    db.refresh(definition)
    return _definition_payload(definition, db)


@stability_router.put("/admin/achievements/{achievement_id}/tiers")
def stable_replace_tiers(
    achievement_id: uuid.UUID,
    payload: TierReplaceInput,
    _: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    definition = db.get(AchievementDefinition, achievement_id)
    if definition is None:
        raise HTTPException(404, "Achievement not found")
    if definition.achievement_type != "TIERED":
        raise HTTPException(409, "Only tiered achievements can have tiers")
    if not payload.tiers:
        raise HTTPException(422, "At least one tier is required")
    keys = [item.key for item in payload.tiers]
    orders = [item.sort_order for item in payload.tiers]
    if len(keys) != len(set(keys)) or len(orders) != len(set(orders)):
        raise HTTPException(422, "Tier keys and sort orders must be unique")
    for item in payload.tiers:
        if item.criteria:
            validate_criteria(item.criteria, "tier.criteria")
    existing = list(db.scalars(select(AchievementTier).where(AchievementTier.achievement_id == achievement_id)))
    existing_by_key = {row.key: row for row in existing}
    requested = set(keys)
    referenced_tier_ids = set(
        db.scalars(
            select(UserAchievementAward.tier_id).where(
                UserAchievementAward.achievement_id == achievement_id,
                UserAchievementAward.tier_id.is_not(None),
            )
        )
    )
    for row in existing:
        if row.key not in requested:
            if row.id in referenced_tier_ids:
                raise HTTPException(409, f"Tier '{row.key}' has award history and cannot be deleted")
            db.delete(row)
    for item in payload.tiers:
        row = existing_by_key.get(item.key)
        if row is None:
            db.add(AchievementTier(achievement_id=achievement_id, **item.model_dump()))
        else:
            for key, value in item.model_dump().items():
                setattr(row, key, value)
    definition.updated_at = _now()
    db.flush()
    reconcile_definition_states(db, achievement_id)
    db.commit()
    db.refresh(definition)
    return _definition_payload(definition, db)


@stability_router.post("/admin/achievements/{achievement_id}/recalculate")
def stable_recalculate_achievement(
    achievement_id: uuid.UUID,
    _: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    if db.get(AchievementDefinition, achievement_id) is None:
        raise HTTPException(404, "Achievement not found")
    changed = reconcile_definition_states(db, achievement_id)
    db.commit()
    return {"recalculated_users": changed}


@stability_router.post("/admin/achievement-awards/{award_id}/revoke")
def stable_revoke_award(
    award_id: uuid.UUID,
    body: achievement_module.RevokeInput,
    principal: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    award = revoke_single_award(
        db,
        award_id=award_id,
        reason=body.reason,
        admin_user_id=principal.profile.id,
    )
    db.commit()
    return {"revoked_award_id": str(award.id)}
