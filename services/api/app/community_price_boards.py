import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Principal, admin_principal, current_principal
from .config import get_settings
from .db import SessionLocal, get_db
from .image_validation import validate_image_content
from .models import (
    MediaAsset,
    MediaType,
    OCRJob,
    OCRJobKind,
    Observation,
    Source,
    Station,
    Status,
    Verification,
)
from .schemas import AdminPriceBoardCreate
from .services import haversine_km, observation_anomaly
from .station_inference import board_candidate_rows, extract_image_gps

community_router = APIRouter(prefix="/api/v1")

ADMIN_AUTO_CONFIDENCE = Decimal("0.90")
COMMUNITY_AUTO_CONFIDENCE = Decimal("0.93")
ADMIN_AUTO_DISTANCE_KM = 0.30
COMMUNITY_AUTO_DISTANCE_KM = 0.20

# SQLAlchemy derives NOT NULL from the current non-optional annotations. The
# migration makes these columns nullable in deployed databases; mutating the
# metadata here keeps SQLite create_all-based tests aligned with that schema.
MediaAsset.__table__.c.user_id.nullable = True
OCRJob.__table__.c.user_id.nullable = True


def _json_job(job: OCRJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "user_id": str(job.user_id) if job.user_id else None,
        "kind": job.kind.value,
        "resource_id": str(job.resource_id),
        "station_id": str(job.station_id) if job.station_id else None,
        "media_asset_id": str(job.media_asset_id),
        "status": job.status.value,
        "result_json": job.result_json,
        "confidence": float(job.confidence) if job.confidence is not None else None,
        "requires_confirmation": job.requires_confirmation,
        "applied_at": job.applied_at,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "submission_source": (job.result_json or {}).get("submission_source") or (
            "FUEL_MAP_USER" if job.kind == OCRJobKind.PRICE_BOARD and job.user_id is None else "ADMIN"
        ),
    }


