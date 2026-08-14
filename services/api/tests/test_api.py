import uuid
import io
import httpx
from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from app.models import Brand, CurrentPrice, FillUp, FuelType, MediaAsset, MediaType, OCRJob, OdometerReading, Observation, Profile, RateLimit, Receipt, ReceiptFingerprint, Source, Station, Status, UploadIntent, Vehicle, Verification
from app.routes import enforce_expensive_limit, process_ocr_jobs, run_ocr_job
from app.config import get_settings
from PIL import Image
def jpeg_bytes(color="white"):
    output=io.BytesIO();Image.new("RGB",(4,4),color).save(output,"JPEG");return output.getvalue()
def png_bytes(color="white"):
    output=io.BytesIO();Image.new("RGB",(4,4),color).save(output,"PNG");return output.getvalue()
def upload_media(client,headers,kind="RECEIPT",content=None):
    content=content or jpeg_bytes();prepared=client.post("/api/v1/media/upload-url",json={"type":kind,"mime_type":"image/jpeg","file_size":len(content)},headers=headers).json();uploaded=client.put(prepared["upload_url"],content=content,headers={**headers,"content-type":"image/jpeg"});assert uploaded.status_code==204;return client.post("/api/v1/media/complete",json={"storage_token":prepared["storage_token"],"type":kind,"mime_type":"image/jpeg","file_size":len(content)},headers=headers)
def test_auth_required(client):assert client.get("/api/v1/me").status_code==401
def test_admin_observations_include_station_name(client,db):
    admin_headers={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"};station=Station(name="Central Station",address_line="1 Fuel Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.flush();observation=Observation(station_id=station.id,fuel_type=FuelType.PETROL_91,pump_price_per_litre=Decimal("2.499"),source=Source.ADMIN,verification_level=Verification.USER_CONFIRMED,observed_at=datetime.now(timezone.utc),confidence_score=Decimal("1"));db.add(observation);db.commit()
    response=client.get("/api/v1/admin/observations",headers=admin_headers);assert response.status_code==200;row=response.json()[0];assert row["station_name"]=="Central Station";assert row["station_id"]==str(station.id);assert row["pump_price_per_litre"]=="2.4990"
def test_receipt_ocr_job_auto_applies_high_confidence_result(client,user_headers,db):
    media=upload_media(client,user_headers).json();receipt=client.post("/api/v1/receipts",json={"media_asset_id":media["id"]},headers=user_headers).json()
    queued=client.post("/api/v1/ocr-jobs",json={"kind":"RECEIPT","resource_id":receipt["id"]},headers=user_headers);assert queued.status_code==202;job=queued.json()
    assert process_ocr_jobs(db.get_bind())==1
    job=client.get(f"/api/v1/ocr-jobs/{job['id']}",headers=user_headers).json()
    assert job["status"]=="READY";assert job["requires_confirmation"] is False;assert job["applied_at"] is not None
    assert client.get(f"/api/v1/receipts/{receipt['id']}",headers=user_headers).json()["processing_status"]=="CONFIRMED"
def test_ocr_enqueue_is_idempotent_and_stale_job_is_recovered(client,user_headers,db):
    media=upload_media(client,user_headers).json();receipt=client.post("/api/v1/receipts",json={"media_asset_id":media["id"]},headers=user_headers).json();payload={"kind":"RECEIPT","resource_id":receipt["id"]}
    first=client.post("/api/v1/ocr-jobs",json=payload,headers=user_headers).json();second=client.post("/api/v1/ocr-jobs",json=payload,headers=user_headers).json();assert second["id"]==first["id"]
    job=db.get(OCRJob,uuid.UUID(first["id"]));job.status=Status.PROCESSING;job.started_at=datetime.now(timezone.utc)-timedelta(minutes=6);db.commit();assert process_ocr_jobs(db.get_bind())==1
    db.refresh(job);assert job.status==Status.READY
    completed=client.post("/api/v1/ocr-jobs",json=payload,headers=user_headers).json();assert completed["id"]==first["id"]
def test_reclaimed_job_fences_old_worker_after_provider_returns(client,user_headers,db,monkeypatch):
    media=upload_media(client,user_headers).json();receipt=client.post("/api/v1/receipts",json={"media_asset_id":media["id"]},headers=user_headers).json();queued=client.post("/api/v1/ocr-jobs",json={"kind":"RECEIPT","resource_id":receipt["id"]},headers=user_headers).json();job=db.get(OCRJob,uuid.UUID(queued["id"]));old_token=uuid.uuid4();new_token=uuid.uuid4();job.status=Status.PROCESSING;job.claim_token=old_token;job.started_at=datetime.now(timezone.utc)-timedelta(minutes=6);db.commit()
    original=__import__("app.services",fromlist=["MockOCRProvider"]).MockOCRProvider.extract_receipt
    def lose_claim(provider,path):
        with Session(bind=db.get_bind()) as competing:competing.execute(update(OCRJob).where(OCRJob.id==job.id,OCRJob.claim_token==old_token).values(claim_token=new_token,started_at=datetime.now(timezone.utc)));competing.commit()
        return original(provider,path)
    monkeypatch.setattr("app.routes.MockOCRProvider.extract_receipt",lose_claim);run_ocr_job(job.id,old_token,db.get_bind());db.expire_all();job=db.get(OCRJob,job.id);stored=db.get(Receipt,uuid.UUID(receipt["id"]));assert job.status==Status.PROCESSING and job.claim_token==new_token and job.completed_at is None;assert stored.processing_status==Status.UPLOADED and stored.raw_result_json is None
def test_fillup_confirms_low_confidence_odometer_job(client,user_headers,db):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"Queue car","make":"Test","model":"One","fuel_type":"PETROL_91"},headers=user_headers).json();media=upload_media(client,user_headers,"ODOMETER").json();reading=client.post("/api/v1/odometer-readings",json={"vehicle_id":vehicle["id"],"media_asset_id":media["id"]},headers=user_headers).json();queued=client.post("/api/v1/ocr-jobs",json={"kind":"ODOMETER","resource_id":reading["id"]},headers=user_headers).json();job=db.get(OCRJob,uuid.UUID(queued["id"]));job.status=Status.REVIEW_REQUIRED;job.confidence=Decimal(".60");job.requires_confirmation=True;db.commit()
    payload={"vehicle_id":vehicle["id"],"occurred_at":datetime.now(timezone.utc).isoformat(),"fuel_type":"PETROL_91","litres":"40","pump_price_per_litre":"2.2","total_amount":"88","odometer_km":12345,"odometer_image_id":media["id"],"full_tank":True,"missed_previous_fill":False};assert client.post("/api/v1/fill-ups",json=payload,headers=user_headers).status_code==201
    db.refresh(job);assert job.status==Status.CONFIRMED and job.applied_at is not None
