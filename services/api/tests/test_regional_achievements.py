from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Profile, Station, FuelType
from app.contribution_rewards import PointTransaction
from app.achievements import AchievementDefinition, UserAchievementAward
from app.regional_achievements import (
    LeaderboardPeriodFinalization,
    current_titles,
    ensure_regional_achievement_catalog,
    finalize_monthly_scope,
    trophy_history,
)


def make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def add_user(db: Session, auth_id: str) -> Profile:
    user = Profile(auth_user_id=auth_id, display_name=auth_id)
    db.add(user)
    db.flush()
    return user


def add_station(db: Session, name: str, city: str, region: str) -> Station:
    station = Station(
        name=name,
        address_line=name,
        city=city,
        region=region,
        country_code="NZ",
        latitude=Decimal("-43.53"),
        longitude=Decimal("172.63"),
        timezone="Pacific/Auckland",
    )
    db.add(station)
    db.flush()
    return station


def add_points(db: Session, user: Profile, station: Station, points: int, created_at: datetime):
    for index in range(points):
        db.add(
            PointTransaction(
                user_id=user.id,
                submission_id=__import__("uuid").uuid4(),
                station_id=station.id,
                fuel_type=FuelType.PETROL_91,
                points=1,
                reason=f"test-{index}-{__import__('uuid').uuid4()}",
                created_at=created_at,
            )
        )


def test_catalog_and_monthly_finalization_are_idempotent():
    engine = make_db()
    with Session(engine) as db:
        ensure_regional_achievement_catalog(db)
        ensure_regional_achievement_catalog(db)
        assert db.query(AchievementDefinition).filter(AchievementDefinition.category == "REGIONAL").count() == 3

        station = add_station(db, "City Station", "Christchurch", "Canterbury")
        first = add_user(db, "first")
        second = add_user(db, "second")
        fourth = add_user(db, "fourth")
        when = datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc)
        add_points(db, first, station, 5, when)
        add_points(db, second, station, 4, when)
        add_points(db, fourth, station, 1, when)
        db.commit()

        result = finalize_monthly_scope(db, period_key="2026-08", scope_type="CITY", scope_key="Christchurch")
        db.commit()
        repeat = finalize_monthly_scope(db, period_key="2026-08", scope_type="CITY", scope_key="Christchurch")
        db.commit()

        assert result["status"] == "finalized"
        assert repeat["status"] == "already_finalized"
        assert db.query(LeaderboardPeriodFinalization).count() == 1
        awards = list(db.scalars(select(UserAchievementAward).where(UserAchievementAward.period_key == "2026-08")))
        assert len(awards) == 3
        keys = {
            db.get(AchievementDefinition, award.achievement_id).key
            for award in awards
        }
        assert keys == {"regional_champion", "regional_top_3", "regional_top_10"}
    engine.dispose()


def test_trophy_history_persists_while_current_title_changes():
    engine = make_db()
    with Session(engine) as db:
        ensure_regional_achievement_catalog(db)
        station = add_station(db, "City Station", "Christchurch", "Canterbury")
        user = add_user(db, "champion")
        rival = add_user(db, "rival")
        august = datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)
        add_points(db, user, station, 3, august)
        add_points(db, rival, station, 2, august)
        db.commit()
        finalize_monthly_scope(db, period_key="2026-08", scope_type="CITY", scope_key="Christchurch")
        db.commit()

        history = trophy_history(db, user.id)
        assert len(history) == 1
        assert history[0]["achievement_key"] == "regional_champion"
        assert history[0]["period_key"] == "2026-08"
    engine.dispose()
