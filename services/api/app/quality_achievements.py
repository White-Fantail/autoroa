import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .achievements import (
    AchievementDefinition,
    UserAchievementAward,
    UserAchievementState,
    evaluate_user_achievements,
    set_achievement_metric,
)
from .models import Observation, Station
from .trust import refresh_user_trust
from .user_price_boards import CommunityPriceBoardSubmission


QUALITY_ACHIEVEMENTS = [
    {
        "key": "fresh_eyes",
        "name": "Fresh Eyes",
        "description": "Refresh a fuel price that has not been updated for at least 7 days.",
        "category": "QUALITY",
        "icon": "fresh",
        "sort_order": 400,
        "criteria": {"event": "payload.max_previous_age_days", "op": "gte", "value": 7},
    },
    {
        "key": "rescuer",
        "name": "Rescuer",
        "description": "Refresh a fuel price that has been stale for at least 30 days.",
        "category": "QUALITY",
        "icon": "rescue",
        "sort_order": 410,
        "criteria": {"event": "payload.max_previous_age_days", "op": "gte", "value": 30},
    },
    {
        "key": "full_board",
        "name": "Full Board",
        "description": "Successfully update at least 3 fuel types from one station price-board photo.",
        "category": "QUALITY",
        "icon": "board",
        "sort_order": 420,
        "criteria": {"event": "payload.applied_fuel_count", "op": "gte", "value": 3},
    },
    {
        "key": "trusted_contributor",
        "name": "Trusted Contributor",
        "description": "Maintain at least 95% accuracy across your latest 50 evaluated fuel-price results.",
        "category": "QUALITY",
        "icon": "trusted",
        "sort_order": 430,
        "achievement_type": "STATUS",
        "criteria": {"metric": "trusted_contributor", "op": "eq", "value": 1},
    },
]


def ensure_quality_achievement_catalog(db: Session) -> None:
    for item in QUALITY_ACHIEVEMENTS:
        exists = db.scalar(
            select(AchievementDefinition).where(AchievementDefinition.key == item["key"])
        )
        if exists is not None:
            continue
        db.add(
            AchievementDefinition(
                key=item["key"],
                name=item["name"],
                description=item["description"],
                category=item["category"],
                icon=item["icon"],
                achievement_type=item.get("achievement_type", "SINGLE"),
                visibility="PUBLIC",
                repeatable=False,
                enabled=True,
                sort_order=item["sort_order"],
                criteria=item["criteria"],
            )
        )
    db.flush()


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _quality_context(
    db: Session,
    *,
    submission_id: uuid.UUID,
    observed_at: datetime,
) -> dict[str, Any]:
    from .contribution_rewards import SubmissionFuelResult

    results = list(
        db.scalars(
            select(SubmissionFuelResult).where(
                SubmissionFuelResult.submission_id == submission_id
            )
        )
    )
    applied = [row for row in results if row.result == "APPLIED"]
    ages: list[float] = []
    current_time = _aware(observed_at) or datetime.now(timezone.utc)
    for row in applied:
        if row.previous_observation_id is None:
            continue
        previous = db.get(Observation, row.previous_observation_id)
        previous_time = _aware(previous.observed_at) if previous is not None else None
        if previous_time is None or previous_time > current_time:
            continue
        ages.append((current_time - previous_time).total_seconds() / 86400)
    return {
        "applied_fuel_count": len(applied),
        "max_previous_age_days": round(max(ages), 2) if ages else 0,
    }


