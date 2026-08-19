import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserTrustState(Base):
    __tablename__ = "user_trust_states"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    evaluated_result_count: Mapped[int] = mapped_column(Integer, default=0)
    accurate_result_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_sample_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_accurate_count: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    recent_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    trust_score: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=Decimal("0"))
    moderation_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    is_trusted_contributor: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    auto_review_eligible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint("evaluated_result_count >= 0", name="user_trust_evaluated_nonnegative"),
        CheckConstraint("accurate_result_count >= 0", name="user_trust_accurate_nonnegative"),
        CheckConstraint("recent_sample_count >= 0", name="user_trust_recent_sample_nonnegative"),
        CheckConstraint("recent_accurate_count >= 0", name="user_trust_recent_accurate_nonnegative"),
        CheckConstraint("trust_score between 0 and 100", name="user_trust_score_range"),
        Index("ix_user_trust_state_score", "trust_score"),
    )


ACCURATE_RESULTS = {"APPLIED", "NO_CHANGE"}
EVALUATED_RESULTS = {"APPLIED", "NO_CHANGE", "NOT_APPLIED"}
RECENT_SAMPLE_SIZE = 50
TRUST_MIN_RESULTS = 50
TRUST_MIN_ACCURACY = Decimal("95")


def refresh_user_trust(db: Session, user_id: uuid.UUID, *, moderation_status: str | None = None) -> UserTrustState:
    from .contribution_rewards import SubmissionFuelResult
    from .user_moderation import moderation_status as current_moderation_status
    from .user_price_boards import CommunityPriceBoardSubmission

    rows = list(
        db.scalars(
            select(SubmissionFuelResult)
            .join(
                CommunityPriceBoardSubmission,
                CommunityPriceBoardSubmission.id == SubmissionFuelResult.submission_id,
            )
            .where(
                CommunityPriceBoardSubmission.user_id == user_id,
                SubmissionFuelResult.result.in_(EVALUATED_RESULTS),
            )
            .order_by(SubmissionFuelResult.decided_at.desc(), SubmissionFuelResult.id.desc())
        )
    )
    evaluated = len(rows)
    accurate = sum(1 for row in rows if row.result in ACCURATE_RESULTS)
    recent = rows[:RECENT_SAMPLE_SIZE]
    recent_accurate = sum(1 for row in recent if row.result in ACCURATE_RESULTS)
    lifetime_accuracy = Decimal(accurate * 100) / Decimal(evaluated) if evaluated else None
    recent_accuracy = Decimal(recent_accurate * 100) / Decimal(len(recent)) if recent else None
    status = moderation_status or current_moderation_status(db, user_id)

    # Weight recent correctness more heavily while still rewarding a strong long-term record.
    if recent_accuracy is None:
        score = Decimal("0")
    elif lifetime_accuracy is None:
        score = recent_accuracy
    else:
        score = recent_accuracy * Decimal("0.75") + lifetime_accuracy * Decimal("0.25")
    score = max(Decimal("0"), min(Decimal("100"), score))

    trusted = (
        status == "ACTIVE"
        and evaluated >= TRUST_MIN_RESULTS
        and len(recent) >= RECENT_SAMPLE_SIZE
        and recent_accuracy is not None
        and recent_accuracy >= TRUST_MIN_ACCURACY
    )

    state = db.get(UserTrustState, user_id)
    if state is None:
        state = UserTrustState(user_id=user_id)
        db.add(state)
    state.evaluated_result_count = evaluated
    state.accurate_result_count = accurate
    state.recent_sample_count = len(recent)
    state.recent_accurate_count = recent_accurate
    state.lifetime_accuracy = lifetime_accuracy
    state.recent_accuracy = recent_accuracy
    state.trust_score = score
    state.moderation_status = status
    state.is_trusted_contributor = trusted
    # Expose future review eligibility without changing the current review policy yet.
    state.auto_review_eligible = trusted
    state.last_evaluated_at = _now()
    state.updated_at = state.last_evaluated_at
    db.flush()
    return state


def trust_payload(state: UserTrustState | None) -> dict:
    if state is None:
        return {
            "trust_score": 0.0,
            "evaluated_result_count": 0,
            "recent_sample_count": 0,
            "recent_accuracy": None,
            "lifetime_accuracy": None,
            "is_trusted_contributor": False,
            "auto_review_eligible": False,
        }
    return {
        "trust_score": float(state.trust_score),
        "evaluated_result_count": state.evaluated_result_count,
        "recent_sample_count": state.recent_sample_count,
        "recent_accuracy": float(state.recent_accuracy) if state.recent_accuracy is not None else None,
        "lifetime_accuracy": float(state.lifetime_accuracy) if state.lifetime_accuracy is not None else None,
        "is_trusted_contributor": state.is_trusted_contributor,
        "auto_review_eligible": state.auto_review_eligible,
    }
