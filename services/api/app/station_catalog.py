import logging
import math
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Iterable

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import DateTime, Integer, Numeric, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import Principal, admin_principal
from .config import get_settings
from .db import Base, SessionLocal, get_db
from .models import Station

catalog_router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)

NZ_MAINLAND_BOUNDS = (
    (-41.75, -34.30, 172.30, 178.70),
    (-47.65, -40.15, 166.00, 174.70),
)
BASE_LAT_STEP = 0.45
BASE_LNG_STEP = 0.55
BASE_RADIUS_KM = 35.0
DENSE_RADIUS_KM = 8.0
DENSE_LAT_STEP = 0.10
DENSE_LNG_STEP = 0.13
DENSE_AREAS = (
    (-37.20, -36.55, 174.45, 175.15),
    (-37.95, -37.55, 175.00, 175.45),
    (-38.05, -37.55, 176.00, 176.45),
    (-41.45, -40.95, 174.55, 175.25),
    (-43.75, -43.30, 172.30, 172.90),
    (-46.05, -45.65, 170.20, 170.75),
)
MAX_REFINEMENT_DEPTH = 2
TARGETED_MAX_REFINEMENT_DEPTH = 5
MIN_REFINEMENT_RADIUS_KM = 0.75
REFINEMENT_RADIUS_FACTOR = 0.60
REFINEMENT_OFFSET_FACTOR = 0.32


class StationCatalogSaturatedCell(Base):
    __tablename__ = "station_catalog_saturated_cells"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    radius_km: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    density: Mapped[str] = mapped_column(String)
    refinement_depth: Mapped[int] = mapped_column(Integer, default=0)
    result_count: Mapped[int] = mapped_column(Integer)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        UniqueConstraint("latitude", "longitude", "radius_km", "refinement_depth", name="uq_station_catalog_saturated_cell"),
    )


@dataclass(frozen=True)
class CatalogCell:
    latitude: float
    longitude: float
    radius_km: float
    density: str
    refinement_depth: int = 0

    def detail(self, result_count: int) -> dict:
        return {"latitude": round(self.latitude, 6), "longitude": round(self.longitude, 6), "radius_km": round(self.radius_km, 3), "density": self.density, "refinement_depth": self.refinement_depth, "result_count": result_count}


def _frange(start: float, stop: float, step: float) -> Iterable[float]:
    value = start
    while value <= stop + 1e-9:
        yield round(value, 6)
        value += step


def _cells_for_bounds(south, north, west, east, *, lat_step, lng_step, radius_km, density):
    for latitude in _frange(south, north, lat_step):
        for longitude in _frange(west, east, lng_step):
            yield CatalogCell(latitude, longitude, radius_km, density)


def nz_catalog_cells() -> list[CatalogCell]:
    cells: list[CatalogCell] = []
    for bounds in NZ_MAINLAND_BOUNDS:
        cells.extend(_cells_for_bounds(*bounds, lat_step=BASE_LAT_STEP, lng_step=BASE_LNG_STEP, radius_km=BASE_RADIUS_KM, density="base"))
    for bounds in DENSE_AREAS:
        cells.extend(_cells_for_bounds(*bounds, lat_step=DENSE_LAT_STEP, lng_step=DENSE_LNG_STEP, radius_km=DENSE_RADIUS_KM, density="dense"))
    unique: dict[tuple[float, float, float], CatalogCell] = {}
    for cell in cells:
        unique.setdefault((cell.latitude, cell.longitude, cell.radius_km), cell)
    return list(unique.values())


def refinement_cells(cell: CatalogCell) -> list[CatalogCell]:
    child_radius = cell.radius_km * REFINEMENT_RADIUS_FACTOR
    offset_km = cell.radius_km * REFINEMENT_OFFSET_FACTOR
    lat_offset = offset_km / 111.0
    lng_scale = max(0.25, math.cos(math.radians(cell.latitude)))
    lng_offset = offset_km / (111.0 * lng_scale)
    depth = cell.refinement_depth + 1
    density = f"{cell.density}_refined"
    return [CatalogCell(cell.latitude + lat_sign * lat_offset, cell.longitude + lng_sign * lng_offset, child_radius, density, depth) for lat_sign in (-1, 1) for lng_sign in (-1, 1)]


class GoogleStationCatalogClient:
    def __init__(self, api_key: str): self.api_key = api_key
    def search_cell(self, cell: CatalogCell) -> list[dict]:
        response = httpx.post("https://places.googleapis.com/v1/places:searchNearby", headers={"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.addressComponents"}, json={"includedTypes": ["gas_station"], "maxResultCount": 20, "regionCode": "NZ", "locationRestriction": {"circle": {"center": {"latitude": cell.latitude, "longitude": cell.longitude}, "radius": min(cell.radius_km * 1000, 50000)}}}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        places = payload.get("places", []) if isinstance(payload, dict) else None
        if not isinstance(places, list): raise ValueError("Invalid Google Places response")
        return places


def _place_values(place: dict):
    place_id = place.get("id"); name = (place.get("displayName") or {}).get("text"); location = place.get("location") or {}; address = place.get("formattedAddress"); latitude = location.get("latitude"); longitude = location.get("longitude")
    if not place_id or not name or not address or not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)): return None
    if not (-48 <= latitude <= -34 and 165 <= longitude <= 179): return None
    components = {kind: text for component in place.get("addressComponents", []) for kind in component.get("types", []) if (text := component.get("longText"))}
    return place_id, name, address, latitude, longitude, components.get("locality") or components.get("postal_town") or "New Zealand", components.get("administrative_area_level_1")


