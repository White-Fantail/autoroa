import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import Principal, current_principal
from .contribution_rewards import PointTransaction, SubmissionFuelResult
from .db import get_db
from .models import OCRJob, Profile, Station, Status
from .user_price_boards import CommunityPriceBoardSubmission

router = APIRouter(prefix="/api/v1")
NZ_TZ = ZoneInfo("Pacific/Auckland")


class ProfileUpdate(BaseModel):
    display_name: str


def _month_start_utc() -> datetime:
    local = datetime.now(NZ_TZ)
    return datetime(local.year, local.month, 1, tzinfo=NZ_TZ).astimezone(timezone.utc)


def _alias(user_id: uuid.UUID) -> str:
    return f"Driver {str(user_id).replace('-', '')[:6].upper()}"


def _public_name(profile: Profile | None, user_id: uuid.UUID) -> str:
    if profile and profile.display_name and profile.display_name.strip():
        return profile.display_name.strip()
    return _alias(user_id)


def _profile_json(profile: Profile) -> dict:
    return {
        "id": str(profile.id),
        "member_id": f"AR-{str(profile.id).replace('-', '')[:8].upper()}",
        "display_name": profile.display_name or _alias(profile.id),
        "member_since": profile.created_at,
    }


def _normalized_display_name(value: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) < 2:
        raise HTTPException(422, "Display name must be at least 2 characters")
    if len(normalized) > 30:
        raise HTTPException(422, "Display name must be 30 characters or fewer")
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise HTTPException(422, "Display name contains unsupported characters")
    return normalized


def _badges(total_points: int, applied_prices: int, submission_count: int, station_count: int) -> list[dict]:
    definitions = [
        ("FIRST_UPDATE", "First update", "Get your first verified fuel-price update applied.", applied_prices, 1),
        ("HELPFUL_DRIVER", "Helpful driver", "Earn 10 contribution points.", total_points, 10),
        ("ROAD_SCOUT", "Road scout", "Help update prices at 5 different stations.", station_count, 5),
        ("FUEL_GUARDIAN", "Fuel guardian", "Earn 50 contribution points.", total_points, 50),
        ("CENTURY_CLUB", "Century club", "Earn 100 contribution points.", total_points, 100),
    ]
    return [
        {"id": badge_id, "name": name, "description": description, "earned": progress >= target, "progress": min(progress, target), "target": target}
        for badge_id, name, description, progress, target in definitions
    ]


def _overall_status(job: OCRJob, results: list[SubmissionFuelResult]) -> str:
    if job.status in {Status.UPLOADED, Status.PROCESSING, Status.REVIEW_REQUIRED}:
        return "REVIEWING"
    if job.status == Status.FAILED:
        return "FAILED"
    if any(row.result == "APPLIED" for row in results):
        return "APPLIED"
    if results:
        return "NO_POINTS"
    return "REVIEWING"


def _fuel_result(row: SubmissionFuelResult) -> dict:
    return {
        "fuel_type": row.fuel_type.value,
        "previous_price": float(row.previous_price) if row.previous_price is not None else None,
        "submitted_price": float(row.submitted_price),
        "final_price": float(row.final_price) if row.final_price is not None else None,
        "result": row.result,
        "points": row.points,
        "decided_at": row.decided_at,
    }


def _submission_json(db: Session, submission: CommunityPriceBoardSubmission, include_results: bool = True) -> dict:
    job = db.get(OCRJob, submission.ocr_job_id)
    station_id = job.station_id if job and job.station_id else submission.selected_station_id
    station = db.get(Station, station_id) if station_id else None
    results = list(db.scalars(select(SubmissionFuelResult).where(SubmissionFuelResult.submission_id == submission.id).order_by(SubmissionFuelResult.fuel_type))) if include_results else []
    points = sum(row.points for row in results)
    return {
        "id": str(submission.id),
        "ocr_job_id": str(submission.ocr_job_id),
        "created_at": submission.created_at,
        "status": _overall_status(job, results) if job else "FAILED",
        "ocr_status": job.status.value if job else "FAILED",
        "station": {"id": str(station.id), "name": station.name, "address": station.address_line, "city": station.city, "region": station.region} if station else None,
        "selected_station_id": str(submission.selected_station_id),
        "detected_station_id": str(submission.detected_station_id) if submission.detected_station_id else None,
        "location_status": submission.location_status,
        "points": points,
        "fuel_results": [_fuel_result(row) for row in results],
        "review_reason": (job.result_json or {}).get("review_reason") if job else None,
    }


@router.get("/me/profile")
def my_profile(p: Principal = Depends(current_principal)):
    return _profile_json(p.profile)


