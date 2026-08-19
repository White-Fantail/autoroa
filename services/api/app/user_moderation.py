import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import Principal, admin_principal, current_principal
from .contribution_rewards import PointTransaction, SubmissionFuelResult
from .db import Base, get_db
from .models import Profile
from .user_price_boards import (
    CommunityPriceBoardSubmission,
    submit_authenticated_station_price_board,
)

ACTIVE = "ACTIVE"
SUSPENDED = "SUSPENDED"
BANNED = "BANNED"
MODERATION_STATUSES = {ACTIVE, SUSPENDED, BANNED}


class UserModerationState(Base):
    __tablename__ = "user_moderation_states"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), default=ACTIVE)
    reason: Mapped[str | None] = mapped_column(Text)
    moderated_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), index=True
    )
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint(
            "status in ('ACTIVE','SUSPENDED','BANNED')",
            name="user_moderation_state_status_valid",
        ),
        Index("ix_user_moderation_states_status", "status"),
    )


class UserModerationEvent(Base):
    __tablename__ = "user_moderation_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    previous_status: Mapped[str] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        CheckConstraint(
            "previous_status in ('ACTIVE','SUSPENDED','BANNED')",
            name="user_moderation_event_previous_status_valid",
        ),
        CheckConstraint(
            "new_status in ('ACTIVE','SUSPENDED','BANNED')",
            name="user_moderation_event_new_status_valid",
        ),
        Index("ix_user_moderation_events_user_created", "user_id", "created_at"),
    )


class UserModerationUpdate(BaseModel):
    status: Literal["ACTIVE", "SUSPENDED", "BANNED"]
    reason: str | None = Field(default=None, max_length=1000)


moderation_router = APIRouter(prefix="/api/v1")


def moderation_state(db: Session, user_id: uuid.UUID) -> UserModerationState | None:
    return db.get(UserModerationState, user_id)


def moderation_status(db: Session, user_id: uuid.UUID) -> str:
    state = moderation_state(db, user_id)
    return state.status if state is not None else ACTIVE


def contribution_allowed(db: Session, user_id: uuid.UUID) -> bool:
    return moderation_status(db, user_id) == ACTIVE


def _event_payload(event: UserModerationEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "previous_status": event.previous_status,
        "new_status": event.new_status,
        "reason": event.reason,
        "admin_user_id": str(event.admin_user_id) if event.admin_user_id else None,
        "created_at": event.created_at,
    }


def _profile_payload(
    profile: Profile, db: Session, *, include_history: bool = False
) -> dict[str, Any]:
    state = moderation_state(db, profile.id)
    history = (
        list(
            db.scalars(
                select(UserModerationEvent)
                .where(UserModerationEvent.user_id == profile.id)
                .order_by(UserModerationEvent.created_at.desc())
                .limit(30)
            )
        )
        if include_history
        else []
    )
    return {
        "display_name": profile.display_name,
        "moderation_status": state.status if state else ACTIVE,
        "moderation_reason": state.reason if state else None,
        "moderated_at": state.moderated_at if state else None,
        "moderated_by_admin_id": (
            str(state.moderated_by_admin_id)
            if state and state.moderated_by_admin_id
            else None
        ),
        "country_code": profile.country_code,
        "preferred_currency": profile.preferred_currency,
        "preferred_distance_unit": profile.preferred_distance_unit,
        "preferred_efficiency_unit": profile.preferred_efficiency_unit,
        "deleted_at": profile.deleted_at,
        "id": str(profile.id),
        "auth_user_id": profile.auth_user_id,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
        **(
            {"moderation_history": [_event_payload(event) for event in history]}
            if include_history
            else {}
        ),
    }


def _restricted_detail(status: str) -> dict[str, Any]:
    return {
        "code": "ACCOUNT_RESTRICTED",
        "message": (
            "This account cannot submit fuel-price contributions while it is "
            f"{status.lower()}."
        ),
        "status": status,
    }


def install_user_moderation_rewards(community_module: Any) -> None:
    """Prevent restricted users from receiving points from already queued submissions."""
    original = community_module._apply_job_prices
    if getattr(original, "_user_moderation_wrapped", False):
        return

    def moderated_apply(
        db: Session,
        *,
        job: Any,
        station: Any,
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
        if contribution is None or contribution_allowed(db, contribution.user_id):
            return observations

        # Keep the factual application result, but use a distinct status so
        # historical achievement/trust backfills never treat restricted work as
        # an eligible rewarded contribution.
        for result in db.scalars(
            select(SubmissionFuelResult).where(
                SubmissionFuelResult.submission_id == contribution.id
            )
        ):
            result.points = 0
            if result.result == "APPLIED":
                result.result = "APPLIED_RESTRICTED"
        for transaction in db.scalars(
            select(PointTransaction).where(
                PointTransaction.submission_id == contribution.id,
                PointTransaction.points > 0,
            )
        ):
            db.delete(transaction)
        db.flush()
        return observations

    moderated_apply._user_moderation_wrapped = True
    community_module._apply_job_prices = moderated_apply


@moderation_router.get("/admin/users")
def list_users_with_moderation(
    _p: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    users = list(
        db.scalars(
            select(Profile)
            .where(Profile.deleted_at.is_(None))
            .order_by(Profile.created_at.desc())
            .limit(500)
        )
    )
    return [_profile_payload(profile, db) for profile in users]


@moderation_router.get("/admin/users/{user_id}")
def get_user_with_moderation(
    user_id: uuid.UUID,
    _p: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    profile = db.get(Profile, user_id)
    if not profile or profile.deleted_at is not None:
        raise HTTPException(404, "User not found")
    return _profile_payload(profile, db, include_history=True)


@moderation_router.patch("/admin/users/{user_id}/moderation")
def update_user_moderation(
    user_id: uuid.UUID,
    body: UserModerationUpdate,
    p: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    profile = db.get(Profile, user_id)
    if not profile or profile.deleted_at is not None:
        raise HTTPException(404, "User not found")
    if profile.id == p.profile.id:
        raise HTTPException(409, "Administrators cannot restrict their own account")

    reason = (body.reason or "").strip() or None
    if body.status in {SUSPENDED, BANNED} and not reason:
        raise HTTPException(422, "A moderation reason is required")

    state = moderation_state(db, profile.id)
    previous_status = state.status if state else ACTIVE
    now = datetime.now(timezone.utc)
    if state is None:
        state = UserModerationState(user_id=profile.id)
        db.add(state)

    state.status = body.status
    state.reason = reason
    state.moderated_by_admin_id = p.profile.id
    state.moderated_at = now
    state.updated_at = now
    db.add(
        UserModerationEvent(
            user_id=profile.id,
            previous_status=previous_status,
            new_status=body.status,
            reason=reason,
            admin_user_id=p.profile.id,
            created_at=now,
        )
    )
    # Refresh trust immediately so badges/statuses cannot remain stale after an
    # admin restriction or reactivation.
    from .quality_achievements import refresh_quality_achievements

    refresh_quality_achievements(db, user_id=profile.id, moderation_status=body.status)
    db.commit()
    db.refresh(profile)
    return _profile_payload(profile, db, include_history=True)


@moderation_router.post(
    "/fuel-stations/{station_id}/user-price-board-submissions",
    status_code=202,
)
async def submit_moderated_station_price_board(
    station_id: uuid.UUID,
    photo: UploadFile = File(...),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    status = moderation_status(db, p.profile.id)
    if status != ACTIVE and not p.admin:
        raise HTTPException(403, _restricted_detail(status))
    return await submit_authenticated_station_price_board(station_id, photo, p, db)