def upsert_catalog_place(db: Session, place: dict) -> tuple[Station | None, str]:
    values = _place_values(place)
    if not values: return None, "invalid"
    place_id, name, address, latitude, longitude, city, region = values
    item = db.scalar(select(Station).where(Station.google_place_id == place_id))
    incoming = {"name": name, "address_line": address, "city": city, "region": region, "latitude": Decimal(str(latitude)), "longitude": Decimal(str(longitude))}
    if item:
        changed = False
        for field, value in incoming.items():
            if getattr(item, field) != value: setattr(item, field, value); changed = True
        if not item.is_active: item.is_active = True; changed = True
        return item, "updated" if changed else "existing"
    item = Station(google_place_id=place_id, country_code="NZ", timezone="Pacific/Auckland", is_active=True, **incoming); db.add(item); return item, "added"


def persist_saturated_cell(db: Session, cell: CatalogCell, result_count: int) -> None:
    latitude = Decimal(str(round(cell.latitude, 6))); longitude = Decimal(str(round(cell.longitude, 6))); radius = Decimal(str(round(cell.radius_km, 3)))
    row = db.scalar(select(StationCatalogSaturatedCell).where(StationCatalogSaturatedCell.latitude == latitude, StationCatalogSaturatedCell.longitude == longitude, StationCatalogSaturatedCell.radius_km == radius, StationCatalogSaturatedCell.refinement_depth == cell.refinement_depth))
    now = datetime.now(timezone.utc)
    if row: row.result_count = result_count; row.last_seen_at = now; row.density = cell.density
    else: db.add(StationCatalogSaturatedCell(latitude=latitude, longitude=longitude, radius_km=radius, density=cell.density, refinement_depth=cell.refinement_depth, result_count=result_count, first_seen_at=now, last_seen_at=now))


def _scan_cell(db: Session, cell: CatalogCell, *, search_cell: Callable[[CatalogCell], list[dict]], seen_place_ids: set[str], stats: dict, saturated_details: list[dict], max_refinement_depth: int = MAX_REFINEMENT_DEPTH) -> None:
    places = search_cell(cell); stats["provider_results"] += len(places)
    if cell.refinement_depth > 0: stats["refinement_cells"] += 1
    saturated = len(places) >= 20
    if saturated:
        saturated_details.append(cell.detail(len(places))); persist_saturated_cell(db, cell, len(places))
    for place in places:
        place_id = place.get("id") if isinstance(place, dict) else None
        if place_id and place_id in seen_place_ids: continue
        if place_id: seen_place_ids.add(place_id)
        _, status = upsert_catalog_place(db, place); stats[status] += 1
    if saturated and cell.refinement_depth < max_refinement_depth and cell.radius_km * REFINEMENT_RADIUS_FACTOR >= MIN_REFINEMENT_RADIUS_KM:
        for child in refinement_cells(cell): _scan_cell(db, child, search_cell=search_cell, seen_place_ids=seen_place_ids, stats=stats, saturated_details=saturated_details, max_refinement_depth=max_refinement_depth)


def sync_catalog_batch(db: Session, *, start_cursor: int = 0, max_cells: int = 10, search_cell: Callable[[CatalogCell], list[dict]]) -> dict:
    cells = nz_catalog_cells()
    if start_cursor < 0 or start_cursor > len(cells): raise ValueError("Invalid catalog cursor")
    end_cursor = min(len(cells), start_cursor + max_cells); stats = {"added": 0, "updated": 0, "existing": 0, "invalid": 0, "provider_results": 0, "refinement_cells": 0}; seen_place_ids: set[str] = set(); saturated_details: list[dict] = []
    for cell in cells[start_cursor:end_cursor]: _scan_cell(db, cell, search_cell=search_cell, seen_place_ids=seen_place_ids, stats=stats, saturated_details=saturated_details)
    db.commit()
    return {**stats, "start_cursor": start_cursor, "next_cursor": end_cursor, "total_cells": len(cells), "processed_cells": end_cursor - start_cursor, "saturated_cells": len(saturated_details), "saturated_cell_details": saturated_details, "complete": end_cursor >= len(cells)}


def _deepest_saturated_cells(db: Session) -> list[CatalogCell]:
    rows = list(db.scalars(select(StationCatalogSaturatedCell).where(StationCatalogSaturatedCell.result_count >= 20)))
    if not rows: return []
    max_depth = max(row.refinement_depth for row in rows)
    return [CatalogCell(float(row.latitude), float(row.longitude), float(row.radius_km), row.density, row.refinement_depth) for row in rows if row.refinement_depth == max_depth]


