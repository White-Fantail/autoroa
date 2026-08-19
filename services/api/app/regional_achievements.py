import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .achievements import AchievementDefinition, UserAchievementAward, process_achievement_event
from .auth import Principal, admin_principal, current_principal
from .contribution_rewards import PointTransaction
from .db import Base, get_db
from .models import Profile, Station

NZ_TZ = ZoneInfo("Pacific/Auckland")
regional_router = APIRouter(prefix="/api/v1")


class LeaderboardPeriodFinalization(Base):
    __tablename__ = "leaderboard_period_finalizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    period_key: Mapped[str] = mapped_column(String(7))
    scope_type: Mapped[str] = mapped_column(String(16))
    scope_key: Mapped[str] = mapped_column(String(128))
    scope_label: Mapped[str] = mapped_column(String(160))
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finalized_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    participant_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("period_key", "scope_type", "scope_key", name="uq_leaderboard_period_finalization_scope"),
        Index("ix_leaderboard_period_finalization_period", "period_key"),
    )


REGIONAL_TROPHIES = [
    ("regional_champion", "Champion", 1, 1, 500),
    ("regional_top_3", "Top 3", 2, 3, 510),
    ("regional_top_10", "Top 10", 4, 10, 520),
]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def ensure_regional_achievement_catalog(db: Session) -> None:
    for key, label, minimum, maximum, sort_order in REGIONAL_TROPHIES:
        if db.scalar(select(AchievementDefinition).where(AchievementDefinition.key == key)) is not None:
            continue
        db.add(
            AchievementDefinition(
                key=key,
                name=label,
                description=f"Finish a monthly regional leaderboard in the {label.lower()} band.",
                category="REGIONAL",
                icon="trophy",
                achievement_type="REPEATABLE",
                visibility="PUBLIC",
                repeatable=True,
                enabled=True,
                sort_order=sort_order,
                criteria={"event": "payload.rank", "op": "between", "value": [minimum, maximum]},
            )
        )
    db.flush()


def _period_bounds(period_key: str) -> tuple[datetime, datetime]:
    try:
        year, month = map(int, period_key.split("-"))
        start_local = datetime(year, month, 1, tzinfo=NZ_TZ)
    except Exception as exc:
        raise HTTPException(422, "period must be YYYY-MM") from exc
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=NZ_TZ)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=NZ_TZ)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _scope_query(scope_type: str, scope_key: str, start: datetime, end: datetime):
    query = (
        select(PointTransaction.user_id, func.sum(PointTransaction.points).label("points"))
        .join(Station, Station.id == PointTransaction.station_id)
        .where(PointTransaction.created_at >= start, PointTransaction.created_at < end)
    )
    if scope_type == "CITY":
        query = query.where(func.lower(Station.city) == scope_key.lower())
    elif scope_type == "REGION":
        query = query.where(func.lower(Station.region) == scope_key.lower())
    elif scope_type == "NATIONAL":
        query = query.where(Station.country_code == "NZ")
    else:
        raise HTTPException(422, "scope_type must be CITY, REGION, or NATIONAL")
    return query.group_by(PointTransaction.user_id).order_by(func.sum(PointTransaction.points).desc(), PointTransaction.user_id)


def _scope_label(scope_type: str, scope_key: str) -> str:
    return "New Zealand" if scope_type == "NATIONAL" else scope_key


def _achievement_for_rank(db: Session, rank: int) -> AchievementDefinition | None:
    key = "regional_champion" if rank == 1 else "regional_top_3" if rank <= 3 else "regional_top_10" if rank <= 10 else None
    return db.scalar(select(AchievementDefinition).where(AchievementDefinition.key == key)) if key else None


