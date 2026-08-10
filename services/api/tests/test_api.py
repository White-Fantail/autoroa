import uuid
import io
from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select
from app.models import Brand, FillUp, FuelType, MediaAsset, MediaType, OdometerReading, Observation, Profile, RateLimit, Receipt, ReceiptFingerprint, Station, Vehicle, Verification
from app.routes import enforce_expensive_limit
from PIL import Image
def jpeg_bytes(color="white"):
    output=io.BytesIO();Image.new("RGB",(4,4),color).save(output,"JPEG");return output.getvalue()
def png_bytes(color="white"):
    output=io.BytesIO();Image.new("RGB",(4,4),color).save(output,"PNG");return output.getvalue()
def upload_media(client,headers,kind="RECEIPT",content=None):
    content=content or jpeg_bytes();prepared=client.post("/api/v1/media/upload-url",json={"type":kind,"mime_type":"image/jpeg","file_size":len(content)},headers=headers).json();uploaded=client.put(prepared["upload_url"],content=content,headers={**headers,"content-type":"image/jpeg"});assert uploaded.status_code==204;return client.post("/api/v1/media/complete",json={"storage_token":prepared["storage_token"],"type":kind,"mime_type":"image/jpeg","file_size":len(content)},headers=headers)
def test_auth_required(client):assert client.get("/api/v1/me").status_code==401
def test_vehicle_crud_and_ownership(client,user_headers):
    data={"nickname":"RAV4","make":"Toyota","model":"RAV4","fuel_type":"PETROL_91"};created=client.post("/api/v1/vehicles",json=data,headers=user_headers);assert created.status_code==201;vehicle=created.json();assert vehicle["is_primary"]
    other={"Authorization":f"Bearer dev:{uuid.uuid4()}"};assert client.get(f"/api/v1/vehicles/{vehicle['id']}",headers=other).status_code==404
    assert client.patch(f"/api/v1/vehicles/{vehicle['id']}",json={"nickname":"Family car"},headers=user_headers).json()["nickname"]=="Family car"
    assert client.delete(f"/api/v1/vehicles/{vehicle['id']}",headers=user_headers).status_code==204
