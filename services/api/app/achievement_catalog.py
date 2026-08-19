import math
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .achievements import (
    AchievementDefinition,
    AchievementEventReceipt,
    AchievementTier,
    evaluate_user_achievements,
    process_achievement_event,
    set_achievement_metric,
)
from .models import Station
from .user_price_boards import CommunityPriceBoardSubmission

NZ_TZ = ZoneInfo("Pacific/Auckland")


CORE_ACHIEVEMENTS = [
    {
        "key": "first_spot",
        "name": "First Spot",
        "description": "Get your first fuel price successfully applied.",
        "category": "STARTER",
        "icon": "spot",
        "sort_order": 10,
        "criteria": {"metric": "prices_confirmed", "op": "gte", "value": 1},
    },
    {
        "key": "first_snap",
        "name": "First Snap",
        "description": "Get your first price-board photo successfully applied.",
        "category": "STARTER",
        "icon": "camera",
        "sort_order": 20,
        "criteria": {"metric": "photos_approved", "op": "gte", "value": 1},
    },
    {
        "key": "getting_started",
        "name": "Getting Started",
        "description": "Help confirm 5 fuel prices.",
        "category": "STARTER",
        "icon": "spark",
        "sort_order": 30,
        "criteria": {"metric": "prices_confirmed", "op": "gte", "value": 5},
    },
    {
        "key": "on_the_road",
        "name": "On the Road",
        "description": "Contribute at 3 different stations.",
        "category": "STARTER",
        "icon": "road",
        "sort_order": 40,
        "criteria": {"metric": "unique_stations_contributed", "op": "gte", "value": 3},
    },
    {
        "key": "double_digits",
        "name": "Double Digits",
        "description": "Get 10 price-board submissions successfully applied.",
        "category": "STARTER",
        "icon": "ten",
        "sort_order": 50,
        "criteria": {"metric": "approved_contributions", "op": "gte", "value": 10},
    },
    {
        "key": "price_spotter",
        "name": "Price Spotter",
        "description": "Keep fuel prices fresh for other drivers.",
        "category": "CONTRIBUTION",
        "icon": "price",
        "sort_order": 100,
        "achievement_type": "TIERED",
        "criteria": {"metric": "prices_confirmed", "op": "gte", "value": 0},
        "tiers": [
            ("bronze", "Bronze", 25),
            ("silver", "Silver", 100),
            ("gold", "Gold", 500),
            ("platinum", "Platinum", 1500),
            ("diamond", "Diamond", 5000),
        ],
    },
    {
        "key": "station_contributor",
        "name": "Station Contributor",
        "description": "Help drivers across an increasing number of stations.",
        "category": "CONTRIBUTION",
        "icon": "station",
        "sort_order": 110,
        "achievement_type": "TIERED",
        "criteria": {"metric": "unique_stations_contributed", "op": "gte", "value": 0},
        "tiers": [
            ("bronze", "Bronze", 10),
            ("silver", "Silver", 25),
            ("gold", "Gold", 50),
            ("platinum", "Platinum", 100),
            ("diamond", "Diamond", 250),
        ],
    },
    {
        "key": "photographer",
        "name": "Photographer",
        "description": "Submit useful station price-board photos.",
        "category": "CONTRIBUTION",
        "icon": "camera",
        "sort_order": 120,
        "achievement_type": "TIERED",
        "criteria": {"metric": "photos_approved", "op": "gte", "value": 0},
        "tiers": [
            ("bronze", "Bronze", 10),
            ("silver", "Silver", 50),
            ("gold", "Gold", 200),
            ("platinum", "Platinum", 500),
            ("diamond", "Diamond", 1000),
        ],
    },
    {
        "key": "explorer",
        "name": "Explorer",
        "description": "Contribute at 10 different stations.",
        "category": "EXPLORATION",
        "icon": "compass",
        "sort_order": 200,
        "criteria": {"metric": "unique_stations_contributed", "op": "gte", "value": 10},
    },
    {
        "key": "adventurer",
        "name": "Adventurer",
        "description": "Contribute at 50 different stations.",
        "category": "EXPLORATION",
        "icon": "map",
        "sort_order": 210,
        "criteria": {"metric": "unique_stations_contributed", "op": "gte", "value": 50},
    },
    {
        "key": "road_tripper",
        "name": "Road Tripper",
        "description": "Contribute at 100 different stations.",
        "category": "EXPLORATION",
        "icon": "car",
        "sort_order": 220,
        "criteria": {"metric": "unique_stations_contributed", "op": "gte", "value": 100},
    },
    {
        "key": "regional_explorer",
        "name": "Regional Explorer",
        "description": "Contribute in 3 different regions.",
        "category": "EXPLORATION",
        "icon": "regions",
        "sort_order": 230,
        "criteria": {"metric": "unique_regions_contributed", "op": "gte", "value": 3},
    },
    {
        "key": "nz_explorer",
        "name": "NZ Explorer",
        "description": "Contribute in 10 different New Zealand regions.",
        "category": "EXPLORATION",
        "icon": "nz",
        "sort_order": 240,
        "criteria": {"metric": "unique_regions_contributed", "op": "gte", "value": 10},
    },
    {
        "key": "early_bird",
        "name": "Early Bird",
        "description": "Make a successful contribution before 7am local time.",
        "category": "SPECIAL",
        "icon": "sunrise",
        "sort_order": 300,
        "criteria": {"event": "payload.local_hour", "op": "lt", "value": 7},
    },
    {
        "key": "night_owl",
        "name": "Night Owl",
        "description": "Make a successful contribution at or after 10pm local time.",
        "category": "SPECIAL",
        "icon": "moon",
        "sort_order": 310,
        "criteria": {"event": "payload.local_hour", "op": "gte", "value": 22},
    },
    {
        "key": "road_trip",
        "name": "Road Trip",
        "description": "Contribute at 3 stations in one day with at least 50 km between your furthest stops.",
        "category": "SPECIAL",
        "icon": "route",
        "sort_order": 320,
        "criteria": {"event": "payload.road_trip_qualified", "op": "eq", "value": True},
    },
    {
        "key": "on_fire",
        "name": "On Fire",
        "description": "Make successful contributions on 5 different days within 7 days.",
        "category": "SPECIAL",
        "icon": "fire",
        "sort_order": 330,
        "criteria": {"metric": "active_days_last_7", "op": "gte", "value": 5},
    },
    {
        "key": "comeback",
        "name": "Comeback",
        "description": "Return with a successful contribution after at least 30 days away.",
        "category": "SPECIAL",
        "icon": "return",
        "sort_order": 340,
        "criteria": {"event": "payload.days_since_previous", "op": "gte", "value": 30},
    },
    {
        "key": "mystery_scout",
        "name": "Mystery Scout",
        "description": "A hidden achievement for an unusually active day on the road.",
        "category": "SPECIAL",
        "icon": "secret",
        "sort_order": 350,
        "visibility": "SECRET",
        "criteria": {"event": "payload.unique_stations_today", "op": "gte", "value": 5},
    },
]


