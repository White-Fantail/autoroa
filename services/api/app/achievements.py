import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import Principal, admin_principal, current_principal
from .db import Base, get_db
from .models import Profile


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AchievementDefinition(Base):
    __tablename__ = "achievement_definitions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(96), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(48), index=True)
    icon: Mapped[str | None] = mapped_column(String(255))
    achievement_type: Mapped[str] = mapped_column(String(24), default="SINGLE")
    visibility: Mapped[str] = mapped_column(String(16), default="PUBLIC")
    repeatable: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint("achievement_type in ('SINGLE','TIERED','REPEATABLE','STATUS')", name="achievement_definition_type_valid"),
        CheckConstraint("visibility in ('PUBLIC','HIDDEN','SECRET')", name="achievement_definition_visibility_valid"),
        CheckConstraint("sort_order >= 0", name="achievement_definition_sort_nonnegative"),
        Index("ix_achievement_definition_category_sort", "category", "sort_order"),
    )


class AchievementTier(Base):
    __tablename__ = "achievement_tiers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    achievement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("achievement_definitions.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(String(96))
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    criteria: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer)
    icon: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        UniqueConstraint("achievement_id", "key", name="uq_achievement_tier_key"),
        UniqueConstraint("achievement_id", "sort_order", name="uq_achievement_tier_sort"),
        CheckConstraint("sort_order >= 0", name="achievement_tier_sort_nonnegative"),
        CheckConstraint("threshold is null or threshold >= 0", name="achievement_tier_threshold_nonnegative"),
    )


class UserAchievementState(Base):
    __tablename__ = "user_achievement_states"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    achievement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("achievement_definitions.id", ondelete="CASCADE"), primary_key=True)
    current_tier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("achievement_tiers.id", ondelete="SET NULL"), index=True)
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    earned_count: Mapped[int] = mapped_column(Integer, default=0)
    first_earned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_earned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint("earned_count >= 0", name="user_achievement_state_count_nonnegative"),
        Index("ix_user_achievement_state_user_updated", "user_id", "updated_at"),
    )


class UserAchievementAward(Base):
    __tablename__ = "user_achievement_awards"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    award_key: Mapped[str] = mapped_column(String(255), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    achievement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("achievement_definitions.id", ondelete="CASCADE"), index=True)
    tier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("achievement_tiers.id", ondelete="SET NULL"))
    source_event_key: Mapped[str | None] = mapped_column(String(255), index=True)
    period_key: Mapped[str | None] = mapped_column(String(64), index=True)
    scope_type: Mapped[str | None] = mapped_column(String(32))
    scope_key: Mapped[str | None] = mapped_column(String(128), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(Text)
    revoked_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))

    __table_args__ = (
        Index("ix_user_achievement_award_user_earned", "user_id", "earned_at"),
        Index("ix_user_achievement_award_scope_period", "scope_type", "scope_key", "period_key"),
    )


class AchievementMetric(Base):
    __tablename__ = "achievement_metrics"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(96), primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=Decimal("0"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (Index("ix_achievement_metric_key_value", "metric_key", "value"),)


class AchievementEventReceipt(Base):
    __tablename__ = "achievement_event_receipts"

    event_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(96), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


SUPPORTED_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "between", "in", "not_in", "contains"}


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    return Decimal(str(value))


