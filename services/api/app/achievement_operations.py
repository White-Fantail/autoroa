import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .achievements import (
    AchievementDefinition,
    AchievementTier,
    UserAchievementAward,
    UserAchievementState,
    _definition_payload,
)
from .auth import Principal, admin_principal
from .db import get_db
from .models import Profile
from .user_price_boards import CommunityPriceBoardSubmission

operations_router = APIRouter(prefix="/api/v1/admin/achievements")


def _now():
    return datetime.now(timezone.utc)


class TierReplaceItem(BaseModel):
    key: str = Field(min_length=1, max_length=48)
    name: str = Field(min_length=1, max_length=96)
    threshold: Decimal | None = Field(default=None, ge=0)
    criteria: dict | None = None
    sort_order: int = Field(ge=0)
    icon: str | None = Field(default=None, max_length=255)


class TierReplaceInput(BaseModel):
    tiers: list[TierReplaceItem]


class GrantInput(BaseModel):
    user_id: uuid.UUID
    tier_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=1000)
    period_key: str | None = Field(default=None, max_length=64)
    scope_type: str | None = Field(default=None, max_length=32)
    scope_key: str | None = Field(default=None, max_length=128)


def _rarity(rate: float) -> str:
    if rate >= 40:
        return "Common"
    if rate >= 15:
        return "Uncommon"
    if rate >= 5:
        return "Rare"
    if rate >= 1:
        return "Epic"
    return "Legendary"


def _contributor_count(db: Session) -> int:
    count = int(db.scalar(select(func.count(func.distinct(CommunityPriceBoardSubmission.user_id)))) or 0)
    if count:
        return count
    return int(db.scalar(select(func.count()).select_from(Profile).where(Profile.deleted_at.is_(None))) or 0)


@operations_router.put("/{achievement_id}/tiers")
def replace_tiers(
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
    existing = list(db.scalars(select(AchievementTier).where(AchievementTier.achievement_id == achievement_id)))
    existing_by_key = {row.key: row for row in existing}
    requested = set(keys)
    referenced_tier_ids = set(db.scalars(select(UserAchievementAward.tier_id).where(UserAchievementAward.achievement_id == achievement_id, UserAchievementAward.tier_id.is_not(None))))
    for row in existing:
        if row.key not in requested:
            if row.id in referenced_tier_ids:
                raise HTTPException(409, f"Tier '{row.key}' has award history and cannot be deleted")
            db.delete(row)
    for item in payload.tiers:
        row = existing_by_key.get(item.key)
        if row is None:
            row = AchievementTier(achievement_id=achievement_id, **item.model_dump())
            db.add(row)
        else:
            for key, value in item.model_dump().items():
                setattr(row, key, value)
    definition.updated_at = _now()
    db.commit()
    db.refresh(definition)
    return _definition_payload(definition, db)


@operations_router.post("/{achievement_id}/grant", status_code=201)
def grant_achievement(
    achievement_id: uuid.UUID,
    payload: GrantInput,
    principal: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    definition = db.get(AchievementDefinition, achievement_id)
    user = db.get(Profile, payload.user_id)
    if definition is None or user is None:
        raise HTTPException(404, "Achievement or user not found")
    tier = None
    if definition.achievement_type == "TIERED":
        if payload.tier_id is None:
            raise HTTPException(422, "tier_id is required for tiered achievements")
        tier = db.get(AchievementTier, payload.tier_id)
        if tier is None or tier.achievement_id != definition.id:
            raise HTTPException(422, "Invalid tier for this achievement")
    elif payload.tier_id is not None:
        raise HTTPException(422, "tier_id is only valid for tiered achievements")

    instance = uuid.uuid4().hex
    award_key = f"admin-grant:{payload.user_id}:{definition.id}:{instance}"
    now = _now()
    award = UserAchievementAward(
        award_key=award_key,
        user_id=payload.user_id,
        achievement_id=definition.id,
        tier_id=tier.id if tier else None,
        source_event_key=f"admin-grant:{instance}",
        period_key=payload.period_key,
        scope_type=payload.scope_type,
        scope_key=payload.scope_key,
        metadata_json={"source": "admin_grant", "note": payload.note, "admin_user_id": str(principal.profile.id)},
        earned_at=now,
    )
    db.add(award)
    state = db.get(UserAchievementState, (payload.user_id, definition.id))
    if state is None:
        state = UserAchievementState(user_id=payload.user_id, achievement_id=definition.id)
        db.add(state)
    state.earned_count += 1
    state.first_earned_at = state.first_earned_at or now
    state.last_earned_at = now
    state.revoked_at = None
    state.revoke_reason = None
    if tier is not None:
        current = db.get(AchievementTier, state.current_tier_id) if state.current_tier_id else None
        if current is None or tier.sort_order >= current.sort_order:
            state.current_tier_id = tier.id
    state.updated_at = now
    db.commit()
    return {"award_id": str(award.id), "achievement_id": str(definition.id), "user_id": str(user.id), "tier_id": str(tier.id) if tier else None}


@operations_router.get("/{achievement_id}/earners")
def achievement_earners(
    achievement_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=500),
    _: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    definition = db.get(AchievementDefinition, achievement_id)
    if definition is None:
        raise HTTPException(404, "Achievement not found")
    rows = list(db.execute(
        select(UserAchievementAward, Profile)
        .join(Profile, Profile.id == UserAchievementAward.user_id)
        .where(UserAchievementAward.achievement_id == achievement_id)
        .order_by(UserAchievementAward.earned_at.desc())
        .limit(limit)
    ).all())
    return [
        {
            "award_id": str(award.id),
            "user_id": str(profile.id),
            "display_name": profile.display_name,
            "tier_id": str(award.tier_id) if award.tier_id else None,
            "period_key": award.period_key,
            "scope_type": award.scope_type,
            "scope_key": award.scope_key,
            "earned_at": award.earned_at,
            "revoked_at": award.revoked_at,
            "revoke_reason": award.revoke_reason,
        }
        for award, profile in rows
    ]


@operations_router.get("/analytics/summary")
def achievement_analytics(
    _: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    contributor_count = _contributor_count(db)
    definitions = list(db.scalars(select(AchievementDefinition).order_by(AchievementDefinition.category, AchievementDefinition.sort_order, AchievementDefinition.key)))
    rows = []
    for definition in definitions:
        active_awards = select(UserAchievementAward).where(UserAchievementAward.achievement_id == definition.id, UserAchievementAward.revoked_at.is_(None)).subquery()
        earned_users = int(db.scalar(select(func.count(func.distinct(active_awards.c.user_id)))) or 0)
        award_count = int(db.scalar(select(func.count()).select_from(active_awards)) or 0)
        rate = round((earned_users / contributor_count * 100), 2) if contributor_count else 0.0
        first_awards = (
            select(UserAchievementAward.user_id, func.min(UserAchievementAward.earned_at).label("first_earned_at"))
            .where(UserAchievementAward.achievement_id == definition.id, UserAchievementAward.revoked_at.is_(None))
            .group_by(UserAchievementAward.user_id)
            .subquery()
        )
        age_rows = list(db.execute(select(Profile.created_at, first_awards.c.first_earned_at).join(first_awards, first_awards.c.user_id == Profile.id)).all())
        days = []
        for created_at, earned_at in age_rows:
            if created_at and earned_at:
                created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
                earned = earned_at if earned_at.tzinfo else earned_at.replace(tzinfo=timezone.utc)
                days.append(max(0.0, (earned - created).total_seconds() / 86400))
        rows.append({
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
        })
    return {"contributors": contributor_count, "achievements": rows}