def test_admin_restricted(client,user_headers):assert client.get("/api/v1/admin/dashboard",headers=user_headers).status_code==403
def test_upload_intent_is_bound_and_single_use(client,user_headers):
    content=jpeg_bytes();prepared=client.post("/api/v1/media/upload-url",json={"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers).json();assert client.put(prepared["upload_url"],content=content,headers={**user_headers,"content-type":"image/jpeg"}).status_code==204;assert client.put(prepared["upload_url"],content=content,headers={**user_headers,"content-type":"image/jpeg"}).status_code==409
    wrong=client.post("/api/v1/media/complete",json={"storage_token":prepared["storage_token"],"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers);assert wrong.status_code==422
    body={"storage_token":prepared["storage_token"],"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)};assert client.post("/api/v1/media/complete",json=body,headers=user_headers).status_code==201;assert client.post("/api/v1/media/complete",json=body,headers=user_headers).status_code==409
def test_local_upload_rejects_body_larger_than_prepared_size(client,user_headers):
    from app.config import get_settings
    prepared=client.post("/api/v1/media/upload-url",json={"type":"ODOMETER","mime_type":"image/jpeg","file_size":4},headers=user_headers).json();response=client.put(prepared["upload_url"],content=b"12345",headers={**user_headers,"content-type":"image/jpeg"});assert response.status_code==422;assert not (get_settings().local_media_dir and (Path(get_settings().local_media_dir)/prepared["storage_path"]).exists())
def test_completion_before_upload_does_not_consume_intent(client,user_headers):
    content=jpeg_bytes();prepared=client.post("/api/v1/media/upload-url",json={"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers).json();body={"storage_token":prepared["storage_token"],"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(content)}
    assert client.post("/api/v1/media/complete",json=body,headers=user_headers).status_code==409
    assert client.put(prepared["upload_url"],content=content,headers={**user_headers,"content-type":"image/jpeg"}).status_code==204
    assert client.post("/api/v1/media/complete",json=body,headers=user_headers).status_code==201
def test_completion_metadata_mismatch_preserves_file_for_corrected_request(client,user_headers):
    from app.config import get_settings
    content=jpeg_bytes();prepared=client.post("/api/v1/media/upload-url",json={"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers).json();assert client.put(prepared["upload_url"],content=content,headers={**user_headers,"content-type":"image/jpeg"}).status_code==204
    path=Path(get_settings().local_media_dir)/prepared["storage_path"];wrong={"storage_token":prepared["storage_token"],"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)}
    assert client.post("/api/v1/media/complete",json=wrong,headers=user_headers).status_code==422;assert path.exists()
    corrected={**wrong,"type":"ODOMETER"};assert client.post("/api/v1/media/complete",json=corrected,headers=user_headers).status_code==201;assert path.exists()
def test_concurrent_local_completion_consumes_intent_once(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config import get_settings
    from app.db import Base,get_db
    from app.main import app
    database=tmp_path/"completion.db";engine=create_engine(f"sqlite:///{database}",connect_args={"check_same_thread":False,"timeout":10});Base.metadata.create_all(engine);sessions=sessionmaker(engine,expire_on_commit=False)
    monkeypatch.setenv("APP_ENV","test");monkeypatch.setenv("LOCAL_MEDIA_DIR",str(tmp_path/"media"));monkeypatch.delenv("SUPABASE_URL",raising=False);monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY",raising=False);get_settings.cache_clear()
    def override():
        with sessions() as session:yield session
    app.dependency_overrides[get_db]=override;headers={"Authorization":f"Bearer dev:{uuid.uuid4()}"};content=jpeg_bytes()
    try:
        with TestClient(app) as setup:
            prepared=setup.post("/api/v1/media/upload-url",json={"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(content)},headers=headers).json();assert setup.put(prepared["upload_url"],content=content,headers={**headers,"content-type":"image/jpeg"}).status_code==204
        body={"storage_token":prepared["storage_token"],"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(content)}
        def complete(_):
            with TestClient(app) as race:return race.post("/api/v1/media/complete",json=body,headers=headers)
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(complete,range(2)))
        assert sorted(response.status_code for response in responses)==[201,409]
        with sessions() as session:assert session.scalar(select(func.count(MediaAsset.id)))==1
    finally:app.dependency_overrides.clear();engine.dispose();get_settings.cache_clear()
def test_media_metadata_is_owned(client,user_headers):
    media=upload_media(client,user_headers,"ODOMETER").json()
    assert client.get(f"/api/v1/media/{media['id']}",headers=user_headers).json()["type"]=="ODOMETER"
    assert client.get(f"/api/v1/media/{media['id']}",headers={"Authorization":f"Bearer dev:{uuid.uuid4()}"}).status_code==404
def test_development_limiter_enforces_bound(db):
    user=uuid.uuid4();enforce_expensive_limit(db,user,"test",2);enforce_expensive_limit(db,user,"test",2)
    try:enforce_expensive_limit(db,user,"test",2)
    except Exception as exc:assert getattr(exc,"status_code",None)==429
    else:raise AssertionError("rate limit was not enforced")
    assert db.scalar(select(RateLimit).where(RateLimit.key==f"test:{user}")) is not None
def test_receipt_cannot_verify_modified_fillup(client,user_headers,db):
    station=Station(name="Test Station",address_line="1 Test Street",city="Christchurch",latitude=Decimal("-43.5"),longitude=Decimal("172.6"));db.add(station);db.commit();vehicle=client.post("/api/v1/vehicles",json={"nickname":"Car","make":"Test","model":"One","fuel_type":"PETROL_91"},headers=user_headers).json();media=upload_media(client,user_headers).json();receipt=client.post("/api/v1/receipts",json={"media_asset_id":media["id"]},headers=user_headers).json();client.post(f"/api/v1/receipts/{receipt['id']}/process",headers=user_headers);when=datetime.now(timezone.utc).isoformat();client.post(f"/api/v1/receipts/{receipt['id']}/confirm",json={"station_id":str(station.id),"fuel_type":"PETROL_91","litres":"42.3","pump_price_per_litre":"2.239","total_amount":"94.71","transaction_datetime":when},headers=user_headers)
    created=client.post("/api/v1/fill-ups",json={"vehicle_id":vehicle["id"],"station_id":str(station.id),"occurred_at":when,"fuel_type":"PETROL_91","litres":"42.3","pump_price_per_litre":"3.999","total_amount":"94.71","odometer_km":80000,"receipt_id":receipt["id"],"acknowledge_arithmetic_warning":True},headers=user_headers);assert created.status_code==201
    observation=db.scalar(select(Observation));db.refresh(observation);assert observation.verification_level==Verification.USER_CONFIRMED;assert observation.receipt_id is None
def test_verified_receipt_fillup_is_idempotent(client,user_headers,db):
    station=Station(name="Verified",address_line="1 Fuel Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit();vehicle=client.post("/api/v1/vehicles",json={"nickname":"Car","make":"Test","model":"One","fuel_type":"PETROL_91"},headers=user_headers).json();media=upload_media(client,user_headers).json();receipt=client.post("/api/v1/receipts",json={"media_asset_id":media["id"]},headers=user_headers).json();client.post(f"/api/v1/receipts/{receipt['id']}/process",headers=user_headers);when=datetime.now(timezone.utc).isoformat();confirmed={"station_id":str(station.id),"fuel_type":"PETROL_91","litres":"40","pump_price_per_litre":"2.2","total_amount":"88","transaction_datetime":when};assert client.post(f"/api/v1/receipts/{receipt['id']}/confirm",json=confirmed,headers=user_headers).status_code==200
    payload={"vehicle_id":vehicle["id"],"station_id":str(station.id),"occurred_at":when,"fuel_type":"PETROL_91","litres":"40","pump_price_per_litre":"2.2","total_amount":"88","odometer_km":80000,"receipt_id":receipt["id"]};first=client.post("/api/v1/fill-ups",json=payload,headers=user_headers);second=client.post("/api/v1/fill-ups",json=payload,headers=user_headers);assert first.status_code==201;assert second.json()["id"]==first.json()["id"]
    observation=db.scalar(select(Observation));db.refresh(observation);assert observation.verification_level==Verification.VERIFIED_RECEIPT
    other={"Authorization":f"Bearer dev:{uuid.uuid4()}"};public=client.get("/api/v1/fuel-prices/nearby?latitude=-36.85&longitude=174.76&radius_km=5&fuel_type=PETROL_91",headers=other);assert public.status_code==200;assert public.json()[0]["verification_level"]=="VERIFIED_RECEIPT";assert "receipt_id" not in public.text and "user_id" not in public.text
def test_nearby_and_admin_endpoints_are_privacy_scoped(client,user_headers,db):
    brand=Brand(name="Test Fuel",slug="test-fuel");db.add(brand);db.flush();station=Station(brand_id=brand.id,name="Public Test",address_line="2 Test Street",city="Christchurch",latitude=Decimal("-43.5"),longitude=Decimal("172.6"));db.add(station);db.commit();response=client.get("/api/v1/fuel-stations/nearby?latitude=-43.5&longitude=172.6",headers=user_headers);assert response.status_code==200;assert response.json()[0]["station"]["name"]=="Public Test";assert "user_id" not in response.text
    admin={"Authorization":user_headers["Authorization"]+":admin"};assert client.get("/api/v1/admin/users",headers=admin).status_code==200;assert client.get(f"/api/v1/admin/brands/{brand.id}",headers=admin).json()["name"]=="Test Fuel";assert client.get(f"/api/v1/admin/stations/{station.id}",headers=admin).json()["name"]=="Public Test";assert client.patch(f"/api/v1/admin/stations/{station.id}?name=Renamed",headers=admin).json()["name"]=="Renamed"
def test_fillup_reference_and_timestamp_validation(client,user_headers):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"Car","make":"Test","model":"One","fuel_type":"PETROL_91"},headers=user_headers).json();payload={"vehicle_id":vehicle["id"],"occurred_at":"2026-01-01T12:00:00","fuel_type":"PETROL_91","litres":"40","total_amount":"90","odometer_km":100};assert client.post("/api/v1/fill-ups",json=payload,headers=user_headers).status_code==422;payload["occurred_at"]=datetime.now(timezone.utc).isoformat();payload["station_id"]=str(uuid.uuid4());assert client.post("/api/v1/fill-ups",json=payload,headers=user_headers).status_code==422
def test_fillup_crud_and_ownership(client,user_headers):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"CRUD","make":"Test","model":"Car","fuel_type":"DIESEL"},headers=user_headers).json();payload={"vehicle_id":vehicle["id"],"occurred_at":datetime.now(timezone.utc).isoformat(),"fuel_type":"DIESEL","litres":"50","pump_price_per_litre":"2","total_amount":"100","odometer_km":5000};created=client.post("/api/v1/fill-ups",json=payload,headers=user_headers);assert created.status_code==201;item=created.json();assert client.get(f"/api/v1/fill-ups/{item['id']}",headers=user_headers).status_code==200;assert len(client.get(f"/api/v1/fill-ups?vehicle_id={vehicle['id']}",headers=user_headers).json())==1
    other={"Authorization":f"Bearer dev:{uuid.uuid4()}"};assert client.get(f"/api/v1/fill-ups/{item['id']}",headers=other).status_code==404;updated=client.patch(f"/api/v1/fill-ups/{item['id']}",json={"notes":"edited","total_amount":"105"},headers=user_headers);assert updated.json()["notes"]=="edited";assert client.delete(f"/api/v1/fill-ups/{item['id']}",headers=user_headers).status_code==204;assert client.get(f"/api/v1/fill-ups/{item['id']}",headers=user_headers).status_code==404

def test_weighted_metrics_and_backdated_partial_recalculation(client,user_headers):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"Metrics","make":"Test","model":"Car","fuel_type":"DIESEL"},headers=user_headers).json();base=datetime.now(timezone.utc)-timedelta(days=4)
    def add(days,odo,litres,total,full=True):
        payload={"vehicle_id":vehicle["id"],"occurred_at":(base+timedelta(days=days)).isoformat(),"fuel_type":"DIESEL","litres":str(litres),"total_amount":str(total),"odometer_km":odo,"full_tank":full}
        response=client.post("/api/v1/fill-ups?confirm_lower_odometer=true",json=payload,headers=user_headers);assert response.status_code==201;return response.json()
    first=add(0,1000,20,40);second=add(2,1100,5,10);third=add(3,2000,90,180)
    metrics=client.get(f"/api/v1/vehicles/{vehicle['id']}/metrics?period=all",headers=user_headers).json();assert metrics["average_fuel_economy_l_per_100km"]=="9.500";assert metrics["average_cost_per_100km"]=="19.00"
    partial=add(1,1050,10,20,False);third=client.get(f"/api/v1/fill-ups/{third['id']}",headers=user_headers).json();assert third["fuel_economy_l_per_100km"]=="10.000"
    second=client.get(f"/api/v1/fill-ups/{second['id']}",headers=user_headers).json();assert second["fuel_economy_l_per_100km"]=="15.000"
    assert client.delete(f"/api/v1/fill-ups/{partial['id']}",headers=user_headers).status_code==204
    second=client.get(f"/api/v1/fill-ups/{second['id']}",headers=user_headers).json();assert second["fuel_economy_l_per_100km"]=="5.000"

def test_fillup_sanity_requires_explicit_acknowledgements(client,user_headers):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"Warnings","make":"Test","model":"Car","fuel_type":"PETROL_91","tank_capacity_litres":"50"},headers=user_headers).json();payload={"vehicle_id":vehicle["id"],"occurred_at":datetime.now(timezone.utc).isoformat(),"fuel_type":"DIESEL","litres":"70","pump_price_per_litre":"2","total_amount":"20","odometer_km":100}
    assert client.post("/api/v1/fill-ups",json=payload,headers=user_headers).status_code==409
    payload.update(acknowledge_fuel_type_mismatch=True,acknowledge_tank_capacity=True,acknowledge_arithmetic_warning=True)
    assert client.post("/api/v1/fill-ups",json=payload,headers=user_headers).status_code==201

def test_deleting_old_middle_and_latest_fillups_recalculates_remaining_economy(client,user_headers):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"Delete","make":"Test","model":"Car","fuel_type":"DIESEL"},headers=user_headers).json();base=datetime.now(timezone.utc)-timedelta(days=10)
    def add(day,odometer):
        response=client.post("/api/v1/fill-ups",json={"vehicle_id":vehicle["id"],"occurred_at":(base+timedelta(days=day)).isoformat(),"fuel_type":"DIESEL","litres":"20","total_amount":"40","odometer_km":odometer},headers=user_headers);assert response.status_code==201;return response.json()["id"]
    first,second,middle,latest=[add(day,1000+day*100) for day in (0,2,4,6)]
    assert client.delete(f"/api/v1/fill-ups/{middle}",headers=user_headers).status_code==204
    recalculated=client.get(f"/api/v1/fill-ups/{latest}",headers=user_headers).json();assert recalculated["distance_since_previous_km"]==400;assert recalculated["fuel_economy_l_per_100km"]=="5.000"
    assert client.delete(f"/api/v1/fill-ups/{first}",headers=user_headers).status_code==204
    new_baseline=client.get(f"/api/v1/fill-ups/{second}",headers=user_headers).json();assert new_baseline["distance_since_previous_km"] is None;assert new_baseline["fuel_economy_l_per_100km"] is None
    assert client.delete(f"/api/v1/fill-ups/{latest}",headers=user_headers).status_code==204
    metrics=client.get(f"/api/v1/vehicles/{vehicle['id']}/metrics?period=all",headers=user_headers).json();assert metrics["fill_up_count"]==1;assert metrics["average_fuel_economy_l_per_100km"] is None

def test_metrics_exclude_interval_opened_before_period(client,user_headers):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"Period","make":"Test","model":"Car","fuel_type":"DIESEL"},headers=user_headers).json();now=datetime.now(timezone.utc)
    common={"vehicle_id":vehicle["id"],"fuel_type":"DIESEL","total_amount":"100","litres":"50"}
    assert client.post("/api/v1/fill-ups",json={**common,"occurred_at":(now-timedelta(days=31)).isoformat(),"odometer_km":1000},headers=user_headers).status_code==201
    assert client.post("/api/v1/fill-ups",json={**common,"occurred_at":(now-timedelta(days=1)).isoformat(),"odometer_km":1500},headers=user_headers).status_code==201
    metrics=client.get(f"/api/v1/vehicles/{vehicle['id']}/metrics?period=30d",headers=user_headers).json();assert metrics["average_fuel_economy_l_per_100km"] is None;assert metrics["distance_km"]==500

def test_backdated_fillup_uses_chronological_neighbors(client,user_headers):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"Backdated","make":"Test","model":"Car","fuel_type":"DIESEL"},headers=user_headers).json();base=datetime.now(timezone.utc)-timedelta(days=10);common={"vehicle_id":vehicle["id"],"fuel_type":"DIESEL","litres":40,"total_amount":80}
    for day,odometer in [(0,10000),(9,10500)]:assert client.post("/api/v1/fill-ups",json={**common,"occurred_at":(base+timedelta(days=day)).isoformat(),"odometer_km":odometer},headers=user_headers).status_code==201
    valid=client.post("/api/v1/fill-ups",json={**common,"occurred_at":(base+timedelta(days=4)).isoformat(),"odometer_km":10250},headers=user_headers);assert valid.status_code==201
    assert client.post("/api/v1/fill-ups",json={**common,"occurred_at":(base+timedelta(days=3)).isoformat(),"odometer_km":9900},headers=user_headers).status_code==409
    assert client.post("/api/v1/fill-ups",json={**common,"occurred_at":(base+timedelta(days=5)).isoformat(),"odometer_km":10700},headers=user_headers).status_code==409

