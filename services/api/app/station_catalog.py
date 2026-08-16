import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Iterable

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Principal, admin_principal
from .config import get_settings
from .db import SessionLocal, get_db
from .models import Station

catalog_router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)

# Google Nearby Search returns a bounded result set, so a single nationwide
# request cannot build a reliable station master.  These overlapping cells
# cover the main North and South islands, with smaller overlays for dense
# metros where a coarse cell is more likely to hit the provider result cap.
NZ_MAINLAND_BOUNDS = (
    (-41.75, -34.30, 172.30, 178.70),  # North Island
    (-47.65, -40.15, 166.00, 174.70),  # South Island
)
BASE_LAT_STEP = 0.45
BASE_LNG_STEP = 0.55
BASE_RADIUS_KM = 35.0
DENSE_RADIUS_KM = 8.0
DENSE_LAT_STEP = 0.10
DENSE_LNG_STEP = 0.13
DENSE_AREAS = (
    (-37.20, -36.55, 174.45, 175.15),  # Auckland
    (-37.95, -37.55, 175.00, 175.45),  # Hamilton
    (-38.05, -37.55, 176.00, 176.45),  # Tauranga
    (-41.45, -40.95, 174.55, 175.25),  # Wellington / Hutt / Porirua
    (-43.75, -43.30, 172.30, 172.90),  # Christchurch
    (-46.05, -45.65, 170.20, 170.75),  # Dunedin
)


@dataclass(frozen=True)
class CatalogCell:
    latitude: float
    longitude: float
    radius_km: float
    density: str


def _frange(start: float, stop: float, step: float) -> Iterable[float]:
    value = start
    while value <= stop + 1e-9:
        yield round(value, 6)
        value += step


def _cells_for_bounds(
    south: float,
    north: float,
    west: float,
    east: float,
    *,
    lat_step: float,
    lng_step: float,
    radius_km: float,
    density: str,
) -> Iterable[CatalogCell]:
    for latitude in _frange(south, north, lat_step):
        for longitude in _frange(west, east, lng_step):
            yield CatalogCell(latitude, longitude, radius_km, density)


def nz_catalog_cells() -> list[CatalogCell]:
    cells: list[CatalogCell] = []
    for bounds in NZ_MAINLAND_BOUNDS:
        cells.extend(
            _cells_for_bounds(
                *bounds,
                lat_step=BASE_LAT_STEP,
                lng_step=BASE_LNG_STEP,
                radius_km=BASE_RADIUS_KM,
                density="base",
            )
        )
    for bounds in DENSE_AREAS:
        cells.extend(
            _cells_for_bounds(
                *bounds,
                lat_step=DENSE_LAT_STEP,
                lng_step=DENSE_LNG_STEP,
                radius_km=DENSE_RADIUS_KM,
                density="dense",
            )
        )
    # Dense overlays intentionally overlap the base grid. Exact duplicate
    # centers add no discovery value, so remove them while preserving order.
    unique: dict[tuple[float, float, float], CatalogCell] = {}
    for cell in cells:
        unique.setdefault((cell.latitude, cell.longitude, cell.radius_km), cell)
    return list(unique.values())