def ensure_core_achievement_catalog(db: Session) -> None:
    """Create the built-in badge catalog without overwriting later admin customisation."""
    for item in CORE_ACHIEVEMENTS:
        definition = db.scalar(
            select(AchievementDefinition).where(AchievementDefinition.key == item["key"])
        )
        tiers = item.get("tiers", [])
        if definition is None:
            definition = AchievementDefinition(
                key=item["key"],
                name=item["name"],
                description=item["description"],
                category=item["category"],
                icon=item.get("icon"),
                achievement_type=item.get("achievement_type", "SINGLE"),
                visibility=item.get("visibility", "PUBLIC"),
                repeatable=item.get("repeatable", False),
                enabled=True,
                sort_order=item["sort_order"],
                criteria=item["criteria"],
            )
            db.add(definition)
            db.flush()
        existing_tier_keys = set(
            db.scalars(
                select(AchievementTier.key).where(AchievementTier.achievement_id == definition.id)
            )
        )
        for sort_order, (key, name, threshold) in enumerate(tiers):
            if key in existing_tier_keys:
                continue
            db.add(
                AchievementTier(
                    achievement_id=definition.id,
                    key=key,
                    name=name,
                    threshold=Decimal(threshold),
                    criteria=None,
                    sort_order=sort_order,
                    icon=key,
                )
            )
    db.flush()


def _successful_submission_ids(db: Session, user_id: uuid.UUID):
    from .contribution_rewards import SubmissionFuelResult

    return select(CommunityPriceBoardSubmission.id).join(
        SubmissionFuelResult,
        SubmissionFuelResult.submission_id == CommunityPriceBoardSubmission.id,
    ).where(
        CommunityPriceBoardSubmission.user_id == user_id,
        SubmissionFuelResult.result == "APPLIED",
    ).distinct()


def _authoritative_metrics(db: Session, user_id: uuid.UUID, *, now: datetime) -> dict[str, int]:
    from .contribution_rewards import PointTransaction, SubmissionFuelResult

    approved_contributions = int(
        db.scalar(select(func.count()).select_from(_successful_submission_ids(db, user_id).subquery())) or 0
    )
    prices_confirmed = int(
        db.scalar(
            select(func.count())
            .select_from(SubmissionFuelResult)
            .join(
                CommunityPriceBoardSubmission,
                CommunityPriceBoardSubmission.id == SubmissionFuelResult.submission_id,
            )
            .where(
                CommunityPriceBoardSubmission.user_id == user_id,
                SubmissionFuelResult.result == "APPLIED",
            )
        )
        or 0
    )
    unique_stations = int(
        db.scalar(
            select(func.count(func.distinct(PointTransaction.station_id))).where(
                PointTransaction.user_id == user_id
            )
        )
        or 0
    )
    unique_regions = int(
        db.scalar(
            select(func.count(func.distinct(Station.region)))
            .select_from(PointTransaction)
            .join(Station, Station.id == PointTransaction.station_id)
            .where(PointTransaction.user_id == user_id, Station.region.is_not(None))
        )
        or 0
    )
    cutoff = now.astimezone(NZ_TZ).date() - timedelta(days=6)
    recent_times = list(
        db.scalars(
            select(PointTransaction.created_at).where(
                PointTransaction.user_id == user_id,
                PointTransaction.created_at >= datetime.combine(cutoff, datetime.min.time(), tzinfo=NZ_TZ).astimezone(timezone.utc),
            )
        )
    )
    active_days = len({value.astimezone(NZ_TZ).date() for value in recent_times})
    return {
        "approved_contributions": approved_contributions,
        "prices_confirmed": prices_confirmed,
        "photos_approved": approved_contributions,
        "unique_stations_contributed": unique_stations,
        "unique_regions_contributed": unique_regions,
        "active_days_last_7": active_days,
    }