def test_backdated_sequence_validation_is_not_limited_to_latest_hundred(client,user_headers,db):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"Long history","make":"Test","model":"Car","fuel_type":"DIESEL"},headers=user_headers).json();profile_id=client.get("/api/v1/me",headers=user_headers).json()["id"];base=datetime.now(timezone.utc)-timedelta(days=200)
    db.add_all([FillUp(user_id=uuid.UUID(profile_id),vehicle_id=uuid.UUID(vehicle["id"]),occurred_at=base+timedelta(days=day),fuel_type=FuelType.DIESEL,litres=Decimal("20"),total_amount=Decimal("40"),odometer_km=1000+day*10) for day in range(101)]);db.commit()
    response=client.post("/api/v1/fill-ups",json={"vehicle_id":vehicle["id"],"occurred_at":(base+timedelta(hours=12)).isoformat(),"fuel_type":"DIESEL","litres":20,"total_amount":40,"odometer_km":900},headers=user_headers);assert response.status_code==409

def test_patch_odometer_neighbors_require_confirmation_and_recalculate(client,user_headers):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"Patch sequence","make":"Test","model":"Car","fuel_type":"DIESEL"},headers=user_headers).json();base=datetime.now(timezone.utc)-timedelta(days=5);common={"vehicle_id":vehicle["id"],"fuel_type":"DIESEL","litres":20,"total_amount":40};ids=[]
    for day,odometer in [(0,1000),(2,1200),(4,1400)]:ids.append(client.post("/api/v1/fill-ups",json={**common,"occurred_at":(base+timedelta(days=day)).isoformat(),"odometer_km":odometer},headers=user_headers).json()["id"])
    assert client.patch(f"/api/v1/fill-ups/{ids[1]}",json={"occurred_at":(base+timedelta(days=1)).isoformat(),"odometer_km":1100},headers=user_headers).status_code==200
    assert client.patch(f"/api/v1/fill-ups/{ids[1]}",json={"odometer_km":1500},headers=user_headers).status_code==409
    confirmed=client.patch(f"/api/v1/fill-ups/{ids[1]}?confirm_lower_odometer=true",json={"odometer_km":1500},headers=user_headers);assert confirmed.status_code==200
    last=client.get(f"/api/v1/fill-ups/{ids[2]}",headers=user_headers).json();assert last["economy_warning"]=="NON_INCREASING_ODOMETER";assert last["fuel_economy_l_per_100km"] is None

