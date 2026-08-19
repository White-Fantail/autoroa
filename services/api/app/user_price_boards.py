import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import Principal, admin_principal, current_principal
from .community_price_boards import _delete_media, _location_diagnostics, _store_media
from .config import get_settings
from .db import Base, get_db
from .image_validation import validate_image_content
from .models import MediaAsset, MediaType, OCRJob, OCRJobKind, Profile, Station


class CommunityPriceBoardSubmission(Base):
    __tablename__ = "community_price_board_submissions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    ocr_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ocr_jobs.id", ondelete="CASCADE"), unique=True)
    selected_station_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fuel_stations.id"), index=True)
    detected_station_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fuel_stations.id"))
    photo_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    photo_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    selected_station_distance_km: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    location_status: Mapped[str] = mapped_column(String, default="missing")
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_community_price_board_submission_user_created", "user_id", "created_at"),
        Index("ix_community_price_board_submission_station_created", "selected_station_id", "created_at"),
    )


class StationIssueReport(Base):
    __tablename__ = "station_issue_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    station_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fuel_stations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(40))
    details: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_station_issue_report_station_created", "station_id", "created_at"),
        Index("ix_station_issue_report_status_created", "status", "created_at"),
    )


class StationIssueRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=40)
    details: str | None = Field(default=None, max_length=1000)


STATION_ISSUE_REASONS = {
    "CLOSED",
    "NOT_A_STATION",
    "DUPLICATE",
    "WRONG_NAME_OR_BRAND",
    "WRONG_LOCATION",
    "OTHER",
}


user_price_board_router = APIRouter(prefix="/api/v1")


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
        "country_code": station.country_code,
        "latitude": float(station.latitude),
        "longitude": float(station.longitude),
        "timezone": station.timezone,
        "is_active": station.is_active,
        "created_at": station.created_at.isoformat() if getattr(station, "created_at", None) else None,
        "updated_at": station.updated_at.isoformat() if getattr(station, "updated_at", None) else None,
    }


def _admin_report_payload(report: StationIssueReport, db: Session) -> dict:
    station = db.get(Station, report.station_id)
    reporter = db.get(Profile, report.user_id)
    return {
        "id": str(report.id),
        "station_id": str(report.station_id),
        "station_name": station.name if station else "Deleted station",
        "station_address": station.address_line if station else None,
        "reporter_name": reporter.display_name if reporter else None,
        "reporter_id": str(report.user_id),
        "reason": report.reason,
        "details": report.details,
        "status": report.status,
        "created_at": report.created_at.isoformat(),
        "updated_at": report.updated_at.isoformat(),
        "station": _station_payload(station) if station else None,
    }


@user_price_board_router.get("/admin/station-reports")
def list_station_issue_reports(
    status: str | None = None,
    _p: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    query = select(StationIssueReport)
    if status:
        normalized = status.strip().upper()
        if normalized not in {"OPEN", "CLOSED"}:
            raise HTTPException(422, "Unsupported report status")
        query = query.where(StationIssueReport.status == normalized)
    reports = db.scalars(query.order_by(StationIssueReport.created_at.desc()).limit(500)).all()
    return [_admin_report_payload(report, db) for report in reports]


@user_price_board_router.get("/admin/station-reports/{report_id}")
def get_station_issue_report(
    report_id: uuid.UUID,
    _p: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    report = db.get(StationIssueReport, report_id)
    if not report:
        raise HTTPException(404, "Station report not found")
    return _admin_report_payload(report, db)


@user_price_board_router.patch("/admin/station-reports/{report_id}/close")
def close_station_issue_report(
    report_id: uuid.UUID,
    _p: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    report = db.get(StationIssueReport, report_id)
    if not report:
        raise HTTPException(404, "Station report not found")
    if report.status != "CLOSED":
        report.status = "CLOSED"
        report.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(report)
    return _admin_report_payload(report, db)


@user_price_board_router.post("/fuel-stations/{station_id}/issue-reports", status_code=201)
def report_station_issue(
    station_id: uuid.UUID,
    body: StationIssueRequest,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    from . import routes as routes_module

    station = db.get(Station, station_id)
    if not station or not station.is_active:
        raise HTTPException(404, "Active station not found")

    reason = body.reason.strip().upper()
    details = (body.details or "").strip() or None
    if reason not in STATION_ISSUE_REASONS:
        raise HTTPException(422, "Unsupported station report reason")
    if reason == "OTHER" and not details:
        raise HTTPException(422, "Please add a short description for Other")

    existing = db.scalar(
        select(StationIssueReport).where(
            StationIssueReport.station_id == station.id,
            StationIssueReport.user_id == p.profile.id,
            StationIssueReport.reason == reason,
            StationIssueReport.status == "OPEN",
        )
    )
    if existing:
        raise HTTPException(409, "You already have an open report for this issue")

    routes_module.enforce_expensive_limit(db, p.profile.id, "station-issue-report", 12)
    report = StationIssueReport(
        station_id=station.id,
        user_id=p.profile.id,
        reason=reason,
        details=details,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {
        "report_id": str(report.id),
        "station_id": str(station.id),
        "status": report.status,
        "message": "Thanks. We’ll review this station information.",
    }


@user_price_board_router.post("/fuel-stations/{station_id}/user-price-board-submissions", status_code=202)
async def submit_authenticated_station_price_board(
    station_id: uuid.UUID,
    photo: UploadFile = File(...),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Create an authenticated contribution while reusing the established community OCR pipeline."""
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

    if db.scalar(select(CommunityPriceBoardSubmission.id).where(CommunityPriceBoardSubmission.content_sha256 == digest)):
        raise HTTPException(409, "This price-board photo has already been submitted")

    routes_module.enforce_expensive_limit(db, p.profile.id, "user-price-board", 8)
    location, detected = _location_diagnostics(db, content, station)
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    selected_distance = location.get("selected_station_distance_km")

    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime_type]
    storage_path = f"community/users/{p.profile.id}/price-board/{uuid.uuid4()}.{extension}"
    _store_media(content, mime_type, storage_path)
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
                "contributor_profile_id": str(p.profile.id),
                "photo_location": location,
            },
            requires_confirmation=True,
        )
        db.add(job)
        db.flush()
        contribution = CommunityPriceBoardSubmission(
            user_id=p.profile.id,
            ocr_job_id=job.id,
            selected_station_id=station.id,
            detected_station_id=detected.id if detected else None,
            photo_latitude=Decimal(str(latitude)) if latitude is not None else None,
            photo_longitude=Decimal(str(longitude)) if longitude is not None else None,
            selected_station_distance_km=Decimal(str(selected_distance)) if selected_distance is not None else None,
            location_status=str(location.get("status") or "missing"),
            content_sha256=digest,
        )
        db.add(contribution)
        db.commit()
        db.refresh(contribution)
        db.refresh(job)
    except Exception:
        db.rollback()
        _delete_media(storage_path)
        raise

    return {
        "submission_id": str(contribution.id),
        "ocr_job_id": str(job.id),
        "status": job.status.value,
        "selected_station_id": str(station.id),
        "detected_station_id": str(detected.id) if detected else None,
        "station_mismatch": bool(location.get("station_mismatch")),
        "location_status": location.get("status"),
        "message": "Thanks! Your photo was submitted. We’ll verify the station and prices in the background.",
    }