def test_high_confidence_price_board_autoapplies_and_job_is_isolated(client,db):
    admin={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"};other={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"};station=Station(name="Queue Station",address_line="1 Queue Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit();media=upload_media(client,admin,"OTHER").json();queued=client.post("/api/v1/ocr-jobs",json={"kind":"PRICE_BOARD","resource_id":media["id"],"station_id":str(station.id)},headers=admin);assert queued.status_code==202;job_id=queued.json()["id"];assert client.get(f"/api/v1/ocr-jobs/{job_id}",headers=other).status_code==404
    assert process_ocr_jobs(db.get_bind())==1;job=client.get(f"/api/v1/ocr-jobs/{job_id}",headers=admin).json();assert job["status"]=="READY" and job["requires_confirmation"] is False
    rows=list(db.scalars(select(Observation).where(Observation.media_asset_id==uuid.UUID(media["id"]))));assert len(rows)==2 and {row.station_id for row in rows}=={station.id}
def test_unassigned_price_board_never_autoapplies_and_can_be_assigned_on_confirmation(client,db):
    admin={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"};station=Station(name="Later Station",address_line="4 Queue Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit();media=upload_media(client,admin,"OTHER").json()
    queued=client.post("/api/v1/ocr-jobs",json={"kind":"PRICE_BOARD","resource_id":media["id"]},headers=admin);assert queued.status_code==202;job_id=queued.json()["id"];assert process_ocr_jobs(db.get_bind())==1
    job=client.get(f"/api/v1/ocr-jobs/{job_id}",headers=admin).json();assert job["station_id"] is None and job["status"]=="REVIEW_REQUIRED" and job["requires_confirmation"] is True and job["applied_at"] is None;assert db.scalar(select(func.count(Observation.id)).where(Observation.media_asset_id==uuid.UUID(media["id"])))==0
    payload={"job_id":job_id,"media_asset_id":media["id"],"observed_at":datetime.now(timezone.utc).isoformat(),"prices":[{"fuel_type":"PETROL_91","price":"2.4"}]};assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json=payload,headers=admin).status_code==201
    stored=db.get(OCRJob,uuid.UUID(job_id));assert stored.station_id==station.id and stored.status==Status.CONFIRMED and stored.applied_at is not None
def test_unassigned_price_board_is_admin_only_and_confirmation_is_owner_scoped(client,user_headers,db):
    owner={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"};other={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"};station=Station(name="Scoped Station",address_line="5 Queue Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit();media=upload_media(client,owner,"OTHER").json();queued=client.post("/api/v1/ocr-jobs",json={"kind":"PRICE_BOARD","resource_id":media["id"]},headers=owner);assert queued.status_code==202;job_id=queued.json()["id"]
    assert client.post("/api/v1/ocr-jobs",json={"kind":"PRICE_BOARD","resource_id":media["id"]},headers=user_headers).status_code==403;assert client.get(f"/api/v1/ocr-jobs/{job_id}",headers=other).status_code==404;process_ocr_jobs(db.get_bind())
    payload={"job_id":job_id,"observed_at":datetime.now(timezone.utc).isoformat(),"prices":[{"fuel_type":"PETROL_91","price":"2.4"}]};assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json=payload,headers=other).status_code==404
def test_queued_price_board_requires_explicit_job_id(client,db):
    admin={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"};first=Station(name="First",address_line="1 Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));second=Station(name="Second",address_line="2 Road",city="Auckland",latitude=Decimal("-36.86"),longitude=Decimal("174.77"));db.add_all([first,second]);db.commit();media=upload_media(client,admin,"OTHER").json();client.post("/api/v1/ocr-jobs",json={"kind":"PRICE_BOARD","resource_id":media["id"],"station_id":str(first.id)},headers=admin)
    payload={"media_asset_id":media["id"],"observed_at":datetime.now(timezone.utc).isoformat(),"prices":[{"fuel_type":"PETROL_91","price":"2.4"}]};assert client.post(f"/api/v1/admin/stations/{second.id}/price-board",json=payload,headers=admin).status_code==422
def test_price_board_confirmation_fences_job_state_media_and_repeats(client,db):
    admin={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"};station=Station(name="Fenced",address_line="6 Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit();media=upload_media(client,admin,"OTHER").json();other_media=upload_media(client,admin,"OTHER").json();queued=client.post("/api/v1/ocr-jobs",json={"kind":"PRICE_BOARD","resource_id":media["id"]},headers=admin).json();job=db.get(OCRJob,uuid.UUID(queued["id"]));base={"observed_at":datetime.now(timezone.utc).isoformat(),"prices":[{"fuel_type":"PETROL_91","price":"2.4"}]}
    assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json={**base,"media_asset_id":media["id"]},headers=admin).status_code==422
    assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json={**base,"job_id":queued["id"],"media_asset_id":media["id"]},headers=admin).status_code==409
    job.status=Status.REVIEW_REQUIRED;job.requires_confirmation=True;job.result_json={"prices":[]};db.commit()
    assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json={**base,"job_id":queued["id"],"media_asset_id":other_media["id"]},headers=admin).status_code==422
    confirmed=client.post(f"/api/v1/admin/stations/{station.id}/price-board",json={**base,"job_id":queued["id"],"media_asset_id":media["id"]},headers=admin);assert confirmed.status_code==201
    assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json={**base,"job_id":queued["id"],"media_asset_id":media["id"]},headers=admin).status_code==409;assert db.scalar(select(func.count(Observation.id)).where(Observation.media_asset_id==uuid.UUID(media["id"])))==1
def test_failed_price_board_cannot_be_applied_by_media_only(client,db):
    admin={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"};station=Station(name="Failed",address_line="7 Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit();media=upload_media(client,admin,"OTHER").json();queued=client.post("/api/v1/ocr-jobs",json={"kind":"PRICE_BOARD","resource_id":media["id"]},headers=admin).json();job=db.get(OCRJob,uuid.UUID(queued["id"]));job.status=Status.FAILED;db.commit();payload={"media_asset_id":media["id"],"observed_at":datetime.now(timezone.utc).isoformat(),"prices":[{"fuel_type":"PETROL_91","price":"2.4"}]};assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json=payload,headers=admin).status_code==422;assert db.scalar(select(func.count(Observation.id)).where(Observation.media_asset_id==uuid.UUID(media["id"])))==0