def _haversine_km(a: Station, b: Station) -> float:
    lat1, lon1 = math.radians(float(a.latitude)), math.radians(float(a.longitude))
    lat2, lon2 = math.radians(float(b.latitude)), math.radians(float(b.longitude))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def _event_context(
    db: Session,
    *,
    user_id: uuid.UUID,
    submission_id: uuid.UUID,
    station: Station,
    observed_at: datetime,
) -> dict:
    from .contribution_rewards import PointTransaction

    local_tz = ZoneInfo(station.timezone or "Pacific/Auckland")
    aware_observed = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc)
    local_observed = aware_observed.astimezone(local_tz)
    local_day_start = datetime.combine(local_observed.date(), datetime.min.time(), tzinfo=local_tz)
    local_day_end = local_day_start + timedelta(days=1)
    transactions = list(
        db.execute(
            select(PointTransaction.created_at, Station)
            .join(Station, Station.id == PointTransaction.station_id)
            .where(
                PointTransaction.user_id == user_id,
                PointTransaction.created_at >= local_day_start.astimezone(timezone.utc),
                PointTransaction.created_at < local_day_end.astimezone(timezone.utc),
            )
        ).all()
    )
    stations_by_id = {row[1].id: row[1] for row in transactions}
    furthest_km = 0.0
    stations = list(stations_by_id.values())
    for index, first in enumerate(stations):
        for second in stations[index + 1 :]:
            furthest_km = max(furthest_km, _haversine_km(first, second))
    previous = db.scalar(
        select(func.max(PointTransaction.created_at)).where(
            PointTransaction.user_id == user_id,
            PointTransaction.submission_id != submission_id,
        )
    )
    days_since_previous = None
    if previous is not None:
        previous_aware = previous if previous.tzinfo else previous.replace(tzinfo=timezone.utc)
        days_since_previous = max(0, (aware_observed - previous_aware).days)
    return {
        "local_hour": local_observed.hour,
        "local_date": local_observed.date().isoformat(),
        "station_id": str(station.id),
        "city": station.city,
        "region": station.region,
        "unique_stations_today": len(stations),
        "furthest_station_distance_km": round(furthest_km, 1),
        "road_trip_qualified": len(stations) >= 3 and furthest_km >= 50,
        "days_since_previous": days_since_previous,
    }


def process_contribution_achievement_update(
    db: Session,
    *,
    user_id: uuid.UUID,
    submission_id: uuid.UUID,
    station: Station,
    observed_at: datetime,
) -> list:
    """Synchronise contribution metrics and evaluate badges after an applied board."""
    metrics = _authoritative_metrics(db, user_id, now=observed_at)
    context = _event_context(
        db,
        user_id=user_id,
        submission_id=submission_id,
        station=station,
        observed_at=observed_at,
    )
    return process_achievement_event(
        db,
        event_key=f"contribution-applied:{submission_id}",
        user_id=user_id,
        event_type="CONTRIBUTION_APPLIED",
        payload=context,
        occurred_at=observed_at,
        metric_sets=metrics,
    )


def bootstrap_existing_contributor_achievements(db: Session) -> int:
    """One-time, idempotent retroactive metrics/awards for contributors that predate badges."""
    from .contribution_rewards import PointTransaction

    user_ids = set(db.scalars(select(CommunityPriceBoardSubmission.user_id).distinct()))
    user_ids.update(db.scalars(select(PointTransaction.user_id).distinct()))
    processed = 0
    now = datetime.now(timezone.utc)
    for user_id in user_ids:
        event_key = f"achievement-core-backfill:{user_id}"
        if db.get(AchievementEventReceipt, event_key) is not None:
            continue
        metrics = _authoritative_metrics(db, user_id, now=now)
        for key, value in metrics.items():
            set_achievement_metric(db, user_id, key, value)
        db.add(
            AchievementEventReceipt(
                event_key=event_key,
                user_id=user_id,
                event_type="ACHIEVEMENT_CORE_BACKFILL",
                occurred_at=now,
                payload={"metric_snapshot": metrics},
            )
        )
        evaluate_user_achievements(db, user_id)
        processed += 1
    db.flush()
    return processed