def _sync_trusted_status(db: Session, user_id: uuid.UUID, trusted: bool) -> None:
    definition = db.scalar(
        select(AchievementDefinition).where(AchievementDefinition.key == "trusted_contributor")
    )
    if definition is None:
        return
    state = db.get(UserAchievementState, (user_id, definition.id))
    if trusted:
        if state is not None:
            state.revoked_at = None
            state.revoke_reason = None
        award = db.scalar(
            select(UserAchievementAward).where(
                UserAchievementAward.user_id == user_id,
                UserAchievementAward.achievement_id == definition.id,
            )
        )
        if award is not None:
            award.revoked_at = None
            award.revoke_reason = None
        return
    if state is None or state.earned_count == 0 or state.revoked_at is not None:
        return
    now = datetime.now(timezone.utc)
    state.revoked_at = now
    state.revoke_reason = "Trusted Contributor requirements are no longer met."
    for award in db.scalars(
        select(UserAchievementAward).where(
            UserAchievementAward.user_id == user_id,
            UserAchievementAward.achievement_id == definition.id,
            UserAchievementAward.revoked_at.is_(None),
        )
    ):
        award.revoked_at = now
        award.revoke_reason = state.revoke_reason


def refresh_quality_achievements(
    db: Session,
    *,
    user_id: uuid.UUID,
    submission_id: uuid.UUID | None = None,
    station: Station | None = None,
    observed_at: datetime | None = None,
    moderation_status: str | None = None,
) -> list[UserAchievementAward]:
    ensure_quality_achievement_catalog(db)
    trust = refresh_user_trust(db, user_id, moderation_status=moderation_status)
    set_achievement_metric(db, user_id, "evaluated_price_results", trust.evaluated_result_count)
    set_achievement_metric(
        db,
        user_id,
        "recent_accuracy_percent",
        trust.recent_accuracy if trust.recent_accuracy is not None else Decimal("0"),
    )
    set_achievement_metric(db, user_id, "trusted_contributor", 1 if trust.is_trusted_contributor else 0)

    # Restricted accounts keep historical achievements, but cannot earn new quality
    # achievements and cannot display the current Trusted Contributor status.
    if trust.moderation_status != "ACTIVE":
        _sync_trusted_status(db, user_id, False)
        db.flush()
        return []

    context: dict[str, Any] | None = None
    source_event_key: str | None = None
    if submission_id is not None:
        context = {
            "type": "QUALITY_CONTRIBUTION_EVALUATED",
            "payload": _quality_context(
                db,
                submission_id=submission_id,
                observed_at=observed_at or datetime.now(timezone.utc),
            ),
        }
        if station is not None:
            context["payload"]["station_id"] = str(station.id)
        source_event_key = f"quality-contribution:{submission_id}"

    awards = evaluate_user_achievements(
        db,
        user_id,
        event=context,
        source_event_key=source_event_key,
        metadata={"source": "quality"},
    )
    _sync_trusted_status(db, user_id, trust.is_trusted_contributor)
    db.flush()
    return awards


def bootstrap_existing_quality_achievements(db: Session) -> int:
    user_ids = set(db.scalars(select(CommunityPriceBoardSubmission.user_id).distinct()))
    count = 0
    for user_id in user_ids:
        refresh_quality_achievements(db, user_id=user_id)
        count += 1
    db.flush()
    return count


def install_quality_achievement_processing(community_module: Any) -> None:
    original = community_module._apply_job_prices
    if getattr(original, "_quality_achievement_wrapped", False):
        return

    def quality_apply(
        db: Session,
        *,
        job: Any,
        station: Station,
        source: Any,
        verification: Any,
        prices: list[dict[str, Any]],
        observed_at: datetime,
    ):
        observations = original(
            db,
            job=job,
            station=station,
            source=source,
            verification=verification,
            prices=prices,
            observed_at=observed_at,
        )
        contribution = db.scalar(
            select(CommunityPriceBoardSubmission).where(
                CommunityPriceBoardSubmission.ocr_job_id == job.id
            )
        )
        if contribution is not None:
            refresh_quality_achievements(
                db,
                user_id=contribution.user_id,
                submission_id=contribution.id,
                station=station,
                observed_at=observed_at,
            )
        db.flush()
        return observations

    quality_apply._quality_achievement_wrapped = True
    community_module._apply_job_prices = quality_apply
