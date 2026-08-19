from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

from sqlalchemy import select

from app import community_price_boards
from app.contribution_rewards import PointTransaction, SubmissionFuelResult
from app.models import FuelType, MediaAsset, MediaType, OCRJob, OCRJobKind, Observation, Profile, Source, Station, Verification
from app.services import resolve_current_price
from app.user_price_boards import CommunityPriceBoardSubmission


def setup_contribution(db, *, previous_price: Decimal | None = None, previous_time=None):
    now = datetime.now(timezone.utc)
    profile = Profile(auth_user_id=f"reward-user-{uuid.uuid4()}")
    station = Station(
        name="Reward Test Station",
        address_line="1 Test Road",
        city="Christchurch",
        region="Canterbury",
        latitude=Decimal("-43.532000"),
        longitude=Decimal("172.636000"),
    )
    db.add_all([profile, station]); db.flush()
    if previous_price is not None:
        prior = Observation(
            station_id=station.id,
            fuel_type=FuelType.PETROL_91,
            pump_price_per_litre=previous_price,
            source=Source.ADMIN,
            verification_level=Verification.USER_CONFIRMED,
            observed_at=previous_time or now - timedelta(hours=1),
            confidence_score=Decimal("1"),
            is_anomaly=False,
        )
        db.add(prior); db.flush(); resolve_current_price(db, station.id, FuelType.PETROL_91); db.flush()
    media = MediaAsset(
        user_id=None,
        type=MediaType.OTHER,
        storage_bucket="local-private-media",
        storage_path=f"reward/{uuid.uuid4()}.jpg",
        mime_type="image/jpeg",
        file_size=100,
        content_sha256="a" * 64,
    )
    db.add(media); db.flush()
    job = OCRJob(
        user_id=None,
        kind=OCRJobKind.PRICE_BOARD,
        resource_id=media.id,
        station_id=station.id,
        media_asset_id=media.id,
        requires_confirmation=False,
    )
    db.add(job); db.flush()
    submission = CommunityPriceBoardSubmission(
        user_id=profile.id,
        ocr_job_id=job.id,
        selected_station_id=station.id,
        location_status="available",
        content_sha256="a" * 64,
    )
    db.add(submission); db.flush()
    return profile, station, job, submission, now


def apply_price(db, job, station, price, observed_at):
    return community_price_boards._apply_job_prices(
        db,
        job=job,
        station=station,
        source=Source.COMMUNITY,
        verification=Verification.USER_CONFIRMED,
        prices=[{"fuel_type": FuelType.PETROL_91, "price": price, "confidence": Decimal("1")}],
        observed_at=observed_at,
    )


def test_first_accepted_changed_price_awards_one_point(db):
    profile, station, job, submission, now = setup_contribution(db, previous_price=Decimal("2.5000"))
    apply_price(db, job, station, Decimal("2.4000"), now)
    result = db.scalar(select(SubmissionFuelResult).where(SubmissionFuelResult.submission_id == submission.id))
    tx = db.scalar(select(PointTransaction).where(PointTransaction.submission_id == submission.id))
    assert result and result.result == "APPLIED" and result.points == 1
    assert result.previous_price == Decimal("2.5000") and result.final_price == Decimal("2.4000")
    assert tx and tx.user_id == profile.id and tx.station_id == station.id and tx.points == 1


def test_same_known_price_records_no_change_without_points(db):
    _, station, job, submission, now = setup_contribution(db, previous_price=Decimal("2.5000"))
    apply_price(db, job, station, Decimal("2.5000"), now)
    result = db.scalar(select(SubmissionFuelResult).where(SubmissionFuelResult.submission_id == submission.id))
    assert result and result.result == "NO_CHANGE" and result.points == 0
    assert db.scalar(select(PointTransaction.id).where(PointTransaction.submission_id == submission.id)) is None


def test_older_changed_price_is_stale_and_cannot_replace_current(db):
    current_time = datetime.now(timezone.utc)
    _, station, job, submission, _ = setup_contribution(
        db, previous_price=Decimal("2.5000"), previous_time=current_time
    )
    observations = apply_price(db, job, station, Decimal("2.3000"), current_time - timedelta(hours=2))
    result = db.scalar(select(SubmissionFuelResult).where(SubmissionFuelResult.submission_id == submission.id))
    current = resolve_current_price(db, station.id, FuelType.PETROL_91)
    assert observations == []
    assert result and result.result == "STALE" and result.points == 0
    assert current and current.price == Decimal("2.5000")
    assert db.scalar(select(PointTransaction.id).where(PointTransaction.submission_id == submission.id)) is None


def test_reward_processing_is_idempotent(db):
    _, station, job, submission, now = setup_contribution(db, previous_price=Decimal("2.5000"))
    apply_price(db, job, station, Decimal("2.4000"), now)
    apply_price(db, job, station, Decimal("2.4000"), now)
    results = list(db.scalars(select(SubmissionFuelResult).where(SubmissionFuelResult.submission_id == submission.id)))
    transactions = list(db.scalars(select(PointTransaction).where(PointTransaction.submission_id == submission.id)))
    assert len(results) == 1
    assert len(transactions) == 1