def finalize_monthly_scope(db: Session, *, period_key: str, scope_type: str, scope_key: str, admin_user_id: uuid.UUID | None = None) -> dict:
    ensure_regional_achievement_catalog(db)
    normalized_type = scope_type.upper()
    normalized_key = "nz" if normalized_type == "NATIONAL" else scope_key.strip()
    existing = db.scalar(
        select(LeaderboardPeriodFinalization).where(
            LeaderboardPeriodFinalization.period_key == period_key,
            LeaderboardPeriodFinalization.scope_type == normalized_type,
            LeaderboardPeriodFinalization.scope_key == normalized_key,
        )
    )
    if existing is not None:
        return {"status": "already_finalized", "period_key": period_key, "scope_type": normalized_type, "scope_key": normalized_key, "participant_count": existing.participant_count}

    start, end = _period_bounds(period_key)
    rows = list(db.execute(_scope_query(normalized_type, normalized_key, start, end)).all())
    label = _scope_label(normalized_type, scope_key)
    awarded = []
    for rank, (user_id, points) in enumerate(rows, start=1):
        definition = _achievement_for_rank(db, rank)
        if definition is None:
            break
        event_key = f"leaderboard-final:{period_key}:{normalized_type}:{_slug(normalized_key)}:{user_id}"
        awards = process_achievement_event(
            db,
            event_key=event_key,
            user_id=user_id,
            event_type="LEADERBOARD_FINALIZED",
            payload={"rank": rank, "points": int(points), "scope_type": normalized_type, "scope_key": normalized_key, "scope_label": label, "period_key": period_key},
            occurred_at=end,
            instance_key=f"{period_key}:{normalized_type}:{_slug(normalized_key)}",
            period_key=period_key,
            scope_type=normalized_type,
            scope_key=normalized_key,
        )
        for award in awards:
            if award.achievement_id == definition.id:
                awarded.append({"user_id": str(user_id), "rank": rank, "points": int(points), "achievement_key": definition.key})
    db.add(
        LeaderboardPeriodFinalization(
            period_key=period_key,
            scope_type=normalized_type,
            scope_key=normalized_key,
            scope_label=label,
            finalized_by_admin_id=admin_user_id,
            participant_count=len(rows),
        )
    )
    db.flush()
    return {"status": "finalized", "period_key": period_key, "scope_type": normalized_type, "scope_key": normalized_key, "participant_count": len(rows), "awarded": awarded}


def current_titles(db: Session, user_id: uuid.UUID) -> list[dict]:
    now = datetime.now(NZ_TZ)
    start = datetime(now.year, now.month, 1, tzinfo=NZ_TZ).astimezone(timezone.utc)
    city_rows = list(db.execute(select(Station.city).join(PointTransaction, PointTransaction.station_id == Station.id).where(PointTransaction.user_id == user_id, PointTransaction.created_at >= start).distinct()).scalars())
    region_rows = list(db.execute(select(Station.region).join(PointTransaction, PointTransaction.station_id == Station.id).where(PointTransaction.user_id == user_id, PointTransaction.created_at >= start, Station.region.is_not(None)).distinct()).scalars())
    scopes = [("CITY", value) for value in city_rows] + [("REGION", value) for value in region_rows] + [("NATIONAL", "nz")]
    titles = []
    for scope_type, scope_key in scopes:
        rows = list(db.execute(_scope_query(scope_type, scope_key, start, datetime.now(timezone.utc))).all())
        for rank, (candidate_id, points) in enumerate(rows, start=1):
            if candidate_id == user_id:
                titles.append({"scope_type": scope_type, "scope_key": scope_key, "scope_label": _scope_label(scope_type, scope_key), "rank": rank, "points": int(points), "is_number_one": rank == 1})
                break
    return titles


def trophy_history(db: Session, user_id: uuid.UUID) -> list[dict]:
    rows = list(
        db.execute(
            select(UserAchievementAward, AchievementDefinition)
            .join(AchievementDefinition, AchievementDefinition.id == UserAchievementAward.achievement_id)
            .where(UserAchievementAward.user_id == user_id, AchievementDefinition.category == "REGIONAL", UserAchievementAward.revoked_at.is_(None))
            .order_by(UserAchievementAward.earned_at.desc())
        ).all()
    )
    return [
        {"achievement_key": definition.key, "name": definition.name, "period_key": award.period_key, "scope_type": award.scope_type, "scope_key": award.scope_key, "earned_at": award.earned_at, "metadata": award.metadata_json}
        for award, definition in rows
    ]


@regional_router.get("/me/regional-status")
def my_regional_status(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return {"current_titles": current_titles(db, p.profile.id), "trophies": trophy_history(db, p.profile.id)}


@regional_router.post("/admin/leaderboards/finalize")
def admin_finalize_leaderboard(period: str = Query(..., pattern=r"^\d{4}-\d{2}$"), scope_type: str = Query(..., pattern="^(CITY|REGION|NATIONAL)$"), scope_key: str = Query("nz"), p: Principal = Depends(admin_principal), db: Session = Depends(get_db)):
    result = finalize_monthly_scope(db, period_key=period, scope_type=scope_type, scope_key=scope_key, admin_user_id=p.profile.id)
    db.commit()
    return result
