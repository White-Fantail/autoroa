"""Fast capture ingestion. Private fuel records are committed only after safe OCR checks.

The source photographs and processing sessions remain durable if the phone closes.
No community price observation is published without explicit station verification.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import Principal, current_principal
from .db import SessionLocal, get_db
from .models import (
    FillUp, FuelType, MediaAsset, MediaType, OCRJob, OCRJobKind,
    OdometerReading, QuickCapture, Receipt, Status, Vehicle,
)
from .services import recalculate_vehicle_economy, receipt_arithmetic_suspicious
from .routes import enforce_expensive_limit

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)
AUTO_CONFIDENCE = Decimal("0.90")


class QuickCaptureCreate(BaseModel):
    client_token: str = Field(min_length=12, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    vehicle_id: uuid.UUID
    receipt_media_asset_id: uuid.UUID


class QuickCaptureOdometer(BaseModel):
    odometer_media_asset_id: uuid.UUID


def _owned(db: Session, model, item_id: uuid.UUID, user_id: uuid.UUID):
    resource = db.scalar(select(model).where(model.id == item_id, model.user_id == user_id))
    if resource is None:
        raise HTTPException(404, "Resource not found")
    return resource


def _summary(db: Session, capture: QuickCapture):
    receipt = db.get(Receipt, capture.receipt_id)
    return {
        "id": capture.id,
        "vehicle_id": capture.vehicle_id,
        "status": capture.status,
        "error_code": capture.error_code,
        "receipt_id": capture.receipt_id,
        "receipt_processing_status": receipt.processing_status if receipt else None,
        "odometer_reading_id": capture.odometer_reading_id,
        "fill_up_id": capture.fill_up_id,
        "created_at": capture.created_at,
    }


@router.post("/quick-captures", status_code=201)
def create_capture(
    data: QuickCaptureCreate,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    prior = db.scalar(select(QuickCapture).where(
        QuickCapture.user_id == p.profile.id,
        QuickCapture.client_token == data.client_token,
    ))
    if prior:
        existing_receipt = db.get(Receipt, prior.receipt_id)
        if (prior.vehicle_id != data.vehicle_id or
                not existing_receipt or
                existing_receipt.media_asset_id != data.receipt_media_asset_id):
            raise HTTPException(409, "Capture token was reused for different media")
        return _summary(db, prior)

    vehicle = _owned(db, Vehicle, data.vehicle_id, p.profile.id)
    if vehicle.is_archived:
        raise HTTPException(422, "Archived vehicles cannot receive new fuel captures")
    media = _owned(db, MediaAsset, data.receipt_media_asset_id, p.profile.id)
    if media.type != MediaType.RECEIPT:
        raise HTTPException(422, "A receipt photo is required")
    if db.scalar(select(Receipt.id).where(Receipt.media_asset_id == media.id)):
        raise HTTPException(409, "This receipt has already been used")

    enforce_expensive_limit(db, p.profile.id, "ocr-job", 6)
    receipt = Receipt(user_id=p.profile.id, media_asset_id=media.id)
    db.add(receipt)
    db.flush()
    capture = QuickCapture(
        user_id=p.profile.id,
        client_token=data.client_token,
        vehicle_id=vehicle.id,
        receipt_id=receipt.id,
        status="PROCESSING",
    )
    db.add(capture)
    db.add(OCRJob(
        user_id=p.profile.id,
        kind=OCRJobKind.RECEIPT,
        resource_id=receipt.id,
        media_asset_id=media.id,
    ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "The capture already exists. Retry with the same token") from exc
    db.refresh(capture)
    return _summary(db, capture)


@router.post("/quick-captures/{capture_id}/odometer")
def add_capture_odometer(
    capture_id: uuid.UUID,
    data: QuickCaptureOdometer,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    capture = _owned(db, QuickCapture, capture_id, p.profile.id)
    media = _owned(db, MediaAsset, data.odometer_media_asset_id, p.profile.id)
    if media.type != MediaType.ODOMETER:
        raise HTTPException(422, "An odometer photo is required")
    if capture.odometer_reading_id:
        existing = db.get(OdometerReading, capture.odometer_reading_id)
        if existing and existing.media_asset_id == media.id:
            return _summary(db, capture)
        raise HTTPException(409, "An odometer photo is already attached")
    if db.scalar(select(OdometerReading.id).where(OdometerReading.media_asset_id == media.id)):
        raise HTTPException(409, "This odometer photo has already been used")
    enforce_expensive_limit(db, p.profile.id, "ocr-job", 6)
    reading = OdometerReading(
        user_id=p.profile.id, vehicle_id=capture.vehicle_id, media_asset_id=media.id,
    )
    db.add(reading)
    db.flush()
    capture.odometer_reading_id = reading.id
    capture.status = "PROCESSING"
    capture.error_code = None
    db.add(OCRJob(
        user_id=p.profile.id,
        kind=OCRJobKind.ODOMETER,
        resource_id=reading.id,
        media_asset_id=media.id,
    ))
    db.commit()
    return _summary(db, capture)


@router.get("/quick-captures")
def list_captures(
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    captures = list(db.scalars(
        select(QuickCapture).where(QuickCapture.user_id == p.profile.id)
        .order_by(QuickCapture.created_at.desc()).limit(30)
    ))
    return [_summary(db, item) for item in captures]


@router.get("/quick-captures/{capture_id}")
def get_capture(
    capture_id: uuid.UUID,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    return _summary(db, _owned(db, QuickCapture, capture_id, p.profile.id))


class QuickCaptureReview(BaseModel):
    occurred_at: datetime
    fuel_type: FuelType
    litres: Decimal = Field(gt=0, le=1000)
    pump_price_per_litre: Decimal = Field(gt=0, le=20)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    total_amount: Decimal = Field(gt=0)
    odometer_km: int | None = Field(None, ge=0)
    full_tank: bool = True
    missed_previous_fill: bool = False
    acknowledge_arithmetic_warning: bool = False
    confirm_odometer_conflict: bool = False


@router.post("/quick-captures/{capture_id}/confirm")
def confirm_capture(
    capture_id: uuid.UUID,
    data: QuickCaptureReview,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Review OCR or enter missing fields without publishing community prices."""
    capture = _owned(db, QuickCapture, capture_id, p.profile.id)
    receipt = _owned(db, Receipt, capture.receipt_id, p.profile.id)
    _owned(db, Vehicle, capture.vehicle_id, p.profile.id)
    occurred = data.occurred_at
    if occurred.tzinfo is None:
        raise HTTPException(422, "Timestamp needs a timezone")
    now = datetime.now(timezone.utc)
    if occurred > now + timedelta(hours=1) or occurred < now - timedelta(days=90):
        raise HTTPException(422, "Receipt date is outside the supported period")
    if (receipt_arithmetic_suspicious(data.litres, data.pump_price_per_litre,
                                      data.total_amount, data.discount_amount) and
            not data.acknowledge_arithmetic_warning):
        raise HTTPException(409, "Receipt arithmetic needs explicit confirmation")
    duplicate = db.scalar(select(FillUp).where(
        FillUp.vehicle_id == capture.vehicle_id, FillUp.occurred_at == occurred,
    ))
    if duplicate and duplicate.id != capture.fill_up_id:
        raise HTTPException(409, "A different fill-up already exists at this time")

    fill = db.get(FillUp, capture.fill_up_id) if capture.fill_up_id else None
    if fill is None:
        fill = FillUp(
            user_id=p.profile.id, vehicle_id=capture.vehicle_id,
            receipt_id=receipt.id, station_id=None,
            occurred_at=occurred, fuel_type=data.fuel_type,
            litres=data.litres, pump_price_per_litre=data.pump_price_per_litre,
            discount_amount=data.discount_amount, total_amount=data.total_amount,
            odometer_km=None, full_tank=data.full_tank,
            missed_previous_fill=data.missed_previous_fill,
        )
        db.add(fill)
        db.flush()
        capture.fill_up_id = fill.id
    if (data.odometer_km is not None and
            not _odometer_in_sequence(db, fill, data.odometer_km) and
            not data.confirm_odometer_conflict):
        raise HTTPException(409, "Odometer conflicts with adjacent fill-ups")

    receipt.processing_status = Status.CONFIRMED
    receipt.fuel_type = data.fuel_type
    receipt.litres = data.litres
    receipt.pump_price_per_litre = data.pump_price_per_litre
    receipt.discount_amount = data.discount_amount
    receipt.total_amount = data.total_amount
    receipt.transaction_datetime = occurred
    job = db.scalar(select(OCRJob).where(
        OCRJob.user_id == p.profile.id, OCRJob.kind == OCRJobKind.RECEIPT,
        OCRJob.resource_id == receipt.id,
    ).order_by(OCRJob.created_at.desc()))
    if job:
        job.status = Status.CONFIRMED
        job.requires_confirmation = False
        job.applied_at = now

    fill.occurred_at = occurred
    fill.fuel_type = data.fuel_type
    fill.litres = data.litres
    fill.pump_price_per_litre = data.pump_price_per_litre
    fill.discount_amount = data.discount_amount
    fill.total_amount = data.total_amount
    fill.odometer_km = data.odometer_km
    fill.full_tank = data.full_tank
    fill.missed_previous_fill = data.missed_previous_fill
    if capture.odometer_reading_id and data.odometer_km is not None:
        reading = _owned(db, OdometerReading, capture.odometer_reading_id, p.profile.id)
        reading.reading_km = data.odometer_km
        reading.processing_status = Status.CONFIRMED
        fill.odometer_image_id = reading.media_asset_id
        odo_job = db.scalar(select(OCRJob).where(
            OCRJob.user_id == p.profile.id, OCRJob.kind == OCRJobKind.ODOMETER,
            OCRJob.resource_id == reading.id,
        ).order_by(OCRJob.created_at.desc()))
        if odo_job:
            odo_job.status = Status.CONFIRMED
            odo_job.requires_confirmation = False
            odo_job.applied_at = now
    db.flush()
    recalculate_vehicle_economy(db, capture.vehicle_id)
    capture.status = "CONFIRMED"
    capture.error_code = None
    db.commit()
    return _summary(db, capture)