def test_low_confidence_assigned_price_board_can_be_reassigned_explicitly(client,db,monkeypatch):
    monkeypatch.setattr("app.routes.MockOCRProvider.extract_price_board",lambda self,path:{"prices":[{"fuel_type":"PETROL_91","price_per_litre":"2.4","confidence":.6}]});admin={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"};first=Station(name="Original",address_line="8 Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));second=Station(name="Corrected",address_line="9 Road",city="Auckland",latitude=Decimal("-36.86"),longitude=Decimal("174.77"));db.add_all([first,second]);db.commit();media=upload_media(client,admin,"OTHER").json();queued=client.post("/api/v1/ocr-jobs",json={"kind":"PRICE_BOARD","resource_id":media["id"],"station_id":str(first.id)},headers=admin).json();process_ocr_jobs(db.get_bind());payload={"job_id":queued["id"],"media_asset_id":media["id"],"observed_at":datetime.now(timezone.utc).isoformat(),"prices":[{"fuel_type":"PETROL_91","price":"2.4"}]};assert client.post(f"/api/v1/admin/stations/{second.id}/price-board",json=payload,headers=admin).status_code==201;job=db.get(OCRJob,uuid.UUID(queued["id"]));assert job.station_id==second.id and {row.station_id for row in db.scalars(select(Observation).where(Observation.media_asset_id==uuid.UUID(media["id"])))}=={second.id}
def test_low_confidence_receipt_and_price_jobs_require_then_accept_confirmation(client,user_headers,db,monkeypatch):
    monkeypatch.setattr("app.routes.MockOCRProvider.extract_receipt",lambda self,path:{"station_name":"Review","station_address":None,"transaction_datetime":datetime.now(timezone.utc).isoformat(),"fuel_type":"PETROL_91","litres":"40","pump_price_per_litre":"2.2","discount_amount":"0","total_amount":"88","confidence":{"station":.6,"datetime":.6,"fuel_type":.6,"litres":.6,"price":.6,"discount":.6,"total":.6}})
    media=upload_media(client,user_headers).json();receipt=client.post("/api/v1/receipts",json={"media_asset_id":media["id"]},headers=user_headers).json();queued=client.post("/api/v1/ocr-jobs",json={"kind":"RECEIPT","resource_id":receipt["id"]},headers=user_headers).json();process_ocr_jobs(db.get_bind());receipt_job=db.get(OCRJob,uuid.UUID(queued["id"]));assert receipt_job.status==Status.REVIEW_REQUIRED and receipt_job.applied_at is None;confirmed=client.post(f"/api/v1/receipts/{receipt['id']}/confirm",json={"fuel_type":"PETROL_91","litres":"40","pump_price_per_litre":"2.2","total_amount":"88","transaction_datetime":datetime.now(timezone.utc).isoformat()},headers=user_headers);assert confirmed.status_code==200;db.refresh(receipt_job);assert receipt_job.status==Status.CONFIRMED
    monkeypatch.setattr("app.routes.MockOCRProvider.extract_price_board",lambda self,path:{"prices":[{"fuel_type":"PETROL_91","price_per_litre":"2.4","confidence":.6}]});admin={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"};station=Station(name="Review Station",address_line="3 Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit();board=upload_media(client,admin,"OTHER").json();queued=client.post("/api/v1/ocr-jobs",json={"kind":"PRICE_BOARD","resource_id":board["id"],"station_id":str(station.id)},headers=admin).json();process_ocr_jobs(db.get_bind());price_job=db.get(OCRJob,uuid.UUID(queued["id"]));assert price_job.status==Status.REVIEW_REQUIRED and db.scalar(select(func.count(Observation.id)).where(Observation.media_asset_id==uuid.UUID(board["id"])))==0;payload={"job_id":queued["id"],"media_asset_id":board["id"],"observed_at":datetime.now(timezone.utc).isoformat(),"prices":[{"fuel_type":"PETROL_91","price":"2.4"}]};assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json=payload,headers=admin).status_code==201;db.refresh(price_job);assert price_job.status==Status.CONFIRMED
def test_vehicle_crud_and_ownership(client,user_headers):
    data={"nickname":"RAV4","make":"Toyota","model":"RAV4","fuel_type":"PETROL_91"};created=client.post("/api/v1/vehicles",json=data,headers=user_headers);assert created.status_code==201;vehicle=created.json();assert vehicle["is_primary"]
    other={"Authorization":f"Bearer dev:{uuid.uuid4()}"};assert client.get(f"/api/v1/vehicles/{vehicle['id']}",headers=other).status_code==404
    assert client.patch(f"/api/v1/vehicles/{vehicle['id']}",json={"nickname":"Family car"},headers=user_headers).json()["nickname"]=="Family car"
    assert client.delete(f"/api/v1/vehicles/{vehicle['id']}",headers=user_headers).status_code==204
