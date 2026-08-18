import logging
import math
import uuid
from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import admin_principal
from .db import get_db
from .models import CurrentPrice, FillUp, FuelType, OCRJob, Observation, Receipt, Station
from .services import haversine_km, resolve_current_price

station_admin_router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)

CATALOG_DUPLICATE_RADIUS_M = 5.0


def _distance_m(first: Station, second: Station) -> float:
    return haversine_km(
        float(first.latitude),
        float(first.longitude),
        float(second.latitude),
        float(second.longitude),
    ) * 1000.0


def _station_payload(station: Station) -> dict:
    return {
        "id": str(station.id),
        "brand_id": str(station.brand_id) if station.brand_id else None,
        "name": station.name,
        "google_place_id": station.google_place_id,
        "address_line": station.address_line,
        "suburb": station.suburb,
        "city": station.city,
        "region": station.region,
        "postal_code": station.postal_code,
        "latitude": float(station.latitude),
        "longitude": float(station.longitude),
        "is_active": station.is_active,
        "created_at": station.created_at.isoformat() if station.created_at else None,
        "updated_at": station.updated_at.isoformat() if station.updated_at else None,
    }


def _find_nearby_station(
    db: Session,
    latitude: float,
    longitude: float,
    *,
    radius_m: float = CATALOG_DUPLICATE_RADIUS_M,
) -> Station | None:
    if radius_m <= 0:
        return db.scalar(
            select(Station).where(
                Station.is_active.is_(True),
                Station.latitude == Decimal(str(latitude)),
                Station.longitude == Decimal(str(longitude)),
            )
        )
    lat_delta = radius_m / 111_320.0
    longitude_scale = max(0.2, math.cos(math.radians(latitude)))
    lng_delta = radius_m / (111_320.0 * longitude_scale)
    candidates = db.scalars(
        select(Station).where(
            Station.is_active.is_(True),
            Station.latitude.between(latitude - lat_delta, latitude + lat_delta),
            Station.longitude.between(longitude - lng_delta, longitude + lng_delta),
        )
    )
    best: tuple[float, Station] | None = None
    for candidate in candidates:
        distance = haversine_km(
            latitude,
            longitude,
            float(candidate.latitude),
            float(candidate.longitude),
        ) * 1000.0
        if distance <= radius_m and (best is None or distance < best[0]):
            best = (distance, candidate)
    return best[1] if best else None


def install_catalog_dedup(station_catalog_module) -> None:
    """Prevent future nationwide catalog syncs from creating stations within 5 m."""
    original = station_catalog_module.upsert_catalog_place
    if getattr(original, "_autoroa_location_dedup", False):
        return

    def deduplicating_upsert(db: Session, place: dict):
        values = station_catalog_module._place_values(place)
        if not values:
            return None, "invalid"
        place_id, _, _, latitude, longitude, _, _ = values
        existing = db.scalar(
            select(Station).where(Station.google_place_id == place_id)
        )
        if existing:
            return original(db, place)
        nearby = _find_nearby_station(db, latitude, longitude)
        if nearby:
            logger.info(
                "station_catalog_location_duplicate skipped_place_id=%s canonical_station_id=%s radius_m=%s",
                place_id,
                nearby.id,
                CATALOG_DUPLICATE_RADIUS_M,
            )
            return nearby, "existing"
        return original(db, place)

    deduplicating_upsert._autoroa_location_dedup = True
    station_catalog_module.upsert_catalog_place = deduplicating_upsert


class _UnionFind:
    def __init__(self, station_ids: list[uuid.UUID]):
        self.parent = {station_id: station_id for station_id in station_ids}

    def find(self, station_id: uuid.UUID) -> uuid.UUID:
        root = station_id
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[station_id] != station_id:
            parent = self.parent[station_id]
            self.parent[station_id] = root
            station_id = parent
        return root

    def union(self, first: uuid.UUID, second: uuid.UUID) -> None:
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root != second_root:
            self.parent[second_root] = first_root