def _trusted_receipt(receipt: Receipt, vehicle: Vehicle) -> bool:
    core_confidences = (
        receipt.fuel_type_confidence,
        receipt.litres_confidence,
        receipt.price_confidence,
        receipt.total_confidence,
        receipt.datetime_confidence,
    )
    if any(value is None or value < AUTO_CONFIDENCE for value in core_confidences):
        return False
    if receipt.fuel_type is None or receipt.fuel_type != vehicle.fuel_type:
        return False
    if (receipt.litres is None or receipt.pump_price_per_litre is None or
            receipt.total_amount is None or receipt.transaction_datetime is None):
        return False
    occurred_at = receipt.transaction_datetime
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if occurred_at > now + timedelta(hours=1) or occurred_at < now - timedelta(days=90):
        return False
    discount = receipt.discount_amount or Decimal("0")
    if discount and (receipt.discount_confidence is None or receipt.discount_confidence < AUTO_CONFIDENCE):
        return False
    return not receipt_arithmetic_suspicious(
        receipt.litres, receipt.pump_price_per_litre, receipt.total_amount, discount,
    )


def _odometer_in_sequence(db: Session, fill: FillUp, reading_km: int) -> bool:
    before = db.scalar(select(FillUp).where(
        FillUp.vehicle_id == fill.vehicle_id, FillUp.id != fill.id,
        FillUp.occurred_at < fill.occurred_at, FillUp.odometer_km.is_not(None),
    ).order_by(FillUp.occurred_at.desc()))
    after = db.scalar(select(FillUp).where(
        FillUp.vehicle_id == fill.vehicle_id, FillUp.id != fill.id,
        FillUp.occurred_at > fill.occurred_at, FillUp.odometer_km.is_not(None),
    ).order_by(FillUp.occurred_at))
    return not ((before and reading_km < before.odometer_km) or
                (after and reading_km > after.odometer_km))


