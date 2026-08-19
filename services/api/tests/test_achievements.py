from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Profile
from app.achievements import (
    AchievementDefinition,
    AchievementMetric,
    AchievementTier,
    UserAchievementAward,
    UserAchievementState,
    evaluate_user_achievements,
    process_achievement_event,
    set_achievement_metric,
)


def make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def make_user(db: Session, auth_id: str = "achievement-user") -> Profile:
    user = Profile(auth_user_id=auth_id, display_name="Badge Tester")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_event_processing_is_idempotent_and_awards_single_achievement_once():
    engine = make_db()
    with Session(engine) as db:
        user = make_user(db)
        badge = AchievementDefinition(
            key="first-spot",
            name="First Spot",
            description="First confirmed price.",
            category="STARTER",
            criteria={"metric": "prices_confirmed", "op": "gte", "value": 1},
        )
        db.add(badge)
        db.commit()

        first = process_achievement_event(
            db,
            event_key="price:1",
            user_id=user.id,
            event_type="price_confirmed",
            metric_increments={"prices_confirmed": 1},
        )
        db.commit()
        second = process_achievement_event(
            db,
            event_key="price:1",
            user_id=user.id,
            event_type="price_confirmed",
            metric_increments={"prices_confirmed": 1},
        )
        db.commit()

        assert len(first) == 1
        assert second == []
        assert db.get(AchievementMetric, (user.id, "prices_confirmed")).value == Decimal("1")
        assert db.query(UserAchievementAward).count() == 1
        state = db.get(UserAchievementState, (user.id, badge.id))
        assert state is not None and state.earned_count == 1
    engine.dispose()


def test_tiered_achievement_keeps_highest_tier_and_next_progress():
    engine = make_db()
    with Session(engine) as db:
        user = make_user(db)
        badge = AchievementDefinition(
            key="price-spotter",
            name="Price Spotter",
            description="Confirm fuel prices.",
            category="CONTRIBUTION",
            achievement_type="TIERED",
            criteria={"metric": "prices_confirmed", "op": "gte"},
        )
        db.add(badge)
        db.flush()
        bronze = AchievementTier(achievement_id=badge.id, key="bronze", name="Bronze", threshold=10, sort_order=0)
        silver = AchievementTier(achievement_id=badge.id, key="silver", name="Silver", threshold=50, sort_order=1)
        gold = AchievementTier(achievement_id=badge.id, key="gold", name="Gold", threshold=100, sort_order=2)
        db.add_all([bronze, silver, gold])
        set_achievement_metric(db, user.id, "prices_confirmed", 60)
        db.commit()

        awards = evaluate_user_achievements(db, user.id)
        db.commit()
        state = db.get(UserAchievementState, (user.id, badge.id))
        assert len(awards) == 1
        assert state is not None and state.current_tier_id == silver.id
        assert state.progress["target"] == "100.000000"

        set_achievement_metric(db, user.id, "prices_confirmed", 120)
        awards = evaluate_user_achievements(db, user.id)
        db.commit()
        state = db.get(UserAchievementState, (user.id, badge.id))
        assert len(awards) == 1
        assert state is not None and state.current_tier_id == gold.id
        assert state.earned_count == 2
    engine.dispose()


def test_repeatable_achievement_uses_event_instance_keys():
    engine = make_db()
    with Session(engine) as db:
        user = make_user(db)
        badge = AchievementDefinition(
            key="monthly-champion",
            name="Monthly Champion",
            description="Finish first in a regional leaderboard.",
            category="REGIONAL",
            achievement_type="REPEATABLE",
            repeatable=True,
            criteria={"event": "payload.rank", "op": "eq", "value": 1},
        )
        db.add(badge)
        db.commit()

        august = process_achievement_event(
            db,
            event_key="leaderboard:christchurch:2026-08:final",
            user_id=user.id,
            event_type="leaderboard_finalized",
            payload={"rank": 1},
            period_key="2026-08",
            scope_type="CITY",
            scope_key="christchurch",
        )
        september = process_achievement_event(
            db,
            event_key="leaderboard:christchurch:2026-09:final",
            user_id=user.id,
            event_type="leaderboard_finalized",
            payload={"rank": 1},
            period_key="2026-09",
            scope_type="CITY",
            scope_key="christchurch",
        )
        db.commit()

        assert len(august) == 1 and len(september) == 1
        state = db.get(UserAchievementState, (user.id, badge.id))
        assert state is not None and state.earned_count == 2
        assert db.query(UserAchievementAward).filter(UserAchievementAward.achievement_id == badge.id).count() == 2
    engine.dispose()
