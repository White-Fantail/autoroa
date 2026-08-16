import functools
import io
import logging
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Principal, current_principal
from .config import get_settings
from .db import SessionLocal, get_db
from .models import MediaAsset, OCRJob, OCRJobKind, Receipt, Station, Status
from .services import GoogleMapsProvider, haversine_km, station_match_score

inference_router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)
GPS_INFO_TAG = 0x8825
BOARD_CANDIDATE_RADIUS_KM = 2.0
BOARD_AUTOSELECT_RADIUS_KM = 1.0


def _gps_ref(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii", "ignore").upper()
    return str(value or "").upper()


def _dms_to_decimal(value: Any) -> float:
    if not value or len(value) != 3:
        raise ValueError("Invalid GPS coordinate")
    degrees, minutes, seconds = (float(part) for part in value)
    return degrees + minutes / 60 + seconds / 3600


def extract_image_gps(content: bytes) -> tuple[float, float] | None:
    """Return EXIF GPS coordinates without retaining the raw photo location."""
    try:
        with Image.open(io.BytesIO(content)) as image:
            exif = image.getexif()
            gps = exif.get_ifd(GPS_INFO_TAG) if exif else {}
        latitude_values = gps.get(2)
        longitude_values = gps.get(4)
        latitude_ref = _gps_ref(gps.get(1))
        longitude_ref = _gps_ref(gps.get(3))
        if not latitude_values or not longitude_values:
            return None
        if latitude_ref not in {"N", "S"} or longitude_ref not in {"E", "W"}:
            return None
        latitude = _dms_to_decimal(latitude_values)
        longitude = _dms_to_decimal(longitude_values)
        if latitude_ref == "S":
            latitude = -latitude
        if longitude_ref == "W":
            longitude = -longitude
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return None
        return latitude, longitude
    except (UnidentifiedImageError, OSError, TypeError, ValueError, KeyError, ZeroDivisionError):
        return None


def _active_stations(db: Session) -> list[Station]:
    return list(db.scalars(select(Station).where(Station.is_active.is_(True))))


def board_candidate_rows(stations: list[Station], latitude: float, longitude: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for station in stations:
        if station.latitude is None or station.longitude is None:
            continue
        distance = haversine_km(latitude, longitude, station.latitude, station.longitude)
        if distance > BOARD_CANDIDATE_RADIUS_KM:
            continue
        confidence = max(0.0, 1.0 - distance / BOARD_CANDIDATE_RADIUS_KM)
        rows.append(
            {
                "id": str(station.id),
                "name": station.name,
                "address": station.address_line,
                "distance_km": round(distance, 3),
                "match_confidence": round(confidence, 3),
                "match_source": "photo_location",
            }
        )
    return sorted(rows, key=lambda row: (row["distance_km"], -row["match_confidence"]))[:5]


def receipt_candidate_rows(
    stations: list[Station],
    station_name: str | None,
    station_address: str | None,
    latitude: float | None,
    longitude: float | None,
) -> list[dict[str, Any]]:
    """Rank receipt text as the primary signal and photo location as a tie-breaker."""
    has_text = bool((station_name or "").strip() or (station_address or "").strip())
    has_location = latitude is not None and longitude is not None
    rows: list[dict[str, Any]] = []
    for station in stations:
        distance = None
        location_score = 0.0
        if has_location and station.latitude is not None and station.longitude is not None:
            distance = haversine_km(latitude, longitude, station.latitude, station.longitude)
            location_score = max(0.0, 1.0 - distance / 10.0)
        text_score = station_match_score(
            station_name or "",
            station_address,
            station.name,
            station.address_line,
            10.0,
        )
        # station_match_score contributes at most 0.85 when distance is neutralized.
        # Location can add at most 0.15, so contradictory GPS cannot outrank a
        # materially stronger receipt name/address match.
        score = text_score + 0.15 * location_score
        if has_text:
            if text_score < 0.08 and (distance is None or distance > 1.0):
                continue
        elif not has_location or distance is None or distance > BOARD_CANDIDATE_RADIUS_KM:
            continue
        if score < 0.05:
            continue
        rows.append(
            {
                "id": str(station.id),
                "name": station.name,
                "address": station.address_line,
                "distance_km": round(distance, 3) if distance is not None else None,
                "match_confidence": round(min(1.0, score), 3),
                "text_confidence": round(min(0.85, text_score), 3),
                "match_source": "receipt_and_photo_location" if has_location else "receipt",
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -row["match_confidence"],
            row["distance_km"] if row["distance_km"] is not None else float("inf"),
        ),
    )[:5]


def _provider_import_candidates(
    db: Session,
    routes_module: Any,
    *,
    latitude: float | None,
    longitude: float | None,
    station_name: str | None = None,
    station_address: str | None = None,
) -> bool:
    settings = get_settings()
    if settings.maps_provider != "google" or not settings.google_maps_api_key:
        return False
    try:
        provider = GoogleMapsProvider(settings.google_maps_api_key)
        if station_name or station_address:
            query = " ".join(value.strip() for value in (station_name, station_address) if value and value.strip())
            places = provider.text_search(query)
        elif latitude is not None and longitude is not None:
            if not (-48 <= latitude <= -34 and 165 <= longitude <= 179):
                return False
            places = provider.nearby_stations(latitude, longitude, BOARD_CANDIDATE_RADIUS_KM)
        else:
            return False
        imported = False
        for place in places:
            values = routes_module.place_values(place)
            if not values:
                continue
            routes_module.import_place(db, values)
            imported = True
        if imported:
            db.flush()
        return imported
    except (httpx.HTTPError, TypeError, ValueError):
        logger.warning("station_candidate_provider_failed", exc_info=True)
        return False


def _board_candidates_for_gps(
    db: Session,
    routes_module: Any,
    latitude: float,
    longitude: float,
) -> list[dict[str, Any]]:
    rows = board_candidate_rows(_active_stations(db), latitude, longitude)
    if not rows and _provider_import_candidates(
        db,
        routes_module,
        latitude=latitude,
        longitude=longitude,
    ):
        rows = board_candidate_rows(_active_stations(db), latitude, longitude)
    return rows


def _board_candidates(db: Session, routes_module: Any, content: bytes) -> list[dict[str, Any]]:
    gps = extract_image_gps(content)
    if not gps:
        return []
    return _board_candidates_for_gps(db, routes_module, *gps)


def _receipt_candidates(
    db: Session,
    routes_module: Any,
    receipt: Receipt,
    content: bytes,
    latitude: float | None = None,
    longitude: float | None = None,
) -> list[dict[str, Any]]:
    if latitude is None or longitude is None:
        gps = extract_image_gps(content)
        if gps:
            latitude, longitude = gps
    station_address = (receipt.raw_result_json or {}).get("station_address")
    rows = receipt_candidate_rows(
        _active_stations(db),
        receipt.station_text,
        station_address,
        latitude,
        longitude,
    )
    best_text = rows[0].get("text_confidence", 0) if rows else 0
    if (not rows or (receipt.station_text and best_text < 0.2)) and _provider_import_candidates(
        db,
        routes_module,
        latitude=latitude,
        longitude=longitude,
        station_name=receipt.station_text,
        station_address=station_address,
    ):
        rows = receipt_candidate_rows(
            _active_stations(db),
            receipt.station_text,
            station_address,
            latitude,
            longitude,
        )
    return rows


def _board_location_diagnostics(
    gps: tuple[float, float] | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if not gps:
        return {
            "status": "missing",
            "source": "exif_gps",
            "reason": "No usable GPS coordinates were found in the uploaded photo metadata.",
            "search_radius_km": BOARD_CANDIDATE_RADIUS_KM,
        }
    latitude, longitude = gps
    diagnostic: dict[str, Any] = {
        "status": "available",
        "source": "exif_gps",
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "search_radius_km": BOARD_CANDIDATE_RADIUS_KM,
    }
    if candidates:
        diagnostic["nearest_station_distance_km"] = candidates[0]["distance_km"]
        diagnostic["candidate_count"] = len(candidates)
        diagnostic["match_status"] = (
            "auto_selected"
            if candidates[0]["distance_km"] <= BOARD_AUTOSELECT_RADIUS_KM
            else "candidate_found_outside_auto_select_radius"
        )
        diagnostic["auto_select_radius_km"] = BOARD_AUTOSELECT_RADIUS_KM
    else:
        diagnostic["candidate_count"] = 0
        diagnostic["match_status"] = "no_station_within_search_radius"
        diagnostic["reason"] = (
            f"GPS was found, but no active station matched within {BOARD_CANDIDATE_RADIUS_KM:.1f} km."
        )
    return diagnostic


def _post_process_job(job_id: uuid.UUID, bind: Any, routes_module: Any) -> None:
    session_factory = (lambda: Session(bind=bind)) if bind is not None else SessionLocal
    with session_factory() as db:
        job = db.get(OCRJob, job_id)
        if not job or job.status == Status.FAILED:
            return
        media = db.get(MediaAsset, job.media_asset_id)
        if not media:
            return
        if job.kind == OCRJobKind.PRICE_BOARD:
            # Explicit station selection always wins and keeps the existing auto-apply behavior.
            if job.station_id is not None:
                return
            content = routes_module.media_bytes(media)
            gps = extract_image_gps(content)
            candidates = _board_candidates_for_gps(db, routes_module, *gps) if gps else []
            result = dict(job.result_json or {})
            result["photo_location"] = _board_location_diagnostics(gps, candidates)
            if candidates:
                result["station_candidates"] = candidates
                top = candidates[0]
                if top["distance_km"] <= BOARD_AUTOSELECT_RADIUS_KM:
                    job.station_id = uuid.UUID(top["id"])
                    # An inferred station is only a default candidate. It must never
                    # convert a high-confidence board OCR result into an automatic apply.
                    job.requires_confirmation = True
                    job.status = Status.REVIEW_REQUIRED
                    job.applied_at = None
            job.result_json = result
            db.commit()
            return
        if job.kind != OCRJobKind.RECEIPT:
            return
        receipt = db.get(Receipt, job.resource_id)
        if not receipt or receipt.station_id is not None:
            return
        content = routes_module.media_bytes(media)
        candidates = _receipt_candidates(db, routes_module, receipt, content)
        if not candidates:
            return
        receipt.station_id = uuid.UUID(candidates[0]["id"])
        result = dict(job.result_json or {})
        result["station_candidates"] = candidates
        job.result_json = result
        db.commit()


def install_station_inference(routes_module: Any) -> None:
    """Wrap OCR completion without changing the existing OCR transaction semantics."""
    original = routes_module.run_ocr_job
    if getattr(original, "_station_inference_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped(job_id: uuid.UUID, claim_token: uuid.UUID, bind: Any = None):
        result = original(job_id, claim_token, bind)
        try:
            _post_process_job(job_id, bind, routes_module)
        except Exception:
            # Station inference is best effort and must never turn successful OCR into a failure.
            logger.exception("station_inference_failed job_id=%s", job_id)
        return result

    wrapped._station_inference_wrapped = True
    routes_module.run_ocr_job = wrapped


@inference_router.get("/receipts/{item_id}/station-candidates")
def station_candidates_with_photo_location(
    item_id: uuid.UUID,
    latitude: float | None = None,
    longitude: float | None = None,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Return receipt-first station candidates, using EXIF location only as secondary evidence."""
    from . import routes as routes_module

    receipt = routes_module.owned(db, Receipt, item_id, p.profile.id)
    media = routes_module.owned(db, MediaAsset, receipt.media_asset_id, p.profile.id)
    try:
        content = routes_module.media_bytes(media)
    except httpx.HTTPError:
        content = b""
    rows = _receipt_candidates(
        db,
        routes_module,
        receipt,
        content,
        latitude=latitude,
        longitude=longitude,
    )
    return rows[:5]
