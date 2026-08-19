from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.achievement_catalog import CORE_ACHIEVEMENTS, ensure_core_achievement_catalog
from app.achievements import (
    AchievementDefinition,
    AchievementMetric,
    AchievementTier,
    UserAchievementAward,
    process_achievement_event,
)
from app.models import Profile


def _user(db, auth_id="catalog-user"):
    user = Profile(auth_user_id=auth_id, display_name="Catalog Tester")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_core_catalog_is_complete_and_idempotent(db):
    ensure_core_achievement_catalog(db)
    db.commit()
    ensure_core_achievement_catalog(db)
    db.commit()

    definitions = list(db.scalars(select(AchievementDefinition)))
    assert len(definitions) == len(CORE_ACHIEVEMENTS) == 19
    assert {row.category for row in definitions} == {
        "STARTER",
        "CONTRIBUTION",
        "EXPLORATION",
        "SPECIAL",
    }

    price_spotter = db.scalar(
        select(AchievementDefinition).where(AchievementDefinition.key == "price_spotter")
    )
    assert price_spotter is not None and price_spotter.achievement_type == "TIERED"
    tiers = list(
        db.scalars(
            select(AchievementTier)
            .where(AchievementTier.achievement_id == price_spotter.id)
            .order_by(AchievementTier.sort_order)
        )
    )
    assert [int(tier.threshold) for tier in tiers] == [25, 100, 500, 1500, 5000]

    mystery = db.scalar(
        select(AchievementDefinition).where(AchievementDefinition.key == "mystery_scout")
    )
    assert mystery is not None and mystery.visibility == "SECRET"


def test_starter_exploration_and_special_badges_evaluate_from_one_event(db):
    user = _user(db)
    ensure_core_achievement_catalog(db)
    db.commit()

    awards = process_achievement_event(
        db,
        event_key="contribution-applied:catalog-1",
        user_id=user.id,
        event_type="CONTRIBUTION_APPLIED",
        payload={
            "local_hour": 6,
            "unique_stations_today": 5,
            "road_trip_qualified": True,
            "days_since_previous": 45,
        },
        occurred_at=datetime.now(timezone.utc),
        metric_sets={
            "approved_contributions": 10,
            "prices_confirmed": 25,
            "photos_approved": 10,
            "unique_stations_contributed": 10,
            "unique_regions_contributed": 3,
            "active_days_last_7": 5,
        },
    )
    db.commit()

    award_keys = {
        db.get(AchievementDefinition, award.achievement_id).key
        for award in awards
    }
    assert {
        "first_spot",
        "first_snap",
        "getting_started",
        "on_the_road",
        "double_digits",
        "price_spotter",
        "station_contributor",
        "photographer",
        "explorer",
        "regional_explorer",
        "early_bird",
        "road_trip",
        "on_fire",
        "comeback",
        "mystery_scout",
    }.issubset(award_keys)
    assert "night_owl" not in award_keys

    assert db.get(AchievementMetric, (user.id, "prices_confirmed")).value == Decimal("25")
    assert db.query(UserAchievementAward).count() == len(awards)


def test_night_owl_does_not_reaward_single_metric_badges(db):
    user = _user(db, "night-user")
    ensure_core_achievement_catalog(db)
    db.commit()

    first = process_achievement_event(
        db,
        event_key="contribution-applied:night-1",
        user_id=user.id,
        event_type="CONTRIBUTION_APPLIED",
        payload={"local_hour": 23, "unique_stations_today": 1, "road_trip_qualified": False},
        metric_sets={
            "approved_contributions": 1,
            "prices_confirmed": 1,
            "photos_approved": 1,
            "unique_stations_contributed": 1,
            "unique_regions_contributed": 1,
            "active_days_last_7": 1,
        },
    )
    second = process_achievement_event(
        db,
        event_key="contribution-applied:night-2",
        user_id=user.id,
        event_type="CONTRIBUTION_APPLIED",
        payload={"local_hour": 23, "unique_stations_today": 1, "road_trip_qualified": False},
        metric_sets={
            "approved_contributions": 2,
            "prices_confirmed": 2,
            "photos_approved": 2,
            "unique_stations_contributed": 1,
            "unique_regions_contributed": 1,
            "active_days_last_7": 1,
        },
    )
    db.commit()

    first_keys = {db.get(AchievementDefinition, row.achievement_id).key for row in first}
    second_keys = {db.get(AchievementDefinition, row.achievement_id).key for row in second}
    assert "night_owl" in first_keys
    assert "night_owl" not in second_keys
    assert "first_spot" in first_keys
    assert "first_spot" not in second_keys
