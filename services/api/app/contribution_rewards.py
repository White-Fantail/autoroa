import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base
from .models import CurrentPrice, FuelType, OCRJob, Observation, Station
from .user_price_boards import CommunityPriceBoardSubmission


class SubmissionFuelResult(Base):
    __tablename__ = "submission_fuel_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_price_board_submissions.id", ondelete="CASCADE"), index=True)
    station_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fuel_stations.id"), index=True)
    fuel_type: Mapped[FuelType] = mapped_column(Enum(FuelType))
    previous_price: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    submitted_price: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    final_price: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    result: Mapped[str] = mapped_column(String(24))
    points: Mapped[int] = mapped_column(Integer, default=0)
    observation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fuel_price_observations.id"))
    previous_observation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fuel_price_observations.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("submission_id", "fuel_type", name="uq_submission_fuel_result"),
        CheckConstraint("points in (0, 1)", name="submission_fuel_result_points"),
        Index("ix_submission_fuel_result_station_fuel", "station_id", "fuel_type"),
    )


class PointTransaction(Base):
    __tablename__ = "point_transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_price_board_submissions.id", ondelete="CASCADE"), index=True)
    station_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fuel_stations.id"), index=True)
    fuel_type: Mapped[FuelType] = mapped_column(Enum(FuelType))
    points: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("submission_id", "fuel_type", "reason", name="uq_point_transaction_reason"),
        CheckConstraint("points <> 0", name="point_transaction_nonzero"),
        Index("ix_point_transaction_station_created", "station_id", "created_at"),
        Index("ix_point_transaction_user_created", "user_id", "created_at"),
    )


REWARD_REASON = "FIRST_ACCEPTED_PRICE_UPDATE"


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _entry_values(entry: dict[str, Any]) -> tuple[FuelType, Decimal]:
    fuel_type = entry["fuel_type"]
    if not isinstance(fuel_type, FuelType):
        fuel_type = FuelType(str(fuel_type))
    raw_price = entry["price_per_litre"] if "price_per_litre" in entry else entry["price"]
    return fuel_type, Decimal(str(raw_price))


def _lock_reward_keys(db: Session, station_id: uuid.UUID, fuel_types: list[FuelType]) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    for fuel_type in sorted(fuel_types, key=lambda item: item.value):
        db.execute(
            text("select pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"contribution-reward:{station_id}:{fuel_type.value}"},
        )


def install_contribution_rewards(community_module: Any) -> None:
    """Attach idempotent fuel-level results and point awards to accepted user price boards."""
    original = community_module._apply_job_prices
    if getattr(original, "_contribution_rewards_wrapped", False):
        return

    def rewarded_apply(
        db: Session,
        *,
        job: OCRJob,
        station: Station,
        source: Any,
        verification: Any,
        prices: list[dict[str, Any]],
        observed_at: datetime,
    ) -> list[Observation]:
        contribution = db.scalar(
            select(CommunityPriceBoardSubmission).where(CommunityPriceBoardSubmission.ocr_job_id == job.id)
        )
        if contribution is None:
            return original(
                db,
                job=job,
                station=station,
                source=source,
                verification=verification,
                prices=prices,
                observed_at=observed_at,
            )

        entries = [_entry_values(entry) for entry in prices]
        _lock_reward_keys(db, station.id, [fuel_type for fuel_type, _ in entries])

        before: dict[FuelType, dict[str, Any]] = {}
        for fuel_type, _ in entries:
            current = db.get(CurrentPrice, (station.id, fuel_type))
            before[fuel_type] = {
                "price": Decimal(current.price) if current is not None else None,
                "observed_at": _aware(current.observed_at) if current is not None else None,
                "observation_id": current.observation_id if current is not None else None,
            }

        stale_fuels = {
            fuel_type
            for fuel_type, price in entries
            if before[fuel_type]["price"] is not None
            and price != before[fuel_type]["price"]
            and before[fuel_type]["observed_at"] is not None
            and _aware(observed_at) is not None
            and _aware(observed_at) < before[fuel_type]["observed_at"]
        }
        applicable_prices = [entry for entry in prices if _entry_values(entry)[0] not in stale_fuels]
        observations = original(
            db,
            job=job,
            station=station,
            source=source,
            verification=verification,
            prices=applicable_prices,
            observed_at=observed_at,
        )
        db.flush()
        observation_by_fuel = {row.fuel_type: row for row in observations}

        for fuel_type, submitted_price in entries:
            existing_result = db.scalar(
                select(SubmissionFuelResult).where(
                    SubmissionFuelResult.submission_id == contribution.id,
                    SubmissionFuelResult.fuel_type == fuel_type,
                )
            )
            if existing_result is not None:
                continue

            previous = before[fuel_type]
            observation = observation_by_fuel.get(fuel_type)
            current = db.get(CurrentPrice, (station.id, fuel_type))
            final_price = Decimal(current.price) if current is not None else None

            if fuel_type in stale_fuels:
                result_name, points = "STALE", 0
            elif previous["price"] is not None and submitted_price == previous["price"]:
                result_name, points = "NO_CHANGE", 0
            elif observation is not None and current is not None and current.observation_id == observation.id:
                result_name, points = "APPLIED", 1
            else:
                result_name, points = "NOT_APPLIED", 0

            db.add(
                SubmissionFuelResult(
                    submission_id=contribution.id,
                    station_id=station.id,
                    fuel_type=fuel_type,
                    previous_price=previous["price"],
                    submitted_price=submitted_price,
                    final_price=final_price,
                    result=result_name,
                    points=points,
                    observation_id=observation.id if observation is not None else None,
                    previous_observation_id=previous["observation_id"],
                )
            )

            if points:
                already_awarded = db.scalar(
                    select(PointTransaction.id).where(
                        PointTransaction.submission_id == contribution.id,
                        PointTransaction.fuel_type == fuel_type,
                        PointTransaction.reason == REWARD_REASON,
                    )
                )
                if already_awarded is None:
                    db.add(
                        PointTransaction(
                            user_id=contribution.user_id,
                            submission_id=contribution.id,
                            station_id=station.id,
                            fuel_type=fuel_type,
                            points=points,
                            reason=REWARD_REASON,
                        )
                    )
        db.flush()
        return observations

    rewarded_apply._contribution_rewards_wrapped = True
    community_module._apply_job_prices = rewarded_apply