def _store_anonymous_media(content: bytes, mime_type: str, storage_path: str) -> None:
    settings = get_settings()
    if settings.supabase_url and settings.supabase_service_role_key:
        response = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/storage/v1/object/private-media/{storage_path}",
            headers={
                "authorization": f"Bearer {settings.supabase_service_role_key}",
                "apikey": settings.supabase_service_role_key,
                "content-type": mime_type,
                "x-upsert": "false",
            },
            content=content,
            timeout=20,
        )
        if not response.is_success:
            raise HTTPException(503, "Private media upload is temporarily unavailable")
        return
    if settings.app_env in {"development", "test"}:
        root = Path(settings.local_media_dir).resolve()
        path = (root / storage_path).resolve()
        if root not in path.parents:
            raise HTTPException(422, "Invalid media path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return
    raise HTTPException(503, "Private media storage is not configured")


def _delete_anonymous_media(storage_path: str) -> None:
    settings = get_settings()
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            httpx.request(
                "DELETE",
                f"{settings.supabase_url.rstrip('/')}/storage/v1/object/private-media",
                headers={
                    "authorization": f"Bearer {settings.supabase_service_role_key}",
                    "apikey": settings.supabase_service_role_key,
                },
                json={"prefixes": [storage_path]},
                timeout=15,
            )
        except httpx.HTTPError:
            pass
        return
    if settings.app_env in {"development", "test"}:
        root = Path(settings.local_media_dir).resolve()
        path = (root / storage_path).resolve()
        if root in path.parents:
            path.unlink(missing_ok=True)


def _active_stations(db: Session) -> list[Station]:
    return list(db.scalars(select(Station).where(Station.is_active.is_(True))))


def _location_diagnostics(
    db: Session,
    media_content: bytes,
    selected_station: Station | None,
) -> tuple[dict[str, Any], Station | None]:
    gps = extract_image_gps(media_content)
    if not gps:
        return (
            {
                "status": "missing",
                "source": "exif_gps",
                "reason": "No usable GPS coordinates were found in the uploaded photo metadata.",
            },
            None,
        )
    latitude, longitude = gps
    candidates = board_candidate_rows(_active_stations(db), latitude, longitude)
    detected = db.get(Station, uuid.UUID(candidates[0]["id"])) if candidates else None
    result: dict[str, Any] = {
        "status": "available",
        "source": "exif_gps",
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "station_candidates": candidates,
    }
    if detected:
        result.update(
            {
                "detected_station_id": str(detected.id),
                "detected_station_name": detected.name,
                "detected_station_address": detected.address_line,
                "nearest_station_distance_km": candidates[0]["distance_km"],
            }
        )
    if selected_station:
        selected_distance = haversine_km(
            latitude,
            longitude,
            selected_station.latitude,
            selected_station.longitude,
        )
        result["selected_station_id"] = str(selected_station.id)
        result["selected_station_name"] = selected_station.name
        result["selected_station_distance_km"] = round(selected_distance, 3)
        if selected_distance <= 0.30:
            result["selected_station_match_status"] = "matched"
        elif selected_distance <= 1.0:
            result["selected_station_match_status"] = "warning"
        else:
            result["selected_station_match_status"] = "mismatch"
        if detected and detected.id != selected_station.id:
            result["station_mismatch"] = True
            result["reason"] = (
                f"The selected station is {selected_distance:.2f} km from the photo location, "
                f"while {detected.name} is the nearest detected station."
            )
        else:
            result["station_mismatch"] = False
    return result, detected


def _apply_prices(
    db: Session,
    *,
    job: OCRJob,
    station: Station,
    source: Source,
    prices: list[dict[str, Any]],
    observed_at: datetime,
) -> None:
    from . import routes as routes_module

    existing = {
        row.fuel_type: row
        for row in db.scalars(select(Observation).where(Observation.media_asset_id == job.media_asset_id))
    }
    for entry in prices:
        fuel_type = entry["fuel_type"]
        price = Decimal(str(entry["price_per_litre"] if "price_per_litre" in entry else entry["price"]))
        confidence = Decimal(str(entry.get("confidence", job.confidence or 0)))
        row = existing.get(fuel_type)
        if row is None:
            row = Observation(
                station_id=station.id,
                fuel_type=fuel_type,
                pump_price_per_litre=price,
                source=source,
                verification_level=Verification.UNVERIFIED,
                observed_at=observed_at,
                media_asset_id=job.media_asset_id,
                confidence_score=confidence,
                is_anomaly=observation_anomaly(db, station.id, fuel_type, price),
            )
            db.add(row)
            db.flush()
        routes_module.resolve_current_price(db, station.id, fuel_type)


def _price_entries(job: OCRJob) -> list[dict[str, Any]]:
    return list((job.result_json or {}).get("prices") or [])


def _has_anomaly(db: Session, station: Station, prices: list[dict[str, Any]]) -> bool:
    return any(
        observation_anomaly(
            db,
            station.id,
            entry["fuel_type"],
            Decimal(str(entry["price_per_litre"])),
        )
        for entry in prices
    )


def _finalize_price_board_job(
    job_id: uuid.UUID,
    selected_station_id: uuid.UUID | None,
    source_name: str,
    bind: Any,
) -> None:
    session_factory = (lambda: Session(bind=bind)) if bind is not None else SessionLocal
    with session_factory() as db:
        job = db.get(OCRJob, job_id)
        if not job or job.status == Status.FAILED:
            return
        media = db.get(MediaAsset, job.media_asset_id)
        if not media:
            return
        from . import routes as routes_module

        content = routes_module.media_bytes(media)
        selected = db.get(Station, selected_station_id) if selected_station_id else None
        diagnostic, detected = _location_diagnostics(db, content, selected)
        result = dict(job.result_json or {})
        result["submission_source"] = source_name
        result["selected_station_id"] = str(selected_station_id) if selected_station_id else None
        result["photo_location"] = diagnostic
        if diagnostic.get("station_candidates"):
            result["station_candidates"] = diagnostic["station_candidates"]
        job.result_json = result

        if selected is None:
            job.station_id = detected.id if detected else None
            job.requires_confirmation = True
            job.status = Status.REVIEW_REQUIRED
            job.applied_at = None
            db.commit()
            return
        if not selected.is_active:
            job.station_id = selected.id
            job.requires_confirmation = True
            job.status = Status.REVIEW_REQUIRED
            job.applied_at = None
            result["review_reason"] = "The selected station is no longer active."
            db.commit()
            return

        prices = _price_entries(job)
        threshold = COMMUNITY_AUTO_CONFIDENCE if source_name == "FUEL_MAP_USER" else ADMIN_AUTO_CONFIDENCE
        max_distance = COMMUNITY_AUTO_DISTANCE_KM if source_name == "FUEL_MAP_USER" else ADMIN_AUTO_DISTANCE_KM
        selected_distance = diagnostic.get("selected_station_distance_km")
        same_station = not diagnostic.get("station_mismatch", False)
        location_ok = (
            diagnostic.get("status") == "available"
            and selected_distance is not None
            and float(selected_distance) <= max_distance
            and same_station
        )
        confidence_ok = bool(prices) and job.confidence is not None and job.confidence >= threshold
        anomaly = _has_anomaly(db, selected, prices) if prices else True

        job.station_id = selected.id
        if location_ok and confidence_ok and not anomaly:
            _apply_prices(
                db,
                job=job,
                station=selected,
                source=Source.COMMUNITY if source_name == "FUEL_MAP_USER" else Source.ADMIN,
                prices=prices,
                observed_at=job.created_at,
            )
            job.requires_confirmation = False
            job.status = Status.READY
            job.applied_at = datetime.now(timezone.utc)
            result["auto_apply"] = {
                "applied": True,
                "confidence_threshold": float(threshold),
                "distance_threshold_km": max_distance,
            }
        else:
            job.requires_confirmation = True
            job.status = Status.REVIEW_REQUIRED
            job.applied_at = None
            reasons = []
            if not location_ok:
                reasons.append("photo location did not safely match the selected station")
            if not confidence_ok:
                reasons.append(f"OCR confidence was below {int(threshold * 100)}%")
            if anomaly:
                reasons.append("one or more prices were anomalous")
            result["review_reason"] = "; ".join(reasons) or "Manual review is required."
            result["auto_apply"] = {
                "applied": False,
                "confidence_threshold": float(threshold),
                "distance_threshold_km": max_distance,
            }
        job.result_json = result
        db.commit()


def install_community_price_board_processing(routes_module: Any) -> None:
    """Prevent selected-station boards from publishing before location validation."""
    original = routes_module.run_ocr_job
    if getattr(original, "_community_price_boards_wrapped", False):
        return

    def wrapped(job_id: uuid.UUID, claim_token: uuid.UUID, bind: Any = None):
        session_factory = (lambda: Session(bind=bind)) if bind is not None else SessionLocal
        selected_station_id = None
        source_name = "ADMIN"
        with session_factory() as db:
            job = db.get(OCRJob, job_id)
            if job and job.kind == OCRJobKind.PRICE_BOARD:
                selected_station_id = job.station_id
                source_name = "FUEL_MAP_USER" if job.user_id is None else "ADMIN"
                # The legacy worker auto-applies a selected station at 90% before
                # EXIF validation. Clear it temporarily; the wrapper restores the
                # selected station only after location and anomaly checks.
                if selected_station_id is not None:
                    job.station_id = None
                    db.commit()
        result = original(job_id, claim_token, bind)
        if selected_station_id is not None or source_name == "FUEL_MAP_USER":
            _finalize_price_board_job(job_id, selected_station_id, source_name, bind)
        return result

    wrapped._community_price_boards_wrapped = True
    routes_module.run_ocr_job = wrapped


@community_router.post("/fuel-stations/{station_id}/price-board-submissions", status_code=202)
async def submit_station_price_board(
    station_id: uuid.UUID,
    request: Request,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Accept a station-scoped price-board photo without requiring an account."""
    from . import routes as routes_module

    station = db.get(Station, station_id)
    if not station or not station.is_active:
        raise HTTPException(404, "Active station not found")
    settings = get_settings()
    mime_type = photo.content_type or ""
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(422, "Unsupported image type")
    content = await photo.read(settings.max_upload_bytes + 1)
    if not content or len(content) > settings.max_upload_bytes:
        raise HTTPException(422, "Image is empty or too large")
    try:
        width, height, digest = validate_image_content(content, mime_type)
    except ValueError as exc:
        raise HTTPException(422, "Uploaded content is not a safe supported image") from exc

    client_key = request.client.host if request.client else "unknown"
    anonymous_id = uuid.uuid5(uuid.NAMESPACE_URL, f"autoroa-community-price-board:{client_key}")
    routes_module.enforce_expensive_limit(db, anonymous_id, "community-price-board", 4)

    duplicate = db.scalar(
        select(OCRJob)
        .join(MediaAsset, MediaAsset.id == OCRJob.media_asset_id)
        .where(
            OCRJob.kind == OCRJobKind.PRICE_BOARD,
            OCRJob.user_id.is_(None),
            OCRJob.station_id == station.id,
            MediaAsset.content_sha256 == digest,
            OCRJob.created_at >= datetime.now(timezone.utc) - timedelta(days=1),
        )
        .order_by(OCRJob.created_at.desc())
    )
    if duplicate:
        return {
            "submission_id": str(duplicate.id),
            "status": duplicate.status.value,
            "message": "This photo was already submitted. Updated prices will appear on the Fuel Map after processing.",
        }

    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime_type]
    storage_path = f"community/price-board/{uuid.uuid4()}.{extension}"
    _store_anonymous_media(content, mime_type, storage_path)
    try:
        media = MediaAsset(
            user_id=None,
            type=MediaType.OTHER,
            storage_bucket="private-media" if settings.supabase_url else "local-private-media",
            storage_path=storage_path,
            mime_type=mime_type,
            file_size=len(content),
            width=width,
            height=height,
            content_sha256=digest,
        )
        db.add(media)
        db.flush()
        job = OCRJob(
            user_id=None,
            kind=OCRJobKind.PRICE_BOARD,
            resource_id=media.id,
            station_id=station.id,
            media_asset_id=media.id,
            result_json={
                "submission_source": "FUEL_MAP_USER",
                "selected_station_id": str(station.id),
            },
            requires_confirmation=True,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
    except Exception:
        db.rollback()
        _delete_anonymous_media(storage_path)
        raise
    return {
        "submission_id": str(job.id),
        "status": job.status.value,
        "message": "Thanks! Your photo was submitted. Updated prices will appear on the Fuel Map after processing.",
    }


@community_router.get("/ocr-jobs")
def list_ocr_jobs_with_admin_queue(
    kind: OCRJobKind | None = None,
    limit: int = Query(20, ge=1, le=100),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    query = select(OCRJob)
    if kind:
        query = query.where(OCRJob.kind == kind)
    if not (p.admin and kind == OCRJobKind.PRICE_BOARD):
        query = query.where(OCRJob.user_id == p.profile.id)
    jobs = db.scalars(query.order_by(OCRJob.created_at.desc()).limit(limit))
    return [_json_job(job) for job in jobs]


@community_router.get("/ocr-jobs/{job_id}")
def get_ocr_job_with_admin_access(
    job_id: uuid.UUID,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    job = db.get(OCRJob, job_id)
    if not job or (job.user_id != p.profile.id and not (p.admin and job.kind == OCRJobKind.PRICE_BOARD)):
        raise HTTPException(404, "Resource not found")
    return _json_job(job)


@community_router.post("/admin/stations/{station_id}/price-board")
def review_or_apply_price_board(
    station_id: uuid.UUID,
    data: AdminPriceBoardCreate,
    p: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    from . import routes as routes_module

    station = db.get(Station, station_id)
    if not station or not station.is_active:
        raise HTTPException(404, "Active station not found")
    if len({entry.fuel_type for entry in data.prices}) != len(data.prices):
        raise HTTPException(422, "Each fuel type may only be entered once")
    observed_at = data.observed_at if data.observed_at.tzinfo else None
    if observed_at is None:
        raise HTTPException(422, "Observed time must include a timezone")
    if observed_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(422, "Observed time cannot be in the future")

    if data.job_id is None:
        for entry in data.prices:
            row = Observation(
                station_id=station.id,
                fuel_type=entry.fuel_type,
                pump_price_per_litre=entry.price,
                source=Source.ADMIN,
                verification_level=Verification.UNVERIFIED,
                observed_at=observed_at,
                confidence_score=Decimal("1"),
                is_anomaly=observation_anomaly(db, station.id, entry.fuel_type, entry.price),
            )
            db.add(row)
            db.flush()
            routes_module.resolve_current_price(db, station.id, entry.fuel_type)
        db.commit()
        return {"applied": True}

    job = db.get(OCRJob, data.job_id)
    if not job or job.kind != OCRJobKind.PRICE_BOARD:
        raise HTTPException(404, "OCR job not found")
    if job.status in {Status.UPLOADED, Status.PROCESSING}:
        raise HTTPException(409, "OCR processing is not complete")
    if job.applied_at is not None or job.status in {Status.READY, Status.CONFIRMED}:
        raise HTTPException(409, "This OCR job has already been applied")
    if job.status != Status.REVIEW_REQUIRED:
        raise HTTPException(409, "This OCR job cannot be confirmed")
    if data.media_asset_id is not None and data.media_asset_id != job.media_asset_id:
        raise HTTPException(422, "OCR job and photo do not match")
    if db.scalar(select(Observation.id).where(Observation.media_asset_id == job.media_asset_id)):
        raise HTTPException(409, "This photo has already been applied")

    source_name = (job.result_json or {}).get("submission_source") or (
        "FUEL_MAP_USER" if job.user_id is None else "ADMIN"
    )
    prices = [
        {"fuel_type": entry.fuel_type, "price": entry.price, "confidence": job.confidence or Decimal("1")}
        for entry in data.prices
    ]
    _apply_prices(
        db,
        job=job,
        station=station,
        source=Source.COMMUNITY if source_name == "FUEL_MAP_USER" else Source.ADMIN,
        prices=prices,
        observed_at=observed_at,
    )
    result = dict(job.result_json or {})
    selected_id = result.get("selected_station_id")
    detected_id = (result.get("photo_location") or {}).get("detected_station_id")
    if selected_id and str(station.id) == selected_id:
        resolution = "USE_SELECTED_STATION"
    elif detected_id and str(station.id) == detected_id:
        resolution = "CHANGE_TO_DETECTED_STATION"
    else:
        resolution = "MANUAL_STATION_SELECTION"
    result["review_resolution"] = resolution
    result["reviewed_station_id"] = str(station.id)
    job.result_json = result
    job.station_id = station.id
    job.requires_confirmation = False
    job.status = Status.READY
    job.applied_at = datetime.now(timezone.utc)
    db.commit()
    return {"applied": True, "review_resolution": resolution}