def _field(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    if operator not in SUPPORTED_OPERATORS:
        raise ValueError(f"Unsupported achievement operator: {operator}")
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if operator in {"in", "not_in"}:
        result = actual in expected if expected is not None else False
        return result if operator == "in" else not result
    if operator == "contains":
        return actual is not None and expected in actual
    if actual is None:
        return False
    if operator == "between":
        low, high = expected
        try:
            actual_value, low_value, high_value = _decimal(actual), _decimal(low), _decimal(high)
        except Exception:
            actual_value, low_value, high_value = actual, low, high
        return low_value <= actual_value <= high_value
    try:
        actual_value, expected_value = _decimal(actual), _decimal(expected)
    except Exception:
        actual_value, expected_value = actual, expected
    if operator == "gt":
        return actual_value > expected_value
    if operator == "gte":
        return actual_value >= expected_value
    if operator == "lt":
        return actual_value < expected_value
    return actual_value <= expected_value


def _metric_values(db: Session, user_id: uuid.UUID) -> dict[str, Decimal]:
    return {row.metric_key: Decimal(row.value) for row in db.scalars(select(AchievementMetric).where(AchievementMetric.user_id == user_id))}


def evaluate_criteria(criteria: dict[str, Any], *, metrics: dict[str, Any], event: dict[str, Any] | None = None) -> bool:
    if not criteria:
        return False
    if "all" in criteria:
        return all(evaluate_criteria(item, metrics=metrics, event=event) for item in criteria["all"])
    if "any" in criteria:
        return any(evaluate_criteria(item, metrics=metrics, event=event) for item in criteria["any"])
    if "not" in criteria:
        return not evaluate_criteria(criteria["not"], metrics=metrics, event=event)
    operator = criteria.get("op", "gte")
    expected = criteria.get("value")
    if "metric" in criteria:
        actual = metrics.get(criteria["metric"], Decimal("0"))
    elif "event" in criteria:
        actual = _field(event or {}, criteria["event"])
    else:
        raise ValueError("Achievement criteria must contain metric, event, all, any, or not")
    return _compare(actual, operator, expected)


def _criteria_for_tier(definition: AchievementDefinition, tier: AchievementTier) -> dict[str, Any]:
    if tier.criteria:
        return tier.criteria
    criteria = dict(definition.criteria or {})
    if tier.threshold is not None:
        criteria["value"] = str(tier.threshold)
    return criteria


def _progress(criteria: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    if "metric" not in criteria or criteria.get("op", "gte") not in {"gte", "gt"} or "value" not in criteria:
        return {}
    current = _decimal(metrics.get(criteria["metric"], 0))
    target = _decimal(criteria["value"])
    percent = Decimal("100") if target <= 0 else min(Decimal("100"), current * Decimal("100") / target)
    return {"metric": criteria["metric"], "current": str(current), "target": str(target), "percent": float(round(percent, 2))}


def set_achievement_metric(db: Session, user_id: uuid.UUID, metric_key: str, value: Decimal | int | float | str, *, metadata: dict[str, Any] | None = None) -> AchievementMetric:
    row = db.get(AchievementMetric, (user_id, metric_key))
    if row is None:
        row = AchievementMetric(user_id=user_id, metric_key=metric_key, value=_decimal(value), metadata_json=metadata or {})
        db.add(row)
    else:
        row.value = _decimal(value)
        if metadata is not None:
            row.metadata_json = metadata
        row.updated_at = _now()
    db.flush()
    return row


def increment_achievement_metric(db: Session, user_id: uuid.UUID, metric_key: str, delta: Decimal | int | float | str = 1) -> AchievementMetric:
    row = db.get(AchievementMetric, (user_id, metric_key))
    if row is None:
        return set_achievement_metric(db, user_id, metric_key, _decimal(delta))
    row.value = Decimal(row.value) + _decimal(delta)
    row.updated_at = _now()
    db.flush()
    return row


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _definition_active(definition: AchievementDefinition, now: datetime) -> bool:
    starts_at = _aware(definition.starts_at)
    ends_at = _aware(definition.ends_at)
    return definition.enabled and (starts_at is None or starts_at <= now) and (ends_at is None or ends_at >= now)


def _award_key(user_id: uuid.UUID, definition: AchievementDefinition, tier: AchievementTier | None, instance_key: str | None) -> str:
    prefix = f"achievement:{user_id}:{definition.id}"
    if definition.repeatable or definition.achievement_type == "REPEATABLE":
        if not instance_key:
            raise ValueError("Repeatable achievements require an instance_key")
        return f"{prefix}:instance:{instance_key}"
    if tier is not None:
        return f"{prefix}:tier:{tier.id}"
    return prefix


def _award(db: Session, *, user_id: uuid.UUID, definition: AchievementDefinition, tier: AchievementTier | None, instance_key: str | None, source_event_key: str | None, period_key: str | None, scope_type: str | None, scope_key: str | None, metadata: dict[str, Any] | None) -> UserAchievementAward | None:
    key = _award_key(user_id, definition, tier, instance_key)
    existing = db.scalar(select(UserAchievementAward).where(UserAchievementAward.award_key == key))
    if existing is not None:
        return None
    now = _now()
    award = UserAchievementAward(award_key=key, user_id=user_id, achievement_id=definition.id, tier_id=tier.id if tier else None, source_event_key=source_event_key, period_key=period_key, scope_type=scope_type, scope_key=scope_key, metadata_json=metadata or {}, earned_at=now)
    db.add(award)
    state = db.get(UserAchievementState, (user_id, definition.id))
    if state is None:
        state = UserAchievementState(user_id=user_id, achievement_id=definition.id)
        db.add(state)
    state.earned_count += 1
    state.first_earned_at = state.first_earned_at or now
    state.last_earned_at = now
    state.revoked_at = None
    state.revoke_reason = None
    if tier is not None:
        state.current_tier_id = tier.id
    state.updated_at = now
    db.flush()
    return award


def evaluate_user_achievements(db: Session, user_id: uuid.UUID, *, event: dict[str, Any] | None = None, source_event_key: str | None = None, instance_key: str | None = None, period_key: str | None = None, scope_type: str | None = None, scope_key: str | None = None, metadata: dict[str, Any] | None = None) -> list[UserAchievementAward]:
    now = _now()
    metrics = _metric_values(db, user_id)
    definitions = list(db.scalars(select(AchievementDefinition).where(AchievementDefinition.enabled.is_(True)).order_by(AchievementDefinition.sort_order, AchievementDefinition.key)))
    awards: list[UserAchievementAward] = []
    for definition in definitions:
        if not _definition_active(definition, now):
            continue
        state = db.get(UserAchievementState, (user_id, definition.id))
        if state is None:
            state = UserAchievementState(user_id=user_id, achievement_id=definition.id)
            db.add(state)
            db.flush()
        if definition.achievement_type == "TIERED":
            tiers = list(db.scalars(select(AchievementTier).where(AchievementTier.achievement_id == definition.id).order_by(AchievementTier.sort_order)))
            eligible = [tier for tier in tiers if evaluate_criteria(_criteria_for_tier(definition, tier), metrics=metrics, event=event)]
            target = eligible[-1] if eligible else None
            next_tier = next((tier for tier in tiers if target is None or tier.sort_order > target.sort_order), None)
            progress_criteria = _criteria_for_tier(definition, next_tier or target) if (next_tier or target) else definition.criteria
            state.progress = _progress(progress_criteria or {}, metrics)
            if target is None:
                continue
            current = db.get(AchievementTier, state.current_tier_id) if state.current_tier_id else None
            if current is not None and current.sort_order >= target.sort_order:
                continue
            award = _award(db, user_id=user_id, definition=definition, tier=target, instance_key=None, source_event_key=source_event_key, period_key=period_key, scope_type=scope_type, scope_key=scope_key, metadata=metadata)
        else:
            state.progress = _progress(definition.criteria or {}, metrics)
            if not evaluate_criteria(definition.criteria or {}, metrics=metrics, event=event):
                continue
            award = _award(db, user_id=user_id, definition=definition, tier=None, instance_key=instance_key or source_event_key, source_event_key=source_event_key, period_key=period_key, scope_type=scope_type, scope_key=scope_key, metadata=metadata)
        if award is not None:
            awards.append(award)
    db.flush()
    return awards


def process_achievement_event(db: Session, *, event_key: str, user_id: uuid.UUID, event_type: str, payload: dict[str, Any] | None = None, occurred_at: datetime | None = None, metric_increments: dict[str, Any] | None = None, metric_sets: dict[str, Any] | None = None, instance_key: str | None = None, period_key: str | None = None, scope_type: str | None = None, scope_key: str | None = None) -> list[UserAchievementAward]:
    if db.get(AchievementEventReceipt, event_key) is not None:
        return []
    event_payload = payload or {}
    receipt = AchievementEventReceipt(event_key=event_key, user_id=user_id, event_type=event_type, occurred_at=occurred_at or _now(), payload=event_payload)
    db.add(receipt)
    db.flush()
    for key, value in (metric_increments or {}).items():
        increment_achievement_metric(db, user_id, key, value)
    for key, value in (metric_sets or {}).items():
        set_achievement_metric(db, user_id, key, value)
    return evaluate_user_achievements(db, user_id, event={"type": event_type, "payload": event_payload, "occurred_at": receipt.occurred_at.isoformat()}, source_event_key=event_key, instance_key=instance_key or event_key, period_key=period_key, scope_type=scope_type, scope_key=scope_key, metadata={"event_type": event_type})


def revoke_user_achievement(db: Session, *, user_id: uuid.UUID, achievement_id: uuid.UUID, reason: str, admin_user_id: uuid.UUID | None = None) -> int:
    now = _now()
    awards = list(db.scalars(select(UserAchievementAward).where(UserAchievementAward.user_id == user_id, UserAchievementAward.achievement_id == achievement_id, UserAchievementAward.revoked_at.is_(None))))
    for award in awards:
        award.revoked_at = now
        award.revoke_reason = reason
        award.revoked_by_admin_id = admin_user_id
    state = db.get(UserAchievementState, (user_id, achievement_id))
    if state is not None:
        state.revoked_at = now
        state.revoke_reason = reason
        state.current_tier_id = None
        state.updated_at = now
    db.flush()
    return len(awards)


class TierInput(BaseModel):
    key: str = Field(min_length=1, max_length=48)
    name: str = Field(min_length=1, max_length=96)
    threshold: Decimal | None = Field(default=None, ge=0)
    criteria: dict[str, Any] | None = None
    sort_order: int = Field(ge=0)
    icon: str | None = Field(default=None, max_length=255)


class AchievementInput(BaseModel):
    key: str = Field(min_length=1, max_length=96, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    category: str = Field(min_length=1, max_length=48)
    icon: str | None = Field(default=None, max_length=255)
    achievement_type: Literal["SINGLE", "TIERED", "REPEATABLE", "STATUS"] = "SINGLE"
    visibility: Literal["PUBLIC", "HIDDEN", "SECRET"] = "PUBLIC"
    repeatable: bool = False
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0)
    criteria: dict[str, Any]
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    tiers: list[TierInput] = Field(default_factory=list)


class AchievementPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    category: str | None = Field(default=None, min_length=1, max_length=48)
    icon: str | None = Field(default=None, max_length=255)
    visibility: Literal["PUBLIC", "HIDDEN", "SECRET"] | None = None
    enabled: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)
    criteria: dict[str, Any] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class RevokeInput(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


achievement_router = APIRouter(prefix="/api/v1")


def _definition_payload(definition: AchievementDefinition, db: Session) -> dict[str, Any]:
    tiers = list(db.scalars(select(AchievementTier).where(AchievementTier.achievement_id == definition.id).order_by(AchievementTier.sort_order)))
    return {"id": str(definition.id), "key": definition.key, "name": definition.name, "description": definition.description, "category": definition.category, "icon": definition.icon, "achievement_type": definition.achievement_type, "visibility": definition.visibility, "repeatable": definition.repeatable, "enabled": definition.enabled, "sort_order": definition.sort_order, "criteria": definition.criteria, "starts_at": definition.starts_at, "ends_at": definition.ends_at, "tiers": [{"id": str(tier.id), "key": tier.key, "name": tier.name, "threshold": tier.threshold, "criteria": tier.criteria, "sort_order": tier.sort_order, "icon": tier.icon} for tier in tiers]}


def _user_payload(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    states = list(db.scalars(select(UserAchievementState).where(UserAchievementState.user_id == user_id)))
    definitions = {row.id: row for row in db.scalars(select(AchievementDefinition))}
    return [{"achievement": _definition_payload(definitions[state.achievement_id], db), "current_tier_id": str(state.current_tier_id) if state.current_tier_id else None, "progress": state.progress, "earned_count": state.earned_count, "first_earned_at": state.first_earned_at, "last_earned_at": state.last_earned_at, "revoked_at": state.revoked_at, "revoke_reason": state.revoke_reason} for state in states if state.achievement_id in definitions]


@achievement_router.get("/achievements/me")
def my_achievements(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return _user_payload(db, principal.profile.id)


@achievement_router.get("/admin/achievements")
def admin_achievements(_: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    definitions = list(db.scalars(select(AchievementDefinition).order_by(AchievementDefinition.category, AchievementDefinition.sort_order, AchievementDefinition.key)))
    return [_definition_payload(definition, db) for definition in definitions]


@achievement_router.post("/admin/achievements", status_code=201)
def create_achievement(payload: AchievementInput, _: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    if db.scalar(select(AchievementDefinition.id).where(AchievementDefinition.key == payload.key)) is not None:
        raise HTTPException(409, "Achievement key already exists")
    if payload.achievement_type == "TIERED" and not payload.tiers:
        raise HTTPException(422, "Tiered achievements require at least one tier")
    definition = AchievementDefinition(**payload.model_dump(exclude={"tiers"}))
    db.add(definition)
    db.flush()
    for tier in payload.tiers:
        db.add(AchievementTier(achievement_id=definition.id, **tier.model_dump()))
    db.commit()
    db.refresh(definition)
    return _definition_payload(definition, db)


@achievement_router.patch("/admin/achievements/{achievement_id}")
def update_achievement(achievement_id: uuid.UUID, payload: AchievementPatch, _: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    definition = db.get(AchievementDefinition, achievement_id)
    if definition is None:
        raise HTTPException(404, "Achievement not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(definition, key, value)
    definition.updated_at = _now()
    db.commit()
    db.refresh(definition)
    return _definition_payload(definition, db)


@achievement_router.get("/admin/users/{user_id}/achievements")
def admin_user_achievements(user_id: uuid.UUID, _: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    if db.get(Profile, user_id) is None:
        raise HTTPException(404, "User not found")
    return _user_payload(db, user_id)


@achievement_router.post("/admin/users/{user_id}/achievements/{achievement_id}/revoke")
def admin_revoke_achievement(user_id: uuid.UUID, achievement_id: uuid.UUID, payload: RevokeInput, principal: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    if db.get(Profile, user_id) is None or db.get(AchievementDefinition, achievement_id) is None:
        raise HTTPException(404, "User or achievement not found")
    count = revoke_user_achievement(db, user_id=user_id, achievement_id=achievement_id, reason=payload.reason, admin_user_id=principal.profile.id)
    db.commit()
    return {"revoked_awards": count}
