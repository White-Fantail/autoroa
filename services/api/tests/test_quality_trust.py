import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.achievements import AchievementDefinition
from app.contribution_rewards import SubmissionFuelResult
from app.db import Base
from app.models import FuelType, Profile
from app.quality_achievements import ensure_quality_achievement_catalog
from app.trust import refresh_user_trust
from app.user_price_boards import CommunityPriceBoardSubmission


def make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def add_result(db: Session, user_id, result: str, index: int):
    submission = CommunityPriceBoardSubmission(
        user_id=user_id,
        ocr_job_id=uuid.uuid4(),
        selected_station_id=uuid.uuid4(),
        detected_station_id=None,
        content_sha256=f"{index:064x}",
    )
    db.add(submission)
    db.flush()
    db.add(
        SubmissionFuelResult(
            submission_id=submission.id,
            station_id=uuid.uuid4(),
            fuel_type=FuelType.PETROL_91,
            previous_price=Decimal("2.50"),
            submitted_price=Decimal("2.60"),
            final_price=Decimal("2.60") if result == "APPLIED" else Decimal("2.50"),
            result=result,
            points=1 if result == "APPLIED" else 0,
            decided_at=datetime.now(timezone.utc),
        )
    )


def test_quality_catalog_is_idempotent():
    engine = make_db()
    with Session(engine) as db:
        ensure_quality_achievement_catalog(db)
        ensure_quality_achievement_catalog(db)
        db.commit()
        keys = set(
            db.scalars(
                select(AchievementDefinition.key).where(
                    AchievementDefinition.category == "QUALITY"
                )
            )
        )
        assert keys == {"fresh_eyes", "rescuer", "full_board", "trusted_contributor"}
    engine.dispose()


def test_trusted_contributor_uses_recent_50_and_excludes_stale():
    engine = make_db()
    with Session(engine) as db:
        user = Profile(auth_user_id="trust-user", display_name="Trust Tester")
        db.add(user)
        db.flush()
        for index in range(48):
            add_result(db, user.id, "APPLIED", index)
        add_result(db, user.id, "NOT_APPLIED", 48)
        add_result(db, user.id, "NOT_APPLIED", 49)
        add_result(db, user.id, "STALE", 50)
        db.flush()

        state = refresh_user_trust(db, user.id, moderation_status="ACTIVE")
        assert state.evaluated_result_count == 50
        assert state.recent_sample_count == 50
        assert state.recent_accurate_count == 48
        assert state.recent_accuracy == Decimal("96")
        assert state.is_trusted_contributor is True
        assert state.auto_review_eligible is True

        state = refresh_user_trust(db, user.id, moderation_status="SUSPENDED")
        assert state.is_trusted_contributor is False
        assert state.auto_review_eligible is False
        assert state.moderation_status == "SUSPENDED"
    engine.dispose()


def test_trusted_contributor_requires_full_sample():
    engine = make_db()
    with Session(engine) as db:
        user = Profile(auth_user_id="trust-small", display_name="Trust Small")
        db.add(user)
        db.flush()
        for index in range(49):
            add_result(db, user.id, "APPLIED", index)
        db.flush()
        state = refresh_user_trust(db, user.id, moderation_status="ACTIVE")
        assert state.recent_accuracy == Decimal("100")
        assert state.is_trusted_contributor is False
    engine.dispose()