def test_patch_reorders_and_recalculates_entire_history(client,user_headers):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"Edit chain","make":"Test","model":"Car","fuel_type":"DIESEL"},headers=user_headers).json();base=datetime.now(timezone.utc)-timedelta(days=4);ids=[]
    for day,odo,litres in [(0,1000,20),(2,1200,20),(3,1400,20)]:
        response=client.post("/api/v1/fill-ups",json={"vehicle_id":vehicle["id"],"fuel_type":"DIESEL","occurred_at":(base+timedelta(days=day)).isoformat(),"odometer_km":odo,"litres":litres,"total_amount":40},headers=user_headers);assert response.status_code==201;ids.append(response.json()["id"])
    changed=client.patch(f"/api/v1/fill-ups/{ids[1]}",json={"occurred_at":(base+timedelta(days=1)).isoformat(),"litres":30,"full_tank":False},headers=user_headers);assert changed.status_code==200
    last=client.get(f"/api/v1/fill-ups/{ids[2]}",headers=user_headers).json();assert last["distance_since_previous_km"]==400;assert last["fuel_economy_l_per_100km"]=="12.500"
    broken=client.patch(f"/api/v1/fill-ups/{ids[1]}",json={"missed_previous_fill":True},headers=user_headers);assert broken.status_code==200
    last=client.get(f"/api/v1/fill-ups/{ids[2]}",headers=user_headers).json();assert last["economy_warning"]=="MISSED_FILL_CHAIN"

