import uuid
from decimal import Decimal

from sqlalchemy import select

from app.contribution_rewards import PointTransaction, SubmissionFuelResult
from app.models import FuelType, OCRJob, OCRJobKind, Profile, Station, Status
from app.user_price_boards import CommunityPriceBoardSubmission


def _profile(client, db, auth_id):
    headers={"Authorization":f"Bearer dev:{auth_id}"}
    assert client.get("/api/v1/me/contribution-summary",headers=headers).status_code==200
    return headers, db.scalar(select(Profile).where(Profile.auth_user_id==str(auth_id)))


def _station(db,name,region="Canterbury",city="Christchurch"):
    row=Station(name=name,address_line="1 Test Road",city=city,region=region,country_code="NZ",latitude=Decimal("-43.530000"),longitude=Decimal("172.630000"),is_active=True)
    db.add(row);db.flush();return row


def _contribution(db,user,station,status=Status.READY):
    job=OCRJob(user_id=None,kind=OCRJobKind.PRICE_BOARD,resource_id=uuid.uuid4(),station_id=station.id,media_asset_id=uuid.uuid4(),status=status,result_json={"submission_source":"FUEL_MAP_USER"},requires_confirmation=False)
    db.add(job);db.flush()
    sub=CommunityPriceBoardSubmission(user_id=user.id,ocr_job_id=job.id,selected_station_id=station.id,location_status="available",content_sha256="a"*64)
    db.add(sub);db.flush();return sub,job


def test_profile_display_name_can_be_updated_and_is_normalized(client,db):
    headers,profile=_profile(client,db,uuid.uuid4())
    response=client.patch("/api/v1/me/profile",headers=headers,json={"display_name":"  Road   Scout  "})
    assert response.status_code==200
    body=response.json();assert body["display_name"]=="Road Scout";assert body["member_id"].startswith("AR-");assert body["id"]==str(profile.id)
    assert client.get("/api/v1/me/profile",headers=headers).json()["display_name"]=="Road Scout"
    assert client.patch("/api/v1/me/profile",headers=headers,json={"display_name":"x"}).status_code==422
    assert client.patch("/api/v1/me/profile",headers=headers,json={"display_name":"x"*31}).status_code==422


def test_my_contributions_is_private_and_reports_fuel_results(client,db):
    owner_headers,owner=_profile(client,db,uuid.uuid4());other_headers,_=_profile(client,db,uuid.uuid4());station=_station(db,"NPD Test")
    sub,_=_contribution(db,owner,station)
    db.add(SubmissionFuelResult(submission_id=sub.id,station_id=station.id,fuel_type=FuelType.PETROL_91,previous_price=Decimal("2.500"),submitted_price=Decimal("2.400"),final_price=Decimal("2.400"),result="APPLIED",points=1))
    db.add(PointTransaction(user_id=owner.id,submission_id=sub.id,station_id=station.id,fuel_type=FuelType.PETROL_91,points=1,reason="FIRST_ACCEPTED_PRICE_UPDATE"));db.commit()
    listing=client.get("/api/v1/me/contributions",headers=owner_headers);assert listing.status_code==200
    body=listing.json();assert body[0]["station"]["name"]=="NPD Test";assert body[0]["status"]=="APPLIED";assert body[0]["points"]==1;assert body[0]["fuel_results"][0]["result"]=="APPLIED"
    assert client.get(f"/api/v1/me/contributions/{sub.id}",headers=other_headers).status_code==404


def test_summary_and_region_leaderboard_use_public_display_names(client,db):
    first_headers,first=_profile(client,db,uuid.uuid4());second_headers,second=_profile(client,db,uuid.uuid4())
    first.display_name="Canterbury Scout";second.display_name="Otago Driver";db.commit()
    canterbury=_station(db,"Canterbury Station","Canterbury","Christchurch");otago=_station(db,"Otago Station","Otago","Queenstown")
    first_sub,_=_contribution(db,first,canterbury);second_sub,_=_contribution(db,second,otago)
    for fuel in (FuelType.PETROL_91,FuelType.PETROL_95):db.add(PointTransaction(user_id=first.id,submission_id=first_sub.id,station_id=canterbury.id,fuel_type=fuel,points=1,reason="FIRST_ACCEPTED_PRICE_UPDATE"))
    db.add(PointTransaction(user_id=second.id,submission_id=second_sub.id,station_id=otago.id,fuel_type=FuelType.DIESEL,points=1,reason="FIRST_ACCEPTED_PRICE_UPDATE"));db.commit()
    summary=client.get("/api/v1/me/contribution-summary",headers=first_headers).json();assert summary["total_points"]==2;assert summary["month_points"]==2
    board=client.get("/api/v1/leaderboard?period=all_time&scope=region&value=Canterbury",headers=first_headers);assert board.status_code==200
    data=board.json();assert len(data["entries"])==1;assert data["entries"][0]["display_name"]=="Canterbury Scout";assert data["entries"][0]["is_current_user"] is True;assert data["entries"][0]["points"]==2
    other_view=client.get("/api/v1/leaderboard?period=all_time&scope=region&value=Canterbury",headers=second_headers).json();assert other_view["entries"][0]["display_name"]=="Canterbury Scout";assert other_view["current_user"] is None