@router.patch("/me/profile")
def update_my_profile(data: ProfileUpdate, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    p.profile.display_name = _normalized_display_name(data.display_name)
    db.commit()
    db.refresh(p.profile)
    return _profile_json(p.profile)


@router.get("/me/contributions")
def my_contributions(status: str = Query("ALL", pattern="^(ALL|REVIEWING|APPLIED|NO_POINTS|FAILED)$"), limit: int = Query(50, ge=1, le=100), p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    submissions = list(db.scalars(select(CommunityPriceBoardSubmission).where(CommunityPriceBoardSubmission.user_id.in_(p.profile_ids)).order_by(CommunityPriceBoardSubmission.created_at.desc()).limit(limit)))
    rows = [_submission_json(db, row) for row in submissions]
    return rows if status == "ALL" else [row for row in rows if row["status"] == status]


@router.get("/me/contributions/{submission_id}")
def my_contribution_detail(submission_id: uuid.UUID, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    submission = db.scalar(select(CommunityPriceBoardSubmission).where(CommunityPriceBoardSubmission.id == submission_id, CommunityPriceBoardSubmission.user_id.in_(p.profile_ids)))
    if not submission:
        raise HTTPException(404, "Contribution not found")
    return _submission_json(db, submission)


@router.get("/me/contribution-summary")
def contribution_summary(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    month_start = _month_start_utc()
    total_points = int(db.scalar(select(func.coalesce(func.sum(PointTransaction.points), 0)).where(PointTransaction.user_id.in_(p.profile_ids))) or 0)
    month_points = int(db.scalar(select(func.coalesce(func.sum(PointTransaction.points), 0)).where(PointTransaction.user_id.in_(p.profile_ids), PointTransaction.created_at >= month_start)) or 0)
    submission_count = int(db.scalar(select(func.count()).select_from(CommunityPriceBoardSubmission).where(CommunityPriceBoardSubmission.user_id.in_(p.profile_ids))) or 0)
    applied_prices = int(db.scalar(select(func.count()).select_from(SubmissionFuelResult).join(CommunityPriceBoardSubmission, CommunityPriceBoardSubmission.id == SubmissionFuelResult.submission_id).where(CommunityPriceBoardSubmission.user_id.in_(p.profile_ids), SubmissionFuelResult.result == "APPLIED")) or 0)
    station_count = int(db.scalar(select(func.count(func.distinct(PointTransaction.station_id))).where(PointTransaction.user_id.in_(p.profile_ids))) or 0)
    return {
        "total_points": total_points,
        "month_points": month_points,
        "submission_count": submission_count,
        "applied_price_count": applied_prices,
        "contributed_station_count": station_count,
        "badges": _badges(total_points, applied_prices, submission_count, station_count),
        "month_started_at": month_start,
    }


def _leaderboard_query(period: str, scope: str, value: str | None):
    query = select(PointTransaction.user_id, func.sum(PointTransaction.points).label("points")).join(Station, Station.id == PointTransaction.station_id)
    if period == "month":
        query = query.where(PointTransaction.created_at >= _month_start_utc())
    if scope == "region":
        if not value:
            raise HTTPException(422, "Region is required")
        query = query.where(func.lower(Station.region) == value.lower())
    elif scope == "city":
        if not value:
            raise HTTPException(422, "City is required")
        query = query.where(func.lower(Station.city) == value.lower())
    elif scope == "station":
        if not value:
            raise HTTPException(422, "Station is required")
        try:
            station_id = uuid.UUID(value)
        except ValueError as exc:
            raise HTTPException(422, "Station must be a valid id") from exc
        query = query.where(PointTransaction.station_id == station_id)
    return query.group_by(PointTransaction.user_id)


@router.get("/leaderboard")
def leaderboard(period: str = Query("month", pattern="^(month|all_time)$"), scope: str = Query("national", pattern="^(national|region|city|station)$"), value: str | None = None, limit: int = Query(20, ge=1, le=100), p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    raw_rows = list(db.execute(_leaderboard_query(period, scope, value)).all())
    linked = set(p.profile_ids)
    totals: dict[uuid.UUID, int] = {}
    for user_id, points in raw_rows:
        key = p.profile.id if user_id in linked else user_id
        totals[key] = totals.get(key, 0) + int(points)
    rows = sorted(totals.items(), key=lambda item: (-item[1], str(item[0])))

    ranked = []
    current = None
    previous_points = None
    rank = 0
    for position, (user_id, numeric_points) in enumerate(rows, start=1):
        if previous_points is None or numeric_points != previous_points:
            rank = position
            previous_points = numeric_points
        is_current = user_id == p.profile.id
        profile = p.profile if is_current else db.get(Profile, user_id)
        item = {"rank": rank, "display_name": _public_name(profile, user_id), "points": numeric_points, "is_current_user": is_current}
        if is_current:
            current = item
        if position <= limit:
            ranked.append(item)
    return {"period": period, "scope": scope, "value": value, "entries": ranked, "current_user": current, "month_started_at": _month_start_utc() if period == "month" else None}
