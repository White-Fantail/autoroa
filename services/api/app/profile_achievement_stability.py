import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import profile_achievements as profile_module
from .achievements import AchievementDefinition, AchievementTier, UserAchievementState


def _tier_payload(tier: AchievementTier | None) -> dict[str, Any] | None:
    if tier is None:
        return None
    return {
        "id": str(tier.id),
        "key": tier.key,
        "name": tier.name,
        "threshold": float(tier.threshold) if tier.threshold is not None else None,
        "sort_order": tier.sort_order,
        "icon": tier.icon,
    }


def stable_achievement_cards(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    definitions = list(
        db.scalars(
            select(AchievementDefinition)
            .where(AchievementDefinition.enabled.is_(True))
            .order_by(AchievementDefinition.category, AchievementDefinition.sort_order)
        )
    )
    states = {
        row.achievement_id: row
        for row in db.scalars(
            select(UserAchievementState).where(UserAchievementState.user_id == user_id)
        )
    }
    tiers_by_achievement: dict[uuid.UUID, list[AchievementTier]] = defaultdict(list)
    tier_by_id: dict[uuid.UUID, AchievementTier] = {}
    for tier in db.scalars(
        select(AchievementTier).order_by(
            AchievementTier.achievement_id, AchievementTier.sort_order
        )
    ):
        tiers_by_achievement[tier.achievement_id].append(tier)
        tier_by_id[tier.id] = tier

    cards: list[dict[str, Any]] = []
    for definition in definitions:
        state = states.get(definition.id)
        earned = bool(state and state.earned_count > 0 and state.revoked_at is None)
        secret_locked = definition.visibility == "SECRET" and not earned
        current_tier = tier_by_id.get(state.current_tier_id) if state and state.current_tier_id else None
        tiers = tiers_by_achievement.get(definition.id, [])
        next_tier = None
        if definition.achievement_type == "TIERED":
            current_order = current_tier.sort_order if current_tier else -1
            next_tier = next((tier for tier in tiers if tier.sort_order > current_order), None)
        cards.append(
            {
                "id": str(definition.id),
                "key": definition.key if not secret_locked else None,
                "name": definition.name if not secret_locked else "Secret achievement",
                "description": definition.description if not secret_locked else "Keep contributing to discover this achievement.",
                "category": definition.category,
                "icon": definition.icon if not secret_locked else "secret",
                "visibility": definition.visibility,
                "achievement_type": definition.achievement_type,
                "earned": earned,
                "earned_count": state.earned_count if state else 0,
                "first_earned_at": state.first_earned_at if state else None,
                "last_earned_at": state.last_earned_at if state else None,
                "progress": state.progress if state else {},
                "current_tier": _tier_payload(current_tier),
                "next_tier": _tier_payload(next_tier),
                "tiers": [_tier_payload(tier) for tier in tiers] if not secret_locked else [],
                "revoked_at": state.revoked_at if state else None,
            }
        )
    return cards


def install_profile_achievement_stability() -> None:
    # Admin definition/tier mutations already recalculate affected users. Profile
    # reads therefore stay read-only and never fan out across all contributors.
    profile_module._achievement_cards = stable_achievement_cards
