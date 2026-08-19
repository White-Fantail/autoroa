from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .contribution_rewards import SubmissionFuelResult
from .db import get_db
from .models import CurrentPrice, Station
from .user_price_boards import CommunityPriceBoardSubmission

public_station_router = APIRouter(prefix="/api/v1")


def _alias(user_id) -> str:
    return f"Driver {str(user_id).replace('-', '')[:6].upper()}"


@public_station_router.get("/fuel-stations/snapshot")
def fuel_station_snapshot(db: Session = Depends(get_db)):
    """Return active geocoded stations, current prices and privacy-safe attribution."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    stations = list(
        db.scalars(
            select(Station).where(
                Station.is_active.is_(True),
                Station.latitude.is_not(None),
                Station.longitude.is_not(None),
            )
        )
    )
    station_ids = [station.id for station in stations]
    prices = (
        list(
            db.scalars(
                select(CurrentPrice).where(
                    CurrentPrice.station_id.in_(station_ids),
                    CurrentPrice.observed_at >= cutoff,
                )
            )
        )
        if station_ids
        else []
    )
    observation_ids = [price.observation_id for price in prices]
    attribution_rows = (
        list(
            db.execute(
                select(SubmissionFuelResult.observation_id, CommunityPriceBoardSubmission.user_id)
                .join(CommunityPriceBoardSubmission, CommunityPriceBoardSubmission.id == SubmissionFuelResult.submission_id)
                .where(SubmissionFuelResult.observation_id.in_(observation_ids), SubmissionFuelResult.result == "APPLIED")
            ).all()
        )
        if observation_ids
        else []
    )
    attribution = {observation_id: _alias(user_id) for observation_id, user_id in attribution_rows}
    by_station = {station.id: {"prices": {}, "observed_at": {}, "contributors": {}} for station in stations}
    for price in prices:
        entry = by_station.get(price.station_id)
        if entry is None:
            continue
        key = price.fuel_type.value
        entry["prices"][key] = price.price
        entry["observed_at"][key] = price.observed_at
        contributor = attribution.get(price.observation_id)
        if contributor:
            entry["contributors"][key] = contributor

    return {
        "stations": [
            {
                "id": station.id,
                "name": station.name,
                "address": station.address_line,
                "city": station.city,
                "latitude": station.latitude,
                "longitude": station.longitude,
                "prices": by_station[station.id]["prices"],
                "observed_at": by_station[station.id]["observed_at"],
                "contributors": by_station[station.id]["contributors"],
            }
            for station in stations
        ],
        "station_count": len(stations),
        "priced_station_count": sum(1 for station in stations if by_station[station.id]["prices"]),
        "generated_at": datetime.now(timezone.utc),
    }