class GoogleStationCatalogClient:
    """Small Places API client dedicated to nationwide discovery.

    Place IDs are used as the durable deduplication key. Provider attributes
    are refreshed on subsequent syncs rather than treated as immutable facts.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search_cell(self, cell: CatalogCell) -> list[dict]:
        response = httpx.post(
            "https://places.googleapis.com/v1/places:searchNearby",
            headers={
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": (
                    "places.id,places.displayName,places.formattedAddress,"
                    "places.location,places.addressComponents"
                ),
            },
            json={
                "includedTypes": ["gas_station"],
                "maxResultCount": 20,
                "regionCode": "NZ",
                "locationRestriction": {
                    "circle": {
                        "center": {
                            "latitude": cell.latitude,
                            "longitude": cell.longitude,
                        },
                        "radius": min(cell.radius_km * 1000, 50000),
                    }
                },
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        places = payload.get("places", []) if isinstance(payload, dict) else None
        if not isinstance(places, list):
            raise ValueError("Invalid Google Places response")
        return places


def _place_values(place: dict):
    place_id = place.get("id")
    name = (place.get("displayName") or {}).get("text")
    location = place.get("location") or {}
    address = place.get("formattedAddress")
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if (
        not place_id
        or not name
        or not address
        or not isinstance(latitude, (int, float))
        or not isinstance(longitude, (int, float))
    ):
        return None
    # Mainland NZ. This matches the existing station importer and deliberately
    # excludes obviously unrelated provider results.
    if not (-48 <= latitude <= -34 and 165 <= longitude <= 179):
        return None
    components = {
        kind: text
        for component in place.get("addressComponents", [])
        for kind in component.get("types", [])
        if (text := component.get("longText"))
    }
    city = components.get("locality") or components.get("postal_town") or "New Zealand"
    region = components.get("administrative_area_level_1")
    return place_id, name, address, latitude, longitude, city, region


def upsert_catalog_place(db: Session, place: dict) -> tuple[Station | None, str]:
    values = _place_values(place)
    if not values:
        return None, "invalid"
    place_id, name, address, latitude, longitude, city, region = values
    item = db.scalar(select(Station).where(Station.google_place_id == place_id))
    incoming = {
        "name": name,
        "address_line": address,
        "city": city,
        "region": region,
        "latitude": Decimal(str(latitude)),
        "longitude": Decimal(str(longitude)),
    }
    if item:
        changed = False
        for field, value in incoming.items():
            if getattr(item, field) != value:
                setattr(item, field, value)
                changed = True
        if not item.is_active:
            item.is_active = True
            changed = True
        return item, "updated" if changed else "existing"
    item = Station(
        google_place_id=place_id,
        country_code="NZ",
        timezone="Pacific/Auckland",
        is_active=True,
        **incoming,
    )
    db.add(item)
    return item, "added"


def sync_catalog_batch(
    db: Session,
    *,
    start_cursor: int = 0,
    max_cells: int = 10,
    search_cell: Callable[[CatalogCell], list[dict]],
) -> dict:
    cells = nz_catalog_cells()
    if start_cursor < 0 or start_cursor > len(cells):
        raise ValueError("Invalid catalog cursor")
    end_cursor = min(len(cells), start_cursor + max_cells)
    stats = {"added": 0, "updated": 0, "existing": 0, "invalid": 0, "provider_results": 0}
    seen_place_ids: set[str] = set()
    saturated_cells = 0
    for cell in cells[start_cursor:end_cursor]:
        places = search_cell(cell)
        stats["provider_results"] += len(places)
        if len(places) >= 20:
            saturated_cells += 1
        for place in places:
            place_id = place.get("id") if isinstance(place, dict) else None
            if place_id and place_id in seen_place_ids:
                continue
            if place_id:
                seen_place_ids.add(place_id)
            _, status = upsert_catalog_place(db, place)
            stats[status] += 1
    db.commit()
    return {
        **stats,
        "start_cursor": start_cursor,
        "next_cursor": end_cursor,
        "total_cells": len(cells),
        "processed_cells": end_cursor - start_cursor,
        "saturated_cells": saturated_cells,
        "complete": end_cursor >= len(cells),
    }


def run_full_catalog_sync(*, start_cursor: int = 0, max_cells: int | None = None, sleep_seconds: float = 0.05) -> dict:
    settings = get_settings()
    if settings.maps_provider != "google" or not settings.google_maps_api_key:
        raise RuntimeError("Google Maps provider is not configured")
    client = GoogleStationCatalogClient(settings.google_maps_api_key)
    total = len(nz_catalog_cells())
    cursor = start_cursor
    remaining = max_cells
    aggregate = {"added": 0, "updated": 0, "existing": 0, "invalid": 0, "provider_results": 0, "saturated_cells": 0}
    while cursor < total and (remaining is None or remaining > 0):
        batch_size = min(10, total - cursor, remaining if remaining is not None else 10)
        with SessionLocal() as db:
            result = sync_catalog_batch(db, start_cursor=cursor, max_cells=batch_size, search_cell=client.search_cell)
        for key in aggregate:
            aggregate[key] += result[key]
        cursor = result["next_cursor"]
        if remaining is not None:
            remaining -= result["processed_cells"]
        logger.info("station_catalog_progress cursor=%s total=%s added=%s updated=%s", cursor, total, aggregate["added"], aggregate["updated"])
        if cursor < total and (remaining is None or remaining > 0):
            time.sleep(max(0, sleep_seconds))
    return {**aggregate, "next_cursor": cursor, "total_cells": total, "complete": cursor >= total}


@catalog_router.get("/admin/stations/catalog-plan")
def catalog_plan(p: Principal = Depends(admin_principal)):
    cells = nz_catalog_cells()
    return {
        "total_cells": len(cells),
        "base_cells": sum(cell.density == "base" for cell in cells),
        "dense_cells": sum(cell.density == "dense" for cell in cells),
        "max_places_per_request": 20,
        "note": "Run the sync in bounded batches; Google Places usage is billable and quota-limited.",
    }


@catalog_router.post("/admin/stations/sync-nz")
def sync_nz_catalog(
    cursor: int = Query(0, ge=0),
    max_cells: int = Query(5, ge=1, le=10),
    p: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if settings.maps_provider != "google" or not settings.google_maps_api_key:
        raise HTTPException(503, "Station provider is not configured")
    try:
        return sync_catalog_batch(
            db,
            start_cursor=cursor,
            max_cells=max_cells,
            search_cell=GoogleStationCatalogClient(settings.google_maps_api_key).search_cell,
        )
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        db.rollback()
        raise HTTPException(503, "Station catalog provider is temporarily unavailable") from exc