def test_receipt_fingerprint_is_cross_account_generic_and_survives_deletion(client,user_headers,db):
    def receipt(headers):
        media=upload_media(client,headers).json();return client.post("/api/v1/receipts",json={"media_asset_id":media["id"]},headers=headers).json()
    first=receipt(user_headers);assert client.post(f"/api/v1/receipts/{first['id']}/process",headers=user_headers).json()["processing_status"] in {"READY","REVIEW_REQUIRED"};assert db.scalar(select(ReceiptFingerprint))
    assert client.delete("/api/v1/me",headers=user_headers).status_code==204;assert db.scalar(select(ReceiptFingerprint))
    other={"Authorization":f"Bearer dev:{uuid.uuid4()}"};duplicate=upload_media(client,other);assert duplicate.status_code==409

def test_local_upload_rejects_invalid_expired_and_wrong_owner(client,user_headers,db):
    invalid=b"not an image";prepared=client.post("/api/v1/media/upload-url",json={"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(invalid)},headers=user_headers).json();assert client.put(prepared["upload_url"],content=invalid,headers={**user_headers,"content-type":"image/jpeg"}).status_code==204
    completed=client.post("/api/v1/media/complete",json={"storage_token":prepared["storage_token"],"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(invalid)},headers=user_headers);assert completed.status_code==422
    from app.config import get_settings
    assert not (Path(get_settings().local_media_dir)/prepared["storage_path"]).exists()
    from app.models import UploadIntent
    intent=db.get(UploadIntent,uuid.UUID(prepared["storage_token"]));intent.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    assert client.put(prepared["upload_url"],content=invalid,headers={**user_headers,"content-type":"image/jpeg"}).status_code==409
    other={"Authorization":f"Bearer dev:{uuid.uuid4()}"};assert client.put(prepared["upload_url"],content=invalid,headers={**other,"content-type":"image/jpeg"}).status_code==409

def test_local_completion_removes_mime_mismatch_without_touching_other_intent(client,user_headers):
    from app.config import get_settings
    mismatched=png_bytes();other_content=jpeg_bytes("black");root=Path(get_settings().local_media_dir);other_headers={"Authorization":f"Bearer dev:{uuid.uuid4()}"}
    rejected=client.post("/api/v1/media/upload-url",json={"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(mismatched)},headers=user_headers).json();preserved=client.post("/api/v1/media/upload-url",json={"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(other_content)},headers=other_headers).json()
    assert client.put(rejected["upload_url"],content=mismatched,headers={**user_headers,"content-type":"image/jpeg"}).status_code==204
    assert client.put(preserved["upload_url"],content=other_content,headers={**other_headers,"content-type":"image/jpeg"}).status_code==204
    response=client.post("/api/v1/media/complete",json={"storage_token":rejected["storage_token"],"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(mismatched)},headers=user_headers)
    assert response.status_code==422;assert not (root/rejected["storage_path"]).exists();assert (root/preserved["storage_path"]).exists()

def test_duplicate_local_receipt_removes_new_upload(client,user_headers):
    from app.config import get_settings
    content=jpeg_bytes();assert upload_media(client,user_headers,"RECEIPT",content).status_code==201
    duplicate=client.post("/api/v1/media/upload-url",json={"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers).json();assert client.put(duplicate["upload_url"],content=content,headers={**user_headers,"content-type":"image/jpeg"}).status_code==204
    response=client.post("/api/v1/media/complete",json={"storage_token":duplicate["storage_token"],"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers)
    assert response.status_code==409;assert not (Path(get_settings().local_media_dir)/duplicate["storage_path"]).exists()

def test_valid_local_receipt_and_odometer_survive_completion_and_processing(client,user_headers):
    receipt_media=upload_media(client,user_headers,"RECEIPT");assert receipt_media.status_code==201
    receipt=client.post("/api/v1/receipts",json={"media_asset_id":receipt_media.json()["id"]},headers=user_headers).json();assert client.post(f"/api/v1/receipts/{receipt['id']}/process",headers=user_headers).json()["processing_status"] in {"READY","REVIEW_REQUIRED"}
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"OCR","make":"Test","model":"Car","fuel_type":"DIESEL"},headers=user_headers).json();odometer_media=upload_media(client,user_headers,"ODOMETER");assert odometer_media.status_code==201
    odometer=client.post("/api/v1/odometer-readings",json={"vehicle_id":vehicle["id"],"media_asset_id":odometer_media.json()["id"]},headers=user_headers).json();assert client.post(f"/api/v1/odometer-readings/{odometer['id']}/process",headers=user_headers).json()["processing_status"] in {"READY","REVIEW_REQUIRED"}

def test_account_deletion_removes_completed_and_incomplete_local_uploads(client,user_headers):
    from app.config import get_settings
    completed=upload_media(client,user_headers,"ODOMETER");assert completed.status_code==201
    content=jpeg_bytes("black");pending=client.post("/api/v1/media/upload-url",json={"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers).json();assert client.put(pending["upload_url"],content=content,headers={**user_headers,"content-type":"image/jpeg"}).status_code==204
    root=Path(get_settings().local_media_dir);paths=[root/completed.json()["storage_path"],root/pending["storage_path"]];assert all(path.exists() for path in paths);assert client.delete("/api/v1/me",headers=user_headers).status_code==204;assert all(not path.exists() for path in paths)

def test_non_development_never_falls_back_to_local_storage(db,tmp_path,monkeypatch):
    from app.config import get_settings
    from app.auth import Principal
    from app.routes import local_media_enabled,prepare_media
    from app.schemas import MediaPrepare
    local=tmp_path/"must-not-exist";monkeypatch.setenv("APP_ENV","staging");monkeypatch.setenv("AUTH_MODE","supabase");monkeypatch.setenv("LOCAL_MEDIA_DIR",str(local));monkeypatch.delenv("SUPABASE_URL",raising=False);monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY",raising=False);get_settings.cache_clear();assert local_media_enabled() is False
    profile=Profile(auth_user_id="non-development");db.add(profile);db.commit()
    with pytest.raises(Exception) as error:prepare_media(MediaPrepare(type=MediaType.RECEIPT,mime_type="image/jpeg",file_size=10),Principal(profile),db)
    assert getattr(error.value,"status_code",None)==503;assert not local.exists()
    get_settings.cache_clear()

def test_invalid_legacy_media_is_rejected_before_mock_ocr(client,user_headers,monkeypatch):
    media=upload_media(client,user_headers).json();receipt=client.post("/api/v1/receipts",json={"media_asset_id":media["id"]},headers=user_headers).json();monkeypatch.setattr("app.routes.media_bytes",lambda media:b"not an image")
    result=client.post(f"/api/v1/receipts/{receipt['id']}/process",headers=user_headers).json();assert result["processing_status"]=="FAILED"

def test_concurrent_legacy_duplicate_processing_has_one_controlled_loser(tmp_path,monkeypatch):
    import io,threading
    from fastapi.testclient import TestClient
    from PIL import Image
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base,get_db
    from app.main import app
    import app.routes as routes
    engine=create_engine(f"sqlite:///{tmp_path/'race.db'}",connect_args={"check_same_thread":False});Base.metadata.create_all(engine);sessions=sessionmaker(engine,expire_on_commit=False)
    def override():
        with sessions() as session:yield session
    app.dependency_overrides[get_db]=override;output=io.BytesIO();Image.new("RGB",(4,4),"white").save(output,"JPEG");monkeypatch.setattr(routes,"media_bytes",lambda media:output.getvalue());original=routes.validate_image_content;barrier=threading.Barrier(2)
    def synchronized_validation(*args,**kwargs):
        result=original(*args,**kwargs);barrier.wait(timeout=5);return result
    monkeypatch.setattr(routes,"validate_image_content",synchronized_validation)
    def make(headers):
        with TestClient(app) as race_client:
            profile=race_client.get("/api/v1/me",headers=headers).json()
            with sessions() as session:
                media=MediaAsset(user_id=uuid.UUID(profile["id"]),type=MediaType.RECEIPT,storage_bucket="legacy",storage_path=f"legacy/{uuid.uuid4()}",mime_type="image/jpeg",file_size=len(jpeg_bytes()));session.add(media);session.flush();receipt=Receipt(user_id=uuid.UUID(profile["id"]),media_asset_id=media.id);session.add(receipt);session.commit();return receipt.id
    headers=[{"Authorization":f"Bearer dev:{uuid.uuid4()}"} for _ in range(2)];receipts=[make(headers[index]) for index in range(2)]
    def process(index):
        with TestClient(app) as race_client:return race_client.post(f"/api/v1/receipts/{receipts[index]}/process",headers=headers[index])
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(process,range(2)))
        payloads=[response.json() for response in results];assert all(response.status_code==200 for response in results);assert sum(payload["processing_status"] in {"READY","REVIEW_REQUIRED"} for payload in payloads)==1;assert sum(payload["processing_status"]=="FAILED" and payload["error_code"]=="RECEIPT_PROCESSING_FAILED" and payload["error_message"]=="We couldn't read this receipt." for payload in payloads)==1
        with sessions() as session:assert session.scalar(select(func.count(ReceiptFingerprint.content_sha256)))==1
    finally:app.dependency_overrides.clear();engine.dispose()

def test_database_rejects_equal_vehicle_timestamp(db):
    from app.models import Profile, Vehicle, FuelType
    profile=Profile(auth_user_id="constraint-owner");db.add(profile);db.flush();vehicle=Vehicle(user_id=profile.id,nickname="Constraint",make="Test",model="Car",fuel_type=FuelType.DIESEL);db.add(vehicle);db.flush();when=datetime.now(timezone.utc)
    values={"user_id":profile.id,"vehicle_id":vehicle.id,"occurred_at":when,"fuel_type":FuelType.DIESEL,"litres":Decimal("10"),"total_amount":Decimal("20"),"odometer_km":100}
    db.add(FillUp(**values));db.flush();db.add(FillUp(**values))
    with pytest.raises(IntegrityError):db.flush()

def test_database_rejects_cross_owner_receipt_media(db):
    first=Profile(auth_user_id="receipt-owner-a");second=Profile(auth_user_id="receipt-owner-b");db.add_all([first,second]);db.flush();media=MediaAsset(user_id=first.id,type=MediaType.RECEIPT,storage_path="a/receipt",mime_type="image/jpeg",file_size=1);db.add(media);db.flush();db.add(Receipt(user_id=second.id,media_asset_id=media.id))
    with pytest.raises(IntegrityError):db.flush()

def test_database_rejects_cross_owner_odometer_vehicle_and_media(db):
    first=Profile(auth_user_id="odo-owner-a");second=Profile(auth_user_id="odo-owner-b");db.add_all([first,second]);db.flush();vehicle=Vehicle(user_id=first.id,nickname="A",make="A",model="A",fuel_type=FuelType.DIESEL);media=MediaAsset(user_id=first.id,type=MediaType.ODOMETER,storage_path="a/odo",mime_type="image/jpeg",file_size=1);db.add_all([vehicle,media]);db.flush();db.add(OdometerReading(user_id=second.id,vehicle_id=vehicle.id,media_asset_id=media.id))
    with pytest.raises(IntegrityError):db.flush()

def test_database_rejects_cross_owner_fill_vehicle(db):
    first=Profile(auth_user_id="fill-owner-a");second=Profile(auth_user_id="fill-owner-b");db.add_all([first,second]);db.flush();vehicle=Vehicle(user_id=first.id,nickname="A",make="A",model="A",fuel_type=FuelType.DIESEL);db.add(vehicle);db.flush();db.add(FillUp(user_id=second.id,vehicle_id=vehicle.id,occurred_at=datetime.now(timezone.utc),fuel_type=FuelType.DIESEL,litres=Decimal("10"),total_amount=Decimal("20"),odometer_km=1))
    with pytest.raises(IntegrityError):db.flush()
