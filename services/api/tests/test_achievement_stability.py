import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.achievement_stability import (
    AchievementCriteriaError,
    _competition_rows,
    revoke_single_award,
    stable_finalize_monthly_scope,
    validate_criteria,
)
from app.achievements import (
    AchievementDefinition,
    UserAchievementAward,
    UserAchievementState,
)
from app.db import Base
from app.models import Profile


def make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def make_user(db: Session, auth_id: str) -> Profile:
    user = Profile(auth_user_id=auth_id, display_name=auth_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_criteria_validation_rejects_unknown_operator():
    with pytest.raises(AchievementCriteriaError):
        validate_criteria(
            {"metric": "prices_confirmed", "op": "greater", "value": 10}
        )


def test_competition_ranking_gives_equal_points_equal_rank():
    first = uuid.uuid4()
    second = uuid.uuid4()
    third = uuid.uuid4()
    rows = [(first, 20), (second, 20), (third, 10)]
    ranked = _competition_rows(rows)
    assert [row[0] for row in ranked] == [1, 1, 3]


def test_new_user_achievement_state_has_safe_python_defaults():
    state = UserAchievementState(
        user_id=uuid.uuid4(), achievement_id=uuid.uuid4()
    )
    assert state.earned_count == 0
    assert state.progress == {}


def test_single_award_revoke_preserves_other_repeatable_awards():
    engine = make_db()
    with Session(engine) as db:
        user = make_user(db, "repeatable-user")
        badge = AchievementDefinition(
            key="regional-test",
            name="Regional test",
            description="Repeated regional trophy",
            category="REGIONAL",
            achievement_type="REPEATABLE",
            repeatable=True,
            criteria={"event": "payload.rank", "op": "eq", "value": 1},
        )
        db.add(badge)
        db.flush()
        state = UserAchievementState(
            user_id=user.id,
            achievement_id=badge.id,
            earned_count=2,
            progress={},
        )
        first = UserAchievementAward(
            award_key="regional:first",
            user_id=user.id,
            achievement_id=badge.id,
            period_key="2026-07",
            scope_type="CITY",
            scope_key="christchurch",
            earned_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        second = UserAchievementAward(
            award_key="regional:second",
            user_id=user.id,
            achievement_id=badge.id,
            period_key="2026-08",
            scope_type="CITY",
            scope_key="christchurch",
            earned_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        db.add_all([state, first, second])
        db.commit()

        revoke_single_award(
            db,
            award_id=first.id,
            reason="Invalid July result",
            admin_user_id=None,
        )
        db.commit()

        db.refresh(first)
        db.refresh(second)
        db.refresh(state)
        assert first.revoked_at is not None
        assert second.revoked_at is None
        assert state.revoked_at is None
        assert state.earned_count == 1
    engine.dispose()


def test_current_month_cannot_be_finalized():
    engine = make_db()
    with Session(engine) as db:
        now = datetime.now(timezone.utc)
        period = now.strftime("%Y-%m")
        with pytest.raises(Exception) as caught:
            stable_finalize_monthly_scope(
                db,
                period_key=period,
                scope_type="NATIONAL",
                scope_key="nz",
            )
        assert getattr(caught.value, "status_code", None) == 409
    engine.dispose()