def duplicate_groups(stations: list[Station], radius_m: float) -> list[dict]:
    if len(stations) < 2:
        return []
    union = _UnionFind([station.id for station in stations])
    pairs: list[tuple[uuid.UUID, uuid.UUID, float]] = []

    if radius_m == 0:
        exact: dict[tuple[Decimal, Decimal], list[Station]] = defaultdict(list)
        for station in stations:
            exact[(station.latitude, station.longitude)].append(station)
        for matching in exact.values():
            if len(matching) < 2:
                continue
            anchor = matching[0]
            for station in matching[1:]:
                union.union(anchor.id, station.id)
                pairs.append((anchor.id, station.id, 0.0))
    else:
        lat_cell = radius_m / 111_320.0
        # Use the smallest cosine across New Zealand so neighbouring cells cannot miss a candidate.
        lng_cell = radius_m / (111_320.0 * 0.65)
        buckets: dict[tuple[int, int], list[Station]] = defaultdict(list)
        for station in stations:
            key = (
                math.floor(float(station.latitude) / lat_cell),
                math.floor(float(station.longitude) / lng_cell),
            )
            buckets[key].append(station)
        seen_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
        for (lat_key, lng_key), bucket in buckets.items():
            neighbours: list[Station] = []
            for lat_offset in (-1, 0, 1):
                for lng_offset in (-1, 0, 1):
                    neighbours.extend(
                        buckets.get((lat_key + lat_offset, lng_key + lng_offset), [])
                    )
            for first in bucket:
                for second in neighbours:
                    if first.id == second.id:
                        continue
                    pair_key = tuple(sorted((first.id, second.id), key=str))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    distance = _distance_m(first, second)
                    if distance <= radius_m:
                        union.union(first.id, second.id)
                        pairs.append((first.id, second.id, distance))

    grouped: dict[uuid.UUID, list[Station]] = defaultdict(list)
    for station in stations:
        grouped[union.find(station.id)].append(station)
    pair_lookup: dict[uuid.UUID, list[dict]] = defaultdict(list)
    for first_id, second_id, distance in pairs:
        root = union.find(first_id)
        pair_lookup[root].append(
            {
                "first_station_id": str(first_id),
                "second_station_id": str(second_id),
                "distance_m": round(distance, 2),
            }
        )

    result = []
    for root, members in grouped.items():
        if len(members) < 2:
            continue
        group_pairs = pair_lookup[root]
        result.append(
            {
                "id": ":".join(sorted(str(member.id) for member in members)),
                "station_count": len(members),
                "minimum_distance_m": min(
                    (pair["distance_m"] for pair in group_pairs), default=0.0
                ),
                "maximum_pair_distance_m": max(
                    (pair["distance_m"] for pair in group_pairs), default=0.0
                ),
                "stations": [
                    _station_payload(member)
                    for member in sorted(members, key=lambda item: (item.name.lower(), str(item.id)))
                ],
                "pairs": sorted(group_pairs, key=lambda pair: pair["distance_m"]),
            }
        )
    return sorted(
        result,
        key=lambda group: (
            group["minimum_distance_m"],
            -group["station_count"],
            group["stations"][0]["name"].lower(),
        ),
    )


@station_admin_router.get("/admin/station-duplicate-groups")
def admin_station_duplicate_groups(
    radius_m: float = Query(default=5.0, ge=0, le=100),
    include_inactive: bool = Query(default=False),
    p=Depends(admin_principal),
    db: Session = Depends(get_db),
):
    query = select(Station)
    if not include_inactive:
        query = query.where(Station.is_active.is_(True))
    stations = list(db.scalars(query.order_by(Station.id)))
    groups = duplicate_groups(stations, radius_m)
    return {
        "radius_m": radius_m,
        "station_count": len(stations),
        "group_count": len(groups),
        "duplicate_station_count": sum(group["station_count"] for group in groups),
        "groups": groups,
    }


def merge_station_records(db: Session, canonical: Station, duplicate: Station) -> dict:
    if canonical.id == duplicate.id:
        raise HTTPException(422, "Canonical and duplicate stations must be different")
    if not canonical.is_active:
        raise HTTPException(422, "Canonical station must be active")

    # Current prices have a composite station/fuel primary key, so remove the
    # duplicate snapshot before moving observations and rebuild it afterwards.
    db.execute(delete(CurrentPrice).where(CurrentPrice.station_id == duplicate.id))
    moved = {
        "receipts": db.execute(
            update(Receipt)
            .where(Receipt.station_id == duplicate.id)
            .values(station_id=canonical.id)
        ).rowcount,
        "ocr_jobs": db.execute(
            update(OCRJob)
            .where(OCRJob.station_id == duplicate.id)
            .values(station_id=canonical.id)
        ).rowcount,
        "fill_ups": db.execute(
            update(FillUp)
            .where(FillUp.station_id == duplicate.id)
            .values(station_id=canonical.id)
        ).rowcount,
        "observations": db.execute(
            update(Observation)
            .where(Observation.station_id == duplicate.id)
            .values(station_id=canonical.id)
        ).rowcount,
    }
    duplicate_google_place_id = duplicate.google_place_id
    db.delete(duplicate)
    try:
        db.flush()
        for fuel_type in FuelType:
            resolve_current_price(db, canonical.id, fuel_type)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409,
            "This station still has related records that cannot be merged safely",
        ) from exc
    db.refresh(canonical)
    return {
        "station": _station_payload(canonical),
        "deleted_station_id": str(duplicate.id),
        "deleted_google_place_id": duplicate_google_place_id,
        "moved": moved,
    }


@station_admin_router.post("/admin/station-duplicates/{canonical_id}/merge")
def admin_merge_station_duplicate(
    canonical_id: uuid.UUID,
    duplicate_id: uuid.UUID = Query(),
    p=Depends(admin_principal),
    db: Session = Depends(get_db),
):
    canonical = db.get(Station, canonical_id)
    duplicate = db.get(Station, duplicate_id)
    if not canonical or not duplicate:
        raise HTTPException(404, "Station not found")
    distance_m = _distance_m(canonical, duplicate)
    result = merge_station_records(db, canonical, duplicate)
    result["distance_m"] = round(distance_m, 2)
    return result