def test_admin_restricted(client,user_headers):assert client.get("/api/v1/admin/dashboard",headers=user_headers).status_code==403
def test_admin_can_view_receipt_media(client,user_headers):
    admin_headers={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"}
    media=upload_media(client,user_headers);media_id=media.json()["id"]
    response=client.get(f"/api/v1/admin/media/{media_id}/content",headers=admin_headers)
    assert response.status_code==200;assert response.headers["content-type"]=="image/jpeg";assert response.headers["cache-control"]=="private, no-store";assert response.content.startswith(b"\xff\xd8")
    assert client.get(f"/api/v1/admin/media/{media_id}/content",headers=user_headers).status_code==403
    assert client.get(f"/api/v1/admin/media/{uuid.uuid4()}/content",headers=admin_headers).status_code==404
def test_upload_intent_is_bound_and_single_use(client,user_headers):
    content=jpeg_bytes();prepared=client.post("/api/v1/media/upload-url",json={"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers).json();assert client.put(prepared["upload_url"],content=content,headers={**user_headers,"content-type":"image/jpeg"}).status_code==204;assert client.put(prepared["upload_url"],content=content,headers={**user_headers,"content-type":"image/jpeg"}).status_code==409
    wrong=client.post("/api/v1/media/complete",json={"storage_token":prepared["storage_token"],"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers);assert wrong.status_code==422
    body={"storage_token":prepared["storage_token"],"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)};assert client.post("/api/v1/media/complete",json=body,headers=user_headers).status_code==201;assert client.post("/api/v1/media/complete",json=body,headers=user_headers).status_code==409
def test_supabase_upload_url_request_sends_json_body(client,user_headers,monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://project.supabase.co");monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","service-role");get_settings.cache_clear();captured={}
    def signed_upload(url,**kwargs):
        captured.update(url=url,**kwargs)
        return type("Response",(),{"raise_for_status":lambda self:None,"json":lambda self:{"url":"/object/upload/sign/private-media/path?token=signed"}})()
    monkeypatch.setattr("app.routes.httpx.post",signed_upload)
    response=client.post("/api/v1/media/upload-url",json={"type":"RECEIPT","mime_type":"image/jpeg","file_size":100},headers=user_headers)
    assert response.status_code==200;assert captured["json"]=={};assert response.json()["upload_url"]=="https://project.supabase.co/storage/v1/object/upload/sign/private-media/path?token=signed"
def test_supabase_upload_url_failure_returns_service_unavailable_without_stale_intent(client,user_headers,db,monkeypatch):
    from app.models import UploadIntent
    monkeypatch.setenv("SUPABASE_URL","https://project.supabase.co");monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","service-role");get_settings.cache_clear()
    def failed_upload(url,**kwargs):
        request=httpx.Request("POST",url);response=httpx.Response(400,request=request)
        raise httpx.HTTPStatusError("bad request",request=request,response=response)
    monkeypatch.setattr("app.routes.httpx.post",failed_upload)
    response=client.post("/api/v1/media/upload-url",json={"type":"RECEIPT","mime_type":"image/jpeg","file_size":100},headers=user_headers)
    assert response.status_code==503;assert db.scalar(select(func.count(UploadIntent.id)))==0
def test_supabase_malformed_signed_response_does_not_leave_stale_intent(client,user_headers,db,monkeypatch):
    from app.models import UploadIntent
    monkeypatch.setenv("SUPABASE_URL","https://project.supabase.co");monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","service-role");get_settings.cache_clear()
    monkeypatch.setattr("app.routes.httpx.post",lambda *args,**kwargs:type("Response",(),{"raise_for_status":lambda self:None,"json":lambda self:{"url":None}})())
    response=client.post("/api/v1/media/upload-url",json={"type":"RECEIPT","mime_type":"image/jpeg","file_size":100},headers=user_headers)
    assert response.status_code==503;assert db.scalar(select(func.count(UploadIntent.id)))==0
def test_supabase_completion_validates_downloaded_image_with_declared_mime(client,user_headers,monkeypatch):
    content=jpeg_bytes()
    monkeypatch.setenv("SUPABASE_URL","https://project.supabase.co");monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","service-role");get_settings.cache_clear()
    monkeypatch.setattr("app.routes.httpx.post",lambda *args,**kwargs:type("Response",(),{"raise_for_status":lambda self:None,"json":lambda self:{"url":"/object/upload/sign/private-media/path?token=signed"}})())
    def storage_get(url,**kwargs):
        request=httpx.Request("GET",url)
        if "/object/info/" in url:return httpx.Response(200,request=request,json={"metadata":{"mimetype":"image/jpeg","size":len(content)}})
        return httpx.Response(200,request=request,content=content)
    monkeypatch.setattr("app.routes.httpx.get",storage_get)
    prepared=client.post("/api/v1/media/upload-url",json={"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers).json()
    response=client.post("/api/v1/media/complete",json={"storage_token":prepared["storage_token"],"type":"ODOMETER","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers)
    assert response.status_code==201;assert response.json()["type"]=="ODOMETER"
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
    monkeypatch.setenv("APP_ENV","test");monkeypatch.setenv("LOCAL_MEDIA_DIR",str(tmp_path/"media"));monkeypatch.setenv("SUPABASE_URL","");monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","");get_settings.cache_clear()
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
    admin={"Authorization":user_headers["Authorization"]+":admin"};assert client.get("/api/v1/admin/users",headers=admin).status_code==200;assert client.get(f"/api/v1/admin/brands/{brand.id}",headers=admin).json()["name"]=="Test Fuel";assert client.get(f"/api/v1/admin/stations/{station.id}",headers=admin).json()["name"]=="Public Test";assert client.patch(f"/api/v1/admin/stations/{station.id}",json={"name":"Renamed"},headers=admin).json()["name"]=="Renamed"

def test_public_fuel_snapshot_aggregates_current_prices_without_private_data(client,db):
    station=Station(name="Snapshot Fuel",address_line="7 Public Road",city="Wellington",latitude=Decimal("-41.2865"),longitude=Decimal("174.7762"));inactive=Station(name="Hidden Fuel",address_line="8 Road",city="Wellington",latitude=Decimal("-41.29"),longitude=Decimal("174.78"),is_active=False);db.add_all([station,inactive]);db.flush();now=datetime.now(timezone.utc)
    observation=Observation(station_id=station.id,fuel_type=FuelType.PETROL_91,pump_price_per_litre=Decimal("2.499"),source=Source.COMMUNITY,verification_level=Verification.UNVERIFIED,observed_at=now,confidence_score=Decimal("0.8"),is_active=True);db.add(observation);db.flush();db.add_all([CurrentPrice(station_id=station.id,fuel_type=FuelType.PETROL_91,price=Decimal("2.499"),observed_at=now,observation_id=observation.id,confidence_score=Decimal("0.8"),verification_level=Verification.UNVERIFIED),CurrentPrice(station_id=inactive.id,fuel_type=FuelType.DIESEL,price=Decimal("1.899"),observed_at=now,observation_id=observation.id,confidence_score=Decimal("0.8"),verification_level=Verification.UNVERIFIED)]);db.commit()
    response=client.get("/api/v1/fuel-prices/snapshot")
    assert response.status_code==200;body=response.json();assert body["priced_station_count"]==1;assert body["stations"][0]["name"]=="Snapshot Fuel";assert body["stations"][0]["prices"]["PETROL_91"]==2.499;assert body["averages"][0]["station_count"]==1;assert body["reports_week"]==1
    assert "user_id" not in response.text and "observation_id" not in response.text and "Hidden Fuel" not in response.text

def test_admin_manages_brands_and_stations(client,user_headers,db):
    admin={"Authorization":user_headers["Authorization"]+":admin"}
    brand_response=client.post("/api/v1/admin/brands",json={"name":"  North Fuel  ","slug":"north-fuel","logo_url":" https://example.test/logo.png "},headers=admin)
    assert brand_response.status_code==201;brand=brand_response.json();assert brand["name"]=="North Fuel"
    assert client.post("/api/v1/admin/brands",json={"name":"Duplicate","slug":"north-fuel"},headers=admin).status_code==409
    assert client.post("/api/v1/admin/brands",json={"name":"   ","slug":"blank"},headers=admin).status_code==422
    assert client.post("/api/v1/admin/brands",json={"name":"Unsafe","slug":"unsafe","logo_url":"javascript:alert(1)"},headers=admin).status_code==422
    for malformed in ("https:foo","https:///path","https://user:pass@example.test/logo.png","https://example.test:bad/logo.png"):
        assert client.post("/api/v1/admin/brands",json={"name":"Unsafe","slug":"unsafe","logo_url":malformed},headers=admin).status_code==422
    edited=client.patch(f"/api/v1/admin/brands/{brand['id']}",json={"name":"Northern Fuel","logo_url":None},headers=admin)
    assert edited.status_code==200;assert edited.json()["logo_url"] is None
    other_brand=client.post("/api/v1/admin/brands",json={"name":"Other Fuel","slug":"other-fuel"},headers=admin).json()
    assert client.patch(f"/api/v1/admin/brands/{other_brand['id']}",json={"slug":"north-fuel"},headers=admin).status_code==409
    for field in ("name","slug"):
        assert client.patch(f"/api/v1/admin/brands/{brand['id']}",json={field:None},headers=admin).status_code==422
    payload={"brand_id":brand["id"],"name":"Harbour Fuel","google_place_id":"place-1","address_line":"1 Quay Street","suburb":"Central","city":"Auckland","region":"Auckland","postal_code":"1010","country_code":"nz","latitude":"-36.844","longitude":"174.768","timezone":"Pacific/Auckland"}
    created=client.post("/api/v1/admin/stations",json=payload,headers=admin)
    assert created.status_code==201;station=created.json();assert station["country_code"]=="NZ";assert station["brand_id"]==brand["id"]
    changed=client.patch(f"/api/v1/admin/stations/{station['id']}",json={"address_line":"2 Quay Street","suburb":None,"latitude":"-36.845","is_active":False,"brand_id":None},headers=admin)
    assert changed.status_code==200;assert changed.json()["address_line"]=="2 Quay Street";assert changed.json()["suburb"] is None;assert changed.json()["brand_id"] is None;assert changed.json()["is_active"] is False
    assert client.post("/api/v1/admin/stations",json=payload,headers=admin).status_code==409
    second=client.post("/api/v1/admin/stations",json={**payload,"name":"Second","google_place_id":"place-2"},headers=admin).json()
    assert client.patch(f"/api/v1/admin/stations/{second['id']}",json={"google_place_id":"place-1"},headers=admin).status_code==409
    for field in ("name","address_line","city","country_code","latitude","longitude","timezone","is_active"):
        assert client.patch(f"/api/v1/admin/stations/{station['id']}",json={field:None},headers=admin).status_code==422
    unknown={**payload,"google_place_id":"place-2","brand_id":str(uuid.uuid4())}
    assert client.post("/api/v1/admin/stations",json=unknown,headers=admin).status_code==422
    assert client.post("/api/v1/admin/brands",json={"name":"Nope","slug":"nope"},headers=user_headers).status_code==403

def test_admin_searches_google_station_candidates_without_importing(client,user_headers,db,monkeypatch):
    admin={"Authorization":user_headers["Authorization"]+":admin"};monkeypatch.setenv("MAPS_PROVIDER","google");monkeypatch.setenv("GOOGLE_MAPS_API_KEY","test-key");get_settings.cache_clear()
    places=[{"id":"google-1","displayName":{"text":"Search Fuel"},"formattedAddress":"5 Test Road, Auckland","location":{"latitude":-36.85,"longitude":174.76},"addressComponents":[{"longText":"Auckland","types":["locality"]},{"longText":"Auckland","types":["administrative_area_level_1"]}]}]
    monkeypatch.setattr("app.routes.GoogleMapsProvider.text_search",lambda self,q:places)
    response=client.get("/api/v1/admin/station-candidates?q=Search",headers=admin)
    assert response.status_code==200;assert response.json()[0]=={"google_place_id":"google-1","name":"Search Fuel","address_line":"5 Test Road, Auckland","city":"Auckland","region":"Auckland","country_code":"NZ","latitude":-36.85,"longitude":174.76,"timezone":"Pacific/Auckland"}
    assert db.scalar(select(func.count(Station.id)))==0

def test_admin_bulk_imports_updates_and_deduplicates_google_stations(client,user_headers,db,monkeypatch):
    admin={"Authorization":user_headers["Authorization"]+":admin"};monkeypatch.setenv("MAPS_PROVIDER","google");monkeypatch.setenv("GOOGLE_MAPS_API_KEY","test-key");get_settings.cache_clear()
    existing=Station(name="Old name",google_place_id="google-1",address_line="Old address",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));unchanged=Station(name="Same Fuel",google_place_id="google-2",address_line="2 Road",city="Auckland",region=None,latitude=Decimal("-36.86"),longitude=Decimal("174.77"));db.add_all([existing,unchanged]);db.commit()
    valid=lambda place_id,name,address,lat,lng:{"id":place_id,"displayName":{"text":name},"formattedAddress":address,"location":{"latitude":lat,"longitude":lng},"addressComponents":[{"longText":"Auckland","types":["locality"]}]}
    places=[valid("google-1","Updated Fuel","1 Road",-36.85,174.76),valid("google-2","Same Fuel","2 Road",-36.86,174.77),valid("google-3","New Fuel","3 Road",-36.87,174.78),valid("google-3","Duplicate provider row","4 Road",-36.88,174.79),{"id":"invalid"}]
    monkeypatch.setattr("app.routes.GoogleMapsProvider.text_search",lambda self,q:places)
    response=client.post("/api/v1/admin/stations/import?q=Auckland",headers=admin)
    assert response.status_code==200;assert response.json()=={"query":"Auckland","provider_results":5,"valid_results":3,"invalid_results":1,"duplicate_provider_results":1,"added":1,"updated":1,"already_existing":1}
    db.expire_all();assert db.scalar(select(Station).where(Station.google_place_id=="google-1")).name=="Updated Fuel";assert db.scalar(select(func.count(Station.id)))==3
    repeated=client.post("/api/v1/admin/stations/import?q=Auckland",headers=admin)
    assert repeated.status_code==200;assert repeated.json()["added"]==0;assert repeated.json()["already_existing"]==3
    assert client.post("/api/v1/admin/stations/import?q=Auckland",headers=user_headers).status_code==403

def test_admin_station_import_rolls_back_on_conflict(client,user_headers,db,monkeypatch):
    admin={"Authorization":user_headers["Authorization"]+":admin"};monkeypatch.setenv("MAPS_PROVIDER","google");monkeypatch.setenv("GOOGLE_MAPS_API_KEY","test-key");get_settings.cache_clear()
    place={"id":"google-conflict","displayName":{"text":"Conflict Fuel"},"formattedAddress":"1 Road","location":{"latitude":-36.85,"longitude":174.76},"addressComponents":[{"longText":"Auckland","types":["locality"]}]};monkeypatch.setattr("app.routes.GoogleMapsProvider.text_search",lambda self,q:[place])
    original_commit=Session.commit
    def conflict(session):
        if any(isinstance(item,Station) for item in session.new):raise IntegrityError("statement",{},Exception("duplicate"))
        return original_commit(session)
    monkeypatch.setattr(Session,"commit",conflict)
    response=client.post("/api/v1/admin/stations/import?q=Conflict",headers=admin)
    assert response.status_code==409
    monkeypatch.setattr(Session,"commit",original_commit);db.rollback();assert db.scalar(select(func.count(Station.id)))==0

def test_admin_can_seed_prices_from_owned_price_board_photo(client,user_headers,db):
    station=Station(name="Seed Station",address_line="1 Seed Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit()
    admin={"Authorization":user_headers["Authorization"]+":admin"};profile_id=uuid.UUID(client.get("/api/v1/me",headers=admin).json()["id"]);media=MediaAsset(user_id=profile_id,type=MediaType.OTHER,storage_path=f"test/{uuid.uuid4()}",mime_type="image/jpeg",file_size=100);db.add(media);db.commit();observed_at=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
    payload={"media_asset_id":str(media.id),"observed_at":observed_at,"prices":[{"fuel_type":"PETROL_91","price":"2.459"},{"fuel_type":"DIESEL","price":"2.059"}]}
    response=client.post(f"/api/v1/admin/stations/{station.id}/price-board",json=payload,headers=admin)
    assert response.status_code==201;assert len(response.json()["observations"])==2
    observations=list(db.scalars(select(Observation).order_by(Observation.fuel_type)));assert {item.source.value for item in observations}=={"ADMIN"};assert {item.media_asset_id for item in observations}=={media.id}
    current=client.get(f"/api/v1/fuel-stations/{station.id}/prices").json();assert {item["fuel_type"] for item in current}=={"PETROL_91","DIESEL"}
    assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json=payload,headers=admin).status_code==409

def test_admin_can_seed_prices_without_a_photo(client,user_headers,db):
    station=Station(name="Manual Station",address_line="6 Seed Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit()
    admin={"Authorization":user_headers["Authorization"]+":admin"};payload={"observed_at":datetime.now(timezone.utc).isoformat(),"prices":[{"fuel_type":"PETROL_95","price":"2.599"}]}
    response=client.post(f"/api/v1/admin/stations/{station.id}/price-board",json=payload,headers=admin)
    assert response.status_code==201;assert response.json()["media_asset_id"] is None
    observation=db.scalar(select(Observation));assert observation.media_asset_id is None;assert observation.source==Source.ADMIN;assert observation.pump_price_per_litre==Decimal("2.599")
    assert Decimal(str(client.get(f"/api/v1/fuel-stations/{station.id}/prices").json()[0]["price"]))==Decimal("2.599")

def test_admin_price_board_analysis_populates_review_without_publishing(client,user_headers,db,monkeypatch):
    monkeypatch.setenv("OCR_PROVIDER","mock");get_settings.cache_clear()
    station=Station(name="Scan Station",address_line="4 Scan Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit()
    admin={"Authorization":user_headers["Authorization"]+":admin"};profile_id=uuid.UUID(client.get("/api/v1/me",headers=admin).json()["id"]);media=MediaAsset(user_id=profile_id,type=MediaType.OTHER,storage_path=f"test/{uuid.uuid4()}",mime_type="image/jpeg",file_size=100);db.add(media);db.commit();monkeypatch.setattr("app.routes.validated_media_bytes",lambda database,item:jpeg_bytes())
    response=client.post(f"/api/v1/admin/stations/{station.id}/price-board/analyze",json={"media_asset_id":str(media.id)},headers=admin)
    assert response.status_code==200
    assert response.json()["prices"]==[{"fuel_type":"PETROL_91","price_per_litre":"2.459","confidence":0.92},{"fuel_type":"DIESEL","price_per_litre":"2.059","confidence":0.9}]
    assert db.scalar(select(func.count(Observation.id)))==0
    assert client.get(f"/api/v1/fuel-stations/{station.id}/prices").json()==[]
    confirmed={"media_asset_id":str(media.id),"observed_at":datetime.now(timezone.utc).isoformat(),"prices":[{"fuel_type":"PETROL_91","price":"2.449"}]}
    assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json=confirmed,headers=admin).status_code==201
    assert db.scalar(select(Observation)).pump_price_per_litre==Decimal("2.449")

def test_admin_price_board_analysis_requires_owned_other_media(client,user_headers,db):
    station=Station(name="Scan Protected",address_line="5 Scan Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit()
    profile_id=uuid.UUID(client.get("/api/v1/me",headers=user_headers).json()["id"]);media=MediaAsset(user_id=profile_id,type=MediaType.OTHER,storage_path=f"test/{uuid.uuid4()}",mime_type="image/jpeg",file_size=100);db.add(media);db.commit();other_admin={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"}
    assert client.post(f"/api/v1/admin/stations/{station.id}/price-board/analyze",json={"media_asset_id":str(media.id)},headers=other_admin).status_code==404
    other_id=uuid.UUID(client.get("/api/v1/me",headers=other_admin).json()["id"]);receipt=MediaAsset(user_id=other_id,type=MediaType.RECEIPT,storage_path=f"test/{uuid.uuid4()}",mime_type="image/jpeg",file_size=100);db.add(receipt);db.commit()
    assert client.post(f"/api/v1/admin/stations/{station.id}/price-board/analyze",json={"media_asset_id":str(receipt.id)},headers=other_admin).status_code==422

def test_admin_price_board_rejects_unowned_media_and_duplicate_fuels(client,user_headers,db):
    station=Station(name="Protected",address_line="2 Seed Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit()
    profile_id=uuid.UUID(client.get("/api/v1/me",headers=user_headers).json()["id"]);media=MediaAsset(user_id=profile_id,type=MediaType.OTHER,storage_path=f"test/{uuid.uuid4()}",mime_type="image/jpeg",file_size=100);db.add(media);db.commit();admin={"Authorization":f"Bearer dev:{uuid.uuid4()}:admin"};base={"media_asset_id":str(media.id),"observed_at":datetime.now(timezone.utc).isoformat()}
    assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json={**base,"prices":[{"fuel_type":"DIESEL","price":"2"}]},headers=admin).status_code==404
    duplicate={**base,"prices":[{"fuel_type":"DIESEL","price":"2"},{"fuel_type":"DIESEL","price":"2.1"}]}
    assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json=duplicate,headers=admin).status_code==422

def test_admin_account_deletion_preserves_seeded_price_without_photo(client,user_headers,db):
    station=Station(name="Durable Seed",address_line="3 Seed Road",city="Auckland",latitude=Decimal("-36.85"),longitude=Decimal("174.76"));db.add(station);db.commit()
    admin={"Authorization":user_headers["Authorization"]+":admin"};profile_id=uuid.UUID(client.get("/api/v1/me",headers=admin).json()["id"]);media=MediaAsset(user_id=profile_id,type=MediaType.OTHER,storage_bucket="local-private-media",storage_path=f"test/{uuid.uuid4()}",mime_type="image/jpeg",file_size=100);db.add(media);db.commit()
    payload={"media_asset_id":str(media.id),"observed_at":datetime.now(timezone.utc).isoformat(),"prices":[{"fuel_type":"PETROL_91","price":"2.459"}]}
    assert client.post(f"/api/v1/admin/stations/{station.id}/price-board",json=payload,headers=admin).status_code==201
    assert client.delete("/api/v1/me",headers=admin).status_code==204
    observation=db.scalar(select(Observation));db.refresh(observation);assert observation.media_asset_id is None;assert observation.is_active
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

def test_duplicate_local_receipt_reuses_unclaimed_owned_media_and_removes_new_upload(client,user_headers,db):
    from app.config import get_settings
    content=jpeg_bytes();original=upload_media(client,user_headers,"RECEIPT",content);assert original.status_code==201
    duplicate=client.post("/api/v1/media/upload-url",json={"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers).json();assert client.put(duplicate["upload_url"],content=content,headers={**user_headers,"content-type":"image/jpeg"}).status_code==204
    response=client.post("/api/v1/media/complete",json={"storage_token":duplicate["storage_token"],"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers)
    assert response.status_code==200;assert response.json()["id"]==original.json()["id"];assert not (Path(get_settings().local_media_dir)/duplicate["storage_path"]).exists()
    db.expire_all();assert db.get(UploadIntent,uuid.UUID(duplicate["storage_token"])).completed_at is not None

def test_failed_owned_receipt_can_be_reselected_and_created_idempotently(client,user_headers,db):
    from app.config import get_settings
    content=jpeg_bytes();original=upload_media(client,user_headers,"RECEIPT",content).json();receipt=client.post("/api/v1/receipts",json={"media_asset_id":original["id"]},headers=user_headers).json()
    row=db.get(Receipt,uuid.UUID(receipt["id"]));row.processing_status=Status.FAILED;row.error_code="OCR_PROVIDER_UNAVAILABLE";db.commit()
    duplicate=client.post("/api/v1/media/upload-url",json={"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers).json();assert client.put(duplicate["upload_url"],content=content,headers={**user_headers,"content-type":"image/jpeg"}).status_code==204
    completed=client.post("/api/v1/media/complete",json={"storage_token":duplicate["storage_token"],"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers)
    assert completed.status_code==200;assert completed.json()["id"]==original["id"];assert not (Path(get_settings().local_media_dir)/duplicate["storage_path"]).exists()
    recreated=client.post("/api/v1/receipts",json={"media_asset_id":original["id"]},headers=user_headers);assert recreated.status_code==200;assert recreated.json()["id"]==receipt["id"]

def test_receipt_reselection_stays_blocked_across_accounts_and_after_success(client,user_headers,db):
    from app.config import get_settings
    content=jpeg_bytes();original=upload_media(client,user_headers,"RECEIPT",content).json();receipt=client.post("/api/v1/receipts",json={"media_asset_id":original["id"]},headers=user_headers).json()
    row=db.get(Receipt,uuid.UUID(receipt["id"]));row.processing_status=Status.CONFIRMED;db.commit()
    for headers in (user_headers,{"Authorization":f"Bearer dev:{uuid.uuid4()}"}):
        duplicate=client.post("/api/v1/media/upload-url",json={"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=headers).json();assert client.put(duplicate["upload_url"],content=content,headers={**headers,"content-type":"image/jpeg"}).status_code==204
        completed=client.post("/api/v1/media/complete",json={"storage_token":duplicate["storage_token"],"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=headers)
        assert completed.status_code==409;assert "This receipt image cannot be accepted" in completed.text
        assert not (Path(get_settings().local_media_dir)/duplicate["storage_path"]).exists();db.expire_all();assert db.get(UploadIntent,uuid.UUID(duplicate["storage_token"])).completed_at is not None

@pytest.mark.parametrize("cleanup_status,expected_status",[(200,200),(503,503)])
def test_supabase_duplicate_cleanup_preserves_retryability_on_failure(client,user_headers,db,monkeypatch,cleanup_status,expected_status):
    content=jpeg_bytes();original=upload_media(client,user_headers,"RECEIPT",content).json();receipt=client.post("/api/v1/receipts",json={"media_asset_id":original["id"]},headers=user_headers).json();row=db.get(Receipt,uuid.UUID(receipt["id"]));row.processing_status=Status.FAILED
    profile_id=row.user_id;intent=UploadIntent(user_id=profile_id,type=MediaType.RECEIPT,storage_path=f"{profile_id}/receipt/supabase-duplicate",mime_type="image/jpeg",file_size=len(content),expires_at=datetime.now(timezone.utc)+timedelta(minutes=5));db.add(intent);db.commit()
    monkeypatch.setenv("SUPABASE_URL","https://project.supabase.co");monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","service-role");get_settings.cache_clear();deleted=[]
    def storage_get(url,**kwargs):
        request=httpx.Request("GET",url)
        if "/object/info/" in url:return httpx.Response(200,request=request,json={"metadata":{"mimetype":"image/jpeg","size":len(content)}})
        return httpx.Response(200,request=request,content=content)
    def storage_delete(method,url,**kwargs):
        deleted.extend(kwargs["json"]["prefixes"]);return httpx.Response(cleanup_status,request=httpx.Request(method,url))
    monkeypatch.setattr("app.routes.httpx.get",storage_get);monkeypatch.setattr("app.routes.httpx.request",storage_delete)
    response=client.post("/api/v1/media/complete",json={"storage_token":str(intent.id),"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers)
    assert response.status_code==expected_status;db.expire_all();stored=db.get(UploadIntent,intent.id)
    assert deleted==[intent.storage_path];assert (stored.completed_at is not None)==(cleanup_status==200)

def test_supabase_duplicate_cleanup_timeout_is_safe_and_retryable(client,user_headers,db,monkeypatch):
    content=jpeg_bytes();original=upload_media(client,user_headers,"RECEIPT",content).json();receipt=client.post("/api/v1/receipts",json={"media_asset_id":original["id"]},headers=user_headers).json();row=db.get(Receipt,uuid.UUID(receipt["id"]));row.processing_status=Status.FAILED
    intent=UploadIntent(user_id=row.user_id,type=MediaType.RECEIPT,storage_path=f"{row.user_id}/receipt/timeout-duplicate",mime_type="image/jpeg",file_size=len(content),expires_at=datetime.now(timezone.utc)+timedelta(minutes=5));db.add(intent);db.commit()
    monkeypatch.setenv("SUPABASE_URL","https://project.supabase.co");monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","service-role");get_settings.cache_clear()
    def storage_get(url,**kwargs):
        request=httpx.Request("GET",url)
        if "/object/info/" in url:return httpx.Response(200,request=request,json={"metadata":{"mimetype":"image/jpeg","size":len(content)}})
        return httpx.Response(200,request=request,content=content)
    def timed_out(method,url,**kwargs):raise httpx.ReadTimeout("storage timeout",request=httpx.Request(method,url))
    monkeypatch.setattr("app.routes.httpx.get",storage_get);monkeypatch.setattr("app.routes.httpx.request",timed_out)
    response=client.post("/api/v1/media/complete",json={"storage_token":str(intent.id),"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=user_headers)
    assert response.status_code==503;assert "Private media cleanup is temporarily unavailable" in response.text
    assert "project.supabase.co" not in response.text and "storage timeout" not in response.text and str(row.user_id) not in response.text
    db.expire_all();assert db.get(UploadIntent,intent.id).completed_at is None

def test_concurrent_create_receipt_is_idempotent(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base,get_db
    from app.main import app
    database=tmp_path/"receipt-create.db";engine=create_engine(f"sqlite:///{database}",connect_args={"check_same_thread":False,"timeout":10});Base.metadata.create_all(engine);sessions=sessionmaker(engine,expire_on_commit=False);headers={"Authorization":f"Bearer dev:{uuid.uuid4()}"}
    def override():
        with sessions() as session:yield session
    app.dependency_overrides[get_db]=override
    try:
        with TestClient(app) as setup:media=upload_media(setup,headers,"RECEIPT").json()
        def create(_):
            with TestClient(app) as race:return race.post("/api/v1/receipts",json={"media_asset_id":media["id"]},headers=headers)
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(create,range(2)))
        assert sorted(response.status_code for response in responses)==[200,201];assert len({response.json()["id"] for response in responses})==1
        with sessions() as session:assert session.scalar(select(func.count(Receipt.id)))==1
    finally:app.dependency_overrides.clear();engine.dispose()

def test_concurrent_same_owner_duplicate_completion_reuses_winner(tmp_path,monkeypatch):
    import threading
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base,get_db
    from app.main import app
    import app.routes as routes
    database=tmp_path/"receipt-complete.db";engine=create_engine(f"sqlite:///{database}",connect_args={"check_same_thread":False,"timeout":10});Base.metadata.create_all(engine);sessions=sessionmaker(engine,expire_on_commit=False);headers={"Authorization":f"Bearer dev:{uuid.uuid4()}"};content=jpeg_bytes()
    monkeypatch.setenv("APP_ENV","test");monkeypatch.setenv("LOCAL_MEDIA_DIR",str(tmp_path/"media"));monkeypatch.setenv("SUPABASE_URL","");monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","");get_settings.cache_clear()
    def override():
        with sessions() as session:yield session
    app.dependency_overrides[get_db]=override;prepared=[]
    try:
        with TestClient(app) as setup:
            for _ in range(2):
                item=setup.post("/api/v1/media/upload-url",json={"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)},headers=headers).json();assert setup.put(item["upload_url"],content=content,headers={**headers,"content-type":"image/jpeg"}).status_code==204;prepared.append(item)
        original=routes.validate_image_content;barrier=threading.Barrier(2)
        def synchronized_validation(*args,**kwargs):
            result=original(*args,**kwargs);barrier.wait(timeout=5);return result
        monkeypatch.setattr(routes,"validate_image_content",synchronized_validation)
        def complete(index):
            body={"storage_token":prepared[index]["storage_token"],"type":"RECEIPT","mime_type":"image/jpeg","file_size":len(content)}
            with TestClient(app) as race:return race.post("/api/v1/media/complete",json=body,headers=headers)
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(complete,range(2)))
        assert sorted(response.status_code for response in responses)==[200,201];assert len({response.json()["id"] for response in responses})==1
        with sessions() as session:
            assert session.scalar(select(func.count(MediaAsset.id)))==1;assert all(session.get(UploadIntent,uuid.UUID(item["storage_token"])).completed_at is not None for item in prepared)
        paths=[Path(get_settings().local_media_dir)/item["storage_path"] for item in prepared];assert sum(path.exists() for path in paths)==1
    finally:app.dependency_overrides.clear();engine.dispose();get_settings.cache_clear()

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
    local=tmp_path/"must-not-exist";monkeypatch.setenv("APP_ENV","staging");monkeypatch.setenv("AUTH_MODE","supabase");monkeypatch.setenv("LOCAL_MEDIA_DIR",str(local));monkeypatch.setenv("SUPABASE_URL","");monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","");get_settings.cache_clear();assert local_media_enabled() is False
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
