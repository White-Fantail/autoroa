from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import CurrentPrice, Station

public_station_router = APIRouter(prefix="/api/v1")


@public_station_router.get("/fuel-stations/snapshot")
def fuel_station_snapshot(db: Session = Depends(get_db)):
    """Return every active, geocoded station plus any recent prices it has.

    Fuel Map contribution flows need stations to remain discoverable even when
    no community price has been recorded yet. Prices older than seven days are
    intentionally omitted while the station itself remains in the response.
    """
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
    by_station = {station.id: {"prices": {}, "observed_at": {}} for station in stations}
    for price in prices:
        entry = by_station.get(price.station_id)
        if entry is None:
            continue
        entry["prices"][price.fuel_type.value] = price.price
        entry["observed_at"][price.fuel_type.value] = price.observed_at

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
            }
            for station in stations
        ],
        "station_count": len(stations),
        "priced_station_count": sum(1 for station in stations if by_station[station.id]["prices"]),
        "generated_at": datetime.now(timezone.utc),
    }