def run_saturated_refinement(*, sleep_seconds: float = 0.05) -> dict:
    settings = get_settings()
    if settings.maps_provider != "google" or not settings.google_maps_api_key: raise RuntimeError("Google Maps provider is not configured")
    client = GoogleStationCatalogClient(settings.google_maps_api_key)
    with SessionLocal() as db:
        roots = _deepest_saturated_cells(db)
        root_depth = max((cell.refinement_depth for cell in roots), default=None)
        stats = {"added": 0, "updated": 0, "existing": 0, "invalid": 0, "provider_results": 0, "refinement_cells": 0}; seen_place_ids: set[str] = set(); details: list[dict] = []
        for index, root in enumerate(roots, 1):
            # The root itself was already searched. Start with its children to avoid paying for the same request again.
            for child in refinement_cells(root):
                _scan_cell(db, child, search_cell=client.search_cell, seen_place_ids=seen_place_ids, stats=stats, saturated_details=details, max_refinement_depth=TARGETED_MAX_REFINEMENT_DEPTH)
            if index % 10 == 0: db.commit(); logger.info("station_catalog_targeted_refinement progress=%s/%s added=%s saturated=%s", index, len(roots), stats["added"], len(details)); time.sleep(max(0, sleep_seconds))
        db.commit()
    terminal = [item for item in details if item["refinement_depth"] == TARGETED_MAX_REFINEMENT_DEPTH or item["radius_km"] * REFINEMENT_RADIUS_FACTOR < MIN_REFINEMENT_RADIUS_KM]
    return {**stats, "source_depth": root_depth, "source_saturated_cells": len(roots), "saturated_cells": len(details), "terminal_saturated_cells": len(terminal), "terminal_saturated_cell_details": terminal, "complete": len(terminal) == 0}


def run_full_catalog_sync(*, start_cursor: int = 0, max_cells: int | None = None, sleep_seconds: float = 0.05) -> dict:
    settings = get_settings()
    if settings.maps_provider != "google" or not settings.google_maps_api_key: raise RuntimeError("Google Maps provider is not configured")
    client = GoogleStationCatalogClient(settings.google_maps_api_key); total = len(nz_catalog_cells()); cursor = start_cursor; remaining = max_cells; aggregate = {"added": 0, "updated": 0, "existing": 0, "invalid": 0, "provider_results": 0, "refinement_cells": 0, "saturated_cells": 0}; saturated_details: list[dict] = []
    while cursor < total and (remaining is None or remaining > 0):
        batch_size = min(10, total - cursor, remaining if remaining is not None else 10)
        with SessionLocal() as db: result = sync_catalog_batch(db, start_cursor=cursor, max_cells=batch_size, search_cell=client.search_cell)
        for key in aggregate: aggregate[key] += result[key]
        saturated_details.extend(result["saturated_cell_details"]); cursor = result["next_cursor"]
        if remaining is not None: remaining -= result["processed_cells"]
        logger.info("station_catalog_progress cursor=%s total=%s added=%s updated=%s saturated=%s refined=%s", cursor, total, aggregate["added"], aggregate["updated"], aggregate["saturated_cells"], aggregate["refinement_cells"])
        if cursor < total and (remaining is None or remaining > 0): time.sleep(max(0, sleep_seconds))
    return {**aggregate, "saturated_cell_details": saturated_details, "next_cursor": cursor, "total_cells": total, "complete": cursor >= total}


@catalog_router.get("/admin/stations/catalog-plan")
def catalog_plan(p: Principal = Depends(admin_principal)):
    cells = nz_catalog_cells(); return {"total_cells": len(cells), "base_cells": sum(cell.density == "base" for cell in cells), "dense_cells": sum(cell.density == "dense" for cell in cells), "max_places_per_request": 20, "max_refinement_depth": MAX_REFINEMENT_DEPTH, "targeted_max_refinement_depth": TARGETED_MAX_REFINEMENT_DEPTH}


@catalog_router.get("/admin/stations/saturated-cells")
def list_saturated_cells(limit: int = Query(200, ge=1, le=1000), p: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(StationCatalogSaturatedCell).order_by(StationCatalogSaturatedCell.last_seen_at.desc()).limit(limit)))
    return [{"id": row.id, "latitude": row.latitude, "longitude": row.longitude, "radius_km": row.radius_km, "density": row.density, "refinement_depth": row.refinement_depth, "result_count": row.result_count, "first_seen_at": row.first_seen_at, "last_seen_at": row.last_seen_at} for row in rows]


@catalog_router.post("/admin/stations/sync-nz")
def sync_nz_catalog(cursor: int = Query(0, ge=0), max_cells: int = Query(5, ge=1, le=10), p: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    settings = get_settings()
    if settings.maps_provider != "google" or not settings.google_maps_api_key: raise HTTPException(503, "Station provider is not configured")
    try: return sync_catalog_batch(db, start_cursor=cursor, max_cells=max_cells, search_cell=GoogleStationCatalogClient(settings.google_maps_api_key).search_cell)
    except (httpx.HTTPError, ValueError) as exc: raise HTTPException(502, f"Station catalog sync failed: {exc}") from exc
