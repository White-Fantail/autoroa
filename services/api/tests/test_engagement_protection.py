import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.contribution_rewards import PointTransaction, SubmissionFuelResult
from app.contribution_views import _badges
from app.models import CurrentPrice, FuelType, Observation, Profile, Source, Station, Verification
from app.user_price_boards import CommunityPriceBoardSubmission


def test_badges_are_derived_from_ledger_progress():
    badges={row["id"]:row for row in _badges(total_points=12,applied_prices=4,submission_count=6,station_count=5)}
    assert badges["FIRST_UPDATE"]["earned"] is True
    assert badges["HELPFUL_DRIVER"]["earned"] is True
    assert badges["ROAD_SCOUT"]["earned"] is True
    assert badges["FUEL_GUARDIAN"]["earned"] is False
    assert badges["FUEL_GUARDIAN"]["progress"]==12


def test_public_snapshot_attributes_only_applied_current_observation(client,db):
    user=Profile(auth_user_id=str(uuid.uuid4()));db.add(user)
    station=Station(name="Community Station",address_line="1 Test Road",city="Christchurch",region="Canterbury",country_code="NZ",latitude=Decimal("-43.53"),longitude=Decimal("172.63"),is_active=True);db.add(station);db.flush()
    observation=Observation(station_id=station.id,fuel_type=FuelType.PETROL_91,pump_price_per_litre=Decimal("2.399"),source=Source.COMMUNITY,verification_level=Verification.USER_CONFIRMED,observed_at=datetime.now(timezone.utc),confidence_score=Decimal("1"),is_anomaly=False,is_active=True);db.add(observation);db.flush()
    current=CurrentPrice(station_id=station.id,fuel_type=FuelType.PETROL_91,price=Decimal("2.399"),observed_at=observation.observed_at,observation_id=observation.id,confidence_score=Decimal("1"),verification_level=Verification.USER_CONFIRMED);db.add(current)
    from app.models import OCRJob, OCRJobKind, Status
    job=OCRJob(user_id=None,kind=OCRJobKind.PRICE_BOARD,resource_id=uuid.uuid4(),station_id=station.id,media_asset_id=uuid.uuid4(),status=Status.READY,requires_confirmation=False);db.add(job);db.flush()
    sub=CommunityPriceBoardSubmission(user_id=user.id,ocr_job_id=job.id,selected_station_id=station.id,location_status="available",content_sha256="b"*64);db.add(sub);db.flush()
    db.add(SubmissionFuelResult(submission_id=sub.id,station_id=station.id,fuel_type=FuelType.PETROL_91,submitted_price=Decimal("2.399"),final_price=Decimal("2.399"),result="APPLIED",points=1,observation_id=observation.id));db.commit()
    body=client.get("/api/v1/fuel-stations/snapshot").json();row=next(item for item in body["stations"] if item["id"]==str(station.id))
    assert row["contributors"]["PETROL_91"].startswith("Driver ")
    assert user.display_name is None
