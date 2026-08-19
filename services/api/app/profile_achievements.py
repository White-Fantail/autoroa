import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .achievements import (
    AchievementDefinition,
    AchievementTier,
    UserAchievementAward,
    UserAchievementState,
)
from .auth import Principal, current_principal
from .db import Base, get_db
from .regional_achievements import current_titles, trophy_history


class UserFeaturedAchievement(Base):
    __tablename__ = "user_featured_achievements"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    slot: Mapped[int] = mapped_column(Integer, primary_key=True)
    achievement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("achievement_definitions.id", ondelete="CASCADE"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "achievement_id", name="uq_user_featured_achievement"
        ),
    )


class UserAchievementSeen(Base):
    __tablename__ = "user_achievement_seen"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    award_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_achievement_awards.id", ondelete="CASCADE"), primary_key=True
    )
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_user_achievement_seen_user_seen", "user_id", "seen_at"),)


class FeaturedInput(BaseModel):
    achievement_ids: list[uuid.UUID] = Field(default_factory=list, max_length=3)


class SeenInput(BaseModel):
    award_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


profile_achievement_router = APIRouter(prefix="/api/v1")


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


def _achievement_cards(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
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
    for tier in db.scalars(
        select(AchievementTier).order_by(
            AchievementTier.achievement_id, AchievementTier.sort_order
        )
    ):
        tiers_by_achievement[tier.achievement_id].append(tier)

    cards: list[dict[str, Any]] = []
    for definition in definitions:
        state = states.get(definition.id)
        earned = bool(state and state.earned_count > 0 and state.revoked_at is None)
        secret_locked = definition.visibility == "SECRET" and not earned
        current_tier = (
            db.get(AchievementTier, state.current_tier_id)
            if state and state.current_tier_id
            else None
        )
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
                "description": (
                    definition.description
                    if not secret_locked
                    else "Keep contributing to discover this achievement."
                ),
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


def _featured(db: Session, user_id: uuid.UUID) -> list[str]:
    rows = list(
        db.scalars(
            select(UserFeaturedAchievement)
            .where(UserFeaturedAchievement.user_id == user_id)
            .order_by(UserFeaturedAchievement.slot)
        )
    )
    return [str(row.achievement_id) for row in rows]


def _trophy_summary(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for trophy in history:
        scope_type = trophy.get("scope_type") or ""
        scope_key = trophy.get("scope_key") or ""
        achievement_key = trophy.get("achievement_key") or ""
        key = (achievement_key, scope_type, scope_key)
        if key not in grouped:
            grouped[key] = {
                "achievement_key": achievement_key,
                "name": trophy.get("name"),
                "scope_type": scope_type,
                "scope_key": scope_key,
                "count": 0,
                "periods": [],
            }
        grouped[key]["count"] += 1
        if trophy.get("period_key"):
            grouped[key]["periods"].append(trophy["period_key"])
    return sorted(
        grouped.values(),
        key=lambda item: (item["scope_type"], item["scope_key"], item["achievement_key"]),
    )


def _award_feed_payload(
    award: UserAchievementAward, definition: AchievementDefinition, tier: AchievementTier | None
) -> dict[str, Any]:
    return {
        "award_id": str(award.id),
        "achievement_id": str(definition.id),
        "achievement_key": definition.key,
        "name": definition.name,
        "description": definition.description,
        "category": definition.category,
        "icon": tier.icon if tier and tier.icon else definition.icon,
        "tier": _tier_payload(tier),
        "period_key": award.period_key,
        "scope_type": award.scope_type,
        "scope_key": award.scope_key,
        "earned_at": award.earned_at,
        "metadata": award.metadata_json,
    }


@profile_achievement_router.get("/me/achievement-profile")
def achievement_profile(
    p: Principal = Depends(current_principal), db: Session = Depends(get_db)
):
    history = trophy_history(db, p.profile.id)
    return {
        "achievements": _achievement_cards(db, p.profile.id),
        "featured_achievement_ids": _featured(db, p.profile.id),
        "current_titles": current_titles(db, p.profile.id),
        "trophy_summary": _trophy_summary(history),
        "trophies": history,
    }


@profile_achievement_router.put("/me/featured-achievements")
def set_featured_achievements(
    body: FeaturedInput,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    if len(set(body.achievement_ids)) != len(body.achievement_ids):
        raise HTTPException(422, "Featured achievements must be unique")
    if body.achievement_ids:
        earned = set(
            db.scalars(
                select(UserAchievementState.achievement_id).where(
                    UserAchievementState.user_id == p.profile.id,
                    UserAchievementState.achievement_id.in_(body.achievement_ids),
                    UserAchievementState.earned_count > 0,
                    UserAchievementState.revoked_at.is_(None),
                )
            )
        )
        if earned != set(body.achievement_ids):
            raise HTTPException(422, "Only active earned achievements can be featured")
    for row in list(
        db.scalars(
            select(UserFeaturedAchievement).where(
                UserFeaturedAchievement.user_id == p.profile.id
            )
        )
    ):
        db.delete(row)
    db.flush()
    now = datetime.now(timezone.utc)
    for slot, achievement_id in enumerate(body.achievement_ids, start=1):
        db.add(
            UserFeaturedAchievement(
                user_id=p.profile.id,
                slot=slot,
                achievement_id=achievement_id,
                updated_at=now,
            )
        )
    db.commit()
    return {"featured_achievement_ids": [str(value) for value in body.achievement_ids]}


@profile_achievement_router.get("/me/achievement-feed")
def achievement_feed(
    p: Principal = Depends(current_principal), db: Session = Depends(get_db)
):
    rows = list(
        db.execute(
            select(UserAchievementAward, AchievementDefinition, AchievementTier)
            .join(
                AchievementDefinition,
                AchievementDefinition.id == UserAchievementAward.achievement_id,
            )
            .outerjoin(AchievementTier, AchievementTier.id == UserAchievementAward.tier_id)
            .outerjoin(
                UserAchievementSeen,
                (UserAchievementSeen.user_id == p.profile.id)
                & (UserAchievementSeen.award_id == UserAchievementAward.id),
            )
            .where(
                UserAchievementAward.user_id == p.profile.id,
                UserAchievementAward.revoked_at.is_(None),
                UserAchievementSeen.award_id.is_(None),
            )
            .order_by(UserAchievementAward.earned_at.asc())
            .limit(10)
        ).all()
    )
    return [
        _award_feed_payload(award, definition, tier)
        for award, definition, tier in rows
    ]


@profile_achievement_router.post("/me/achievement-feed/seen")
def mark_achievement_feed_seen(
    body: SeenInput,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    if not body.award_ids:
        return {"seen": 0}
    owned = set(
        db.scalars(
            select(UserAchievementAward.id).where(
                UserAchievementAward.user_id == p.profile.id,
                UserAchievementAward.id.in_(body.award_ids),
            )
        )
    )
    now = datetime.now(timezone.utc)
    seen = 0
    for award_id in body.award_ids:
        if award_id not in owned:
            continue
        if db.get(UserAchievementSeen, (p.profile.id, award_id)) is None:
            db.add(
                UserAchievementSeen(
                    user_id=p.profile.id, award_id=award_id, seen_at=now
                )
            )
            seen += 1
    db.commit()
    return {"seen": seen}