def _finalize(db: Session, capture: QuickCapture):
    receipt = db.get(Receipt, capture.receipt_id)
    vehicle = db.get(Vehicle, capture.vehicle_id)
    if receipt is None or vehicle is None:
        capture.status, capture.error_code = "FAILED", "MISSING_RESOURCE"
        return
    if receipt.processing_status == Status.FAILED:
        capture.status, capture.error_code = "FAILED", "RECEIPT_OCR_FAILED"
        return
    if receipt.processing_status in (Status.UPLOADED, Status.PROCESSING):
        return

    if capture.fill_up_id is None:
        if not _trusted_receipt(receipt, vehicle):
            capture.status, capture.error_code = "REVIEW_REQUIRED", "RECEIPT_REVIEW_REQUIRED"
            return
        occurred_at = receipt.transaction_datetime
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        existing = db.scalar(select(FillUp).where(
            FillUp.vehicle_id == capture.vehicle_id,
            FillUp.occurred_at == occurred_at,
        ))
        if existing:
            capture.status, capture.error_code = "REVIEW_REQUIRED", "FILLUP_TIME_CONFLICT"
            return
        # Keep inferred station names private; unreviewed station matching must
        # never create a public price observation.
        receipt.processing_status = Status.CONFIRMED
        fill = FillUp(
            user_id=capture.user_id,
            vehicle_id=capture.vehicle_id,
            receipt_id=receipt.id,
            station_id=None,
            occurred_at=occurred_at,
            fuel_type=receipt.fuel_type,
            litres=receipt.litres,
            pump_price_per_litre=receipt.pump_price_per_litre,
            discount_amount=receipt.discount_amount or Decimal("0"),
            total_amount=receipt.total_amount,
            odometer_km=None,
            full_tank=True,
            missed_previous_fill=False,
        )
        db.add(fill)
        db.flush()
        capture.fill_up_id = fill.id
        recalculate_vehicle_economy(db, fill.vehicle_id)

    if capture.odometer_reading_id is not None:
        reading = db.get(OdometerReading, capture.odometer_reading_id)
        if reading is None or reading.processing_status == Status.FAILED:
            capture.status, capture.error_code = "REVIEW_REQUIRED", "ODOMETER_OCR_FAILED"
            return
        if reading.processing_status in (Status.UPLOADED, Status.PROCESSING):
            capture.status = "PROCESSING"
            return
        if (reading.reading_km is None or reading.confidence is None or
                reading.confidence < AUTO_CONFIDENCE):
            capture.status, capture.error_code = "REVIEW_REQUIRED", "ODOMETER_REVIEW_REQUIRED"
            return
        fill = db.get(FillUp, capture.fill_up_id)
        if not _odometer_in_sequence(db, fill, reading.reading_km):
            capture.status, capture.error_code = "REVIEW_REQUIRED", "ODOMETER_CONFLICT"
            return
        fill.odometer_km = reading.reading_km
        fill.odometer_image_id = reading.media_asset_id
        reading.processing_status = Status.CONFIRMED
        recalculate_vehicle_economy(db, fill.vehicle_id)

    capture.status = "CONFIRMED"
    capture.error_code = None


def finalize_quick_captures(bind=None, max_items: int = 20) -> int:
    """Resolve OCR results idempotently in the server worker."""
    count = 0
    with Session(bind=bind) if bind is not None else SessionLocal() as db:
        captures = list(db.scalars(
            select(QuickCapture).where(QuickCapture.status == "PROCESSING")
            .order_by(QuickCapture.created_at).limit(max_items)
        ))
        for capture in captures:
            try:
                _finalize(db, capture)
                db.commit()
                count += 1
            except Exception:
                db.rollback()
                logger.exception("quick_capture_finalize_failed capture_id=%s", capture.id)
    return count
