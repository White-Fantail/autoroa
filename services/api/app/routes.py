import uuid
import threading
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from pydantic import ValidationError
from .auth import Principal, admin_principal, current_principal
from .config import get_settings
from .db import get_db
from .models import *
from .schemas import *
from .services import GoogleMapsProvider, MockOCRProvider, OCRProviderResponseError, OdometerExtraction, OpenAIOCRProvider, PriceBoardExtraction, haversine_km, normalize_fuel_type, observation_anomaly, recalculate_vehicle_economy, receipt_arithmetic_suspicious, resolve_current_price, station_match_score, validate_image_content

router=APIRouter(prefix="/api/v1")
logger=logging.getLogger(__name__)
_development_limiter_lock=threading.Lock()
_development_fingerprint_lock=threading.Lock()
def cleanup_expired_limits(db:Session):
    db.execute(delete(RateLimit).where(RateLimit.window_started_at<datetime.now(timezone.utc)-timedelta(days=1)));db.commit()
def enforce_expensive_limit(db:Session,user_id:uuid.UUID,operation:str,limit:int):
    now=datetime.now(timezone.utc);key=f"{operation}:{user_id}"
    lock=_development_limiter_lock if db.get_bind().dialect.name!="postgresql" else threading.Lock()
    with lock,Session(bind=db.get_bind()) as limiter:
        if limiter.bind and limiter.bind.dialect.name=="postgresql":limiter.execute(text("select pg_advisory_xact_lock(hashtext(:key))"),{"key":key})
        row=limiter.scalar(select(RateLimit).where(RateLimit.key==key).with_for_update())
        if not row:row=RateLimit(key=key,window_started_at=now,count=0);limiter.add(row)
        started=row.window_started_at if row.window_started_at.tzinfo else row.window_started_at.replace(tzinfo=timezone.utc)
        if started<now-timedelta(minutes=1):row.window_started_at=now;row.count=0
        if row.count>=limit:raise HTTPException(429,"Rate limit exceeded; retry shortly")
        row.count+=1;limiter.commit()
def owned(db, model, item_id, user_id):
    item=db.scalar(select(model).where(model.id==item_id,model.user_id==user_id));
    if not item: raise HTTPException(404,"Resource not found")
    return item
def receipt_failure_code(exc:Exception)->str:
    if isinstance(exc,(ValidationError,OCRProviderResponseError)):return "OCR_PROVIDER_INVALID_RESPONSE"
    if isinstance(exc,httpx.HTTPError):return "OCR_PROVIDER_UNAVAILABLE"
    return "RECEIPT_PROCESSING_FAILED"
def local_media_enabled():
    settings=get_settings()
    return settings.app_env in {"development","test"} and not settings.supabase_url and not settings.supabase_service_role_key
def local_media_path(storage_path:str):
    root=Path(get_settings().local_media_dir).resolve();path=(root/storage_path).resolve()
    if root not in path.parents:raise HTTPException(422,"Invalid media path")
    return path
def media_bytes(media:MediaAsset):
    settings=get_settings()
    if media.storage_bucket=="local-private-media":
        if not local_media_enabled():raise HTTPException(503,"Local media storage is unavailable")
        try:return local_media_path(media.storage_path).read_bytes()
        except FileNotFoundError as exc:raise HTTPException(409,"Uploaded object was not found") from exc
    if not settings.supabase_url or not settings.supabase_service_role_key:raise HTTPException(503,"Private media storage is not configured")
    response=httpx.get(f"{settings.supabase_url}/storage/v1/object/{media.storage_bucket}/{media.storage_path}",headers={"authorization":f"Bearer {settings.supabase_service_role_key}","apikey":settings.supabase_service_role_key},timeout=20);response.raise_for_status();return response.content
def discard_uploaded_object(storage_path:str):
    settings=get_settings()
    if settings.supabase_url and settings.supabase_service_role_key:
        try:response=httpx.request("DELETE",f"{settings.supabase_url}/storage/v1/object/private-media",headers={"authorization":f"Bearer {settings.supabase_service_role_key}","apikey":settings.supabase_service_role_key},json={"prefixes":[storage_path]},timeout=15)
        except httpx.HTTPError as exc:raise HTTPException(503,"Private media cleanup is temporarily unavailable") from exc
        if not response.is_success:raise HTTPException(503,"Private media cleanup is temporarily unavailable")
    elif local_media_enabled():local_media_path(storage_path).unlink(missing_ok=True)
def reusable_receipt_media(db:Session,user_id:uuid.UUID,content_hash:str):
    media=db.scalar(select(MediaAsset).where(MediaAsset.type==MediaType.RECEIPT,MediaAsset.content_sha256==content_hash))
    if not media or media.user_id!=user_id:return None
    receipt=db.scalar(select(Receipt).where(Receipt.media_asset_id==media.id,Receipt.user_id==user_id))
    if receipt and receipt.processing_status not in {Status.UPLOADED,Status.FAILED}:return None
    if receipt and db.scalar(select(FillUp.id).where(FillUp.receipt_id==receipt.id)):return None
    return media
def finish_reused_upload(db:Session,intent:UploadIntent,media:MediaAsset,response:Response):
    claimed_at=datetime.now(timezone.utc)
    claim=db.execute(update(UploadIntent).where(UploadIntent.id==intent.id,UploadIntent.user_id==intent.user_id,UploadIntent.completed_at.is_(None),UploadIntent.expires_at>=claimed_at).values(completed_at=claimed_at).execution_options(synchronize_session=False))
    if claim.rowcount!=1:db.rollback();raise HTTPException(409,"Upload intent is invalid, expired, or already used")
    discard_uploaded_object(intent.storage_path)
    db.commit()
    response.status_code=200
    return {"id":media.id,"type":media.type,"storage_path":media.storage_path}
def reject_duplicate_upload(db:Session,intent:UploadIntent):
    claimed_at=datetime.now(timezone.utc)
    claim=db.execute(update(UploadIntent).where(UploadIntent.id==intent.id,UploadIntent.user_id==intent.user_id,UploadIntent.completed_at.is_(None),UploadIntent.expires_at>=claimed_at).values(completed_at=claimed_at).execution_options(synchronize_session=False))
    if claim.rowcount!=1:db.rollback();raise HTTPException(409,"Upload intent is invalid, expired, or already used")
    discard_uploaded_object(intent.storage_path);db.commit()
    raise HTTPException(409,"This receipt image cannot be accepted")
def validated_media_bytes(db:Session,media:MediaAsset):
    content=media_bytes(media)
    try:width,height,digest=validate_image_content(content,media.mime_type)
    except ValueError as exc:raise HTTPException(422,"Uploaded content is not a safe supported image") from exc
    if media.type==MediaType.RECEIPT:
        lock=_development_fingerprint_lock if db.get_bind().dialect.name!="postgresql" else threading.Lock()
        with lock:
            existing=db.get(ReceiptFingerprint,digest)
            if existing and (not media.content_sha256 or media.content_sha256!=digest):raise HTTPException(409,"This receipt image cannot be accepted")
            if not existing:
                try:
                    with db.begin_nested():db.add(ReceiptFingerprint(content_sha256=digest));db.flush()
                except IntegrityError as exc:raise HTTPException(409,"This receipt image cannot be accepted") from exc
    media.width=width;media.height=height;media.content_sha256=digest;db.flush();return content
def validate_fillup_sanity(data,vehicle:Vehicle,current:FillUp|None=None):
    values={name:getattr(current,name,None) for name in ("fuel_type","litres","pump_price_per_litre","discount_amount","total_amount")};values.update(data.model_dump(exclude_unset=True))
    if values["fuel_type"]!=vehicle.fuel_type and not data.acknowledge_fuel_type_mismatch:raise HTTPException(409,{"code":"FUEL_TYPE_MISMATCH","message":"Fuel type differs from the vehicle; explicit confirmation is required"})
    if vehicle.tank_capacity_litres and values["litres"]>vehicle.tank_capacity_litres*Decimal("1.20") and not data.acknowledge_tank_capacity:raise HTTPException(409,{"code":"TANK_CAPACITY_WARNING","message":"Litres substantially exceed tank capacity; explicit confirmation is required"})
    if values["pump_price_per_litre"] and receipt_arithmetic_suspicious(values["litres"],values["pump_price_per_litre"],values["total_amount"],values["discount_amount"] or 0) and not data.acknowledge_arithmetic_warning:raise HTTPException(409,{"code":"ARITHMETIC_WARNING","message":"Fill-up arithmetic needs explicit confirmation"})
def place_values(place:dict):
    place_id=place.get("id");name=(place.get("displayName") or {}).get("text");location=place.get("location") or {};address=place.get("formattedAddress")
    if not place_id or not name or not address or not isinstance(location.get("latitude"),(int,float)) or not isinstance(location.get("longitude"),(int,float)):return None
    if not (-48<=location["latitude"]<=-34 and 165<=location["longitude"]<=179):return None
    components={kind:text for component in place.get("addressComponents",[]) for kind in component.get("types",[]) if (text:=component.get("longText"))}
    return place_id,name,address,location["latitude"],location["longitude"],components.get("locality") or components.get("postal_town") or "New Zealand",components.get("administrative_area_level_1")
def import_place(db:Session,values):
    place_id,name,address,lat,lng,city,region=values;item=db.scalar(select(Station).where(Station.google_place_id==place_id))
    if item:return item
    fields={"id":uuid.uuid4(),"name":name,"google_place_id":place_id,"address_line":address,"city":city,"region":region,"latitude":lat,"longitude":lng,"country_code":"NZ","timezone":"Pacific/Auckland","is_active":True}
    if db.get_bind().dialect.name=="postgresql":
        stmt=pg_insert(Station).values(**fields).on_conflict_do_update(index_elements=[Station.google_place_id],set_={"name":name,"address_line":address,"city":city,"region":region,"latitude":lat,"longitude":lng}).returning(Station)
        return db.scalars(stmt).one()
    try:
        with db.begin_nested():item=Station(name=name,google_place_id=place_id,address_line=address,city=city,region=region,latitude=lat,longitude=lng);db.add(item);db.flush()
        return item
    except IntegrityError:
        for _ in range(3):
            item=db.scalar(select(Station).where(Station.google_place_id==place_id))
            if item:return item
        raise HTTPException(503,"Station import is temporarily unavailable")
@router.get("/me",response_model=ProfileOut)
def me(p:Principal=Depends(current_principal)): return p.profile
@router.patch("/me",response_model=ProfileOut)
def patch_me(data:ProfilePatch,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(p.profile,k,v)
    db.commit();return p.profile
@router.delete("/me",status_code=204)
def delete_me(p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    job=db.scalar(select(AccountDeletion).where(AccountDeletion.user_id==p.profile.id))
    if not job:job=AccountDeletion(user_id=p.profile.id);db.add(job);db.commit();db.refresh(job)
    settings=get_settings();media=list(db.scalars(select(MediaAsset).where(MediaAsset.user_id==p.profile.id)));intents=list(db.scalars(select(UploadIntent).where(UploadIntent.user_id==p.profile.id)));receipts=list(db.scalars(select(Receipt).where(Receipt.user_id==p.profile.id)));receipt_ids=[x.id for x in receipts];fills=list(db.scalars(select(FillUp).where(FillUp.user_id==p.profile.id)));fill_ids=[x.id for x in fills]
    if media and (not settings.supabase_url or not settings.supabase_service_role_key) and any(x.storage_bucket!="local-private-media" for x in media):raise HTTPException(503,"Private media deletion is unavailable; account was not changed")
    observations=list(db.scalars(select(Observation).where((Observation.receipt_id.in_(receipt_ids) if receipt_ids else False)|(Observation.fill_up_id.in_(fill_ids) if fill_ids else False))))
    affected={(observation.station_id,observation.fuel_type) for observation in observations}
    for observation in observations:
        if observation.verification_level!=Verification.VERIFIED_RECEIPT:observation.is_active=False
        observation.receipt_id=None;observation.fill_up_id=None
    db.flush()
    if settings.supabase_url and settings.supabase_service_role_key and media and job.status!="STORAGE_DELETED":
        deletion=httpx.request("DELETE",f"{settings.supabase_url}/storage/v1/object/private-media",headers={"authorization":f"Bearer {settings.supabase_service_role_key}","apikey":settings.supabase_service_role_key},json={"prefixes":[x.storage_path for x in media]},timeout=15)
        if not deletion.is_success:raise HTTPException(503,"Private media deletion failed; account was not changed")
        job.status="STORAGE_DELETED";db.commit()
    if local_media_enabled():
        for storage_path in {item.storage_path for item in intents}|{item.storage_path for item in media if item.storage_bucket=="local-private-media"}:local_media_path(storage_path).unlink(missing_ok=True)
    db.execute(delete(FillUp).where(FillUp.user_id==p.profile.id));db.execute(delete(OdometerReading).where(OdometerReading.user_id==p.profile.id));db.execute(delete(Receipt).where(Receipt.user_id==p.profile.id));db.execute(delete(MediaAsset).where(MediaAsset.user_id==p.profile.id));db.execute(delete(Vehicle).where(Vehicle.user_id==p.profile.id));db.execute(delete(UploadIntent).where(UploadIntent.user_id==p.profile.id))
    job.status="COMPLETED";db.delete(p.profile)
    for station_id,fuel_type in affected:resolve_current_price(db,station_id,fuel_type)
    db.commit()
@router.get("/vehicles",response_model=list[VehicleOut])
def vehicles(p:Principal=Depends(current_principal),db:Session=Depends(get_db)): return list(db.scalars(select(Vehicle).where(Vehicle.user_id==p.profile.id,Vehicle.is_archived.is_(False)).order_by(Vehicle.is_primary.desc())))
@router.post("/vehicles",response_model=VehicleOut,status_code=201)
def create_vehicle(data:VehicleIn,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    if data.is_primary or not db.scalar(select(Vehicle.id).where(Vehicle.user_id==p.profile.id)): db.execute(update(Vehicle).where(Vehicle.user_id==p.profile.id).values(is_primary=False)); data.is_primary=True
    item=Vehicle(user_id=p.profile.id,**data.model_dump());db.add(item);db.commit();db.refresh(item);return item
@router.get("/vehicles/{item_id}",response_model=VehicleOut)
def get_vehicle(item_id:uuid.UUID,p:Principal=Depends(current_principal),db:Session=Depends(get_db)): return owned(db,Vehicle,item_id,p.profile.id)
@router.patch("/vehicles/{item_id}",response_model=VehicleOut)
def patch_vehicle(item_id:uuid.UUID,data:VehiclePatch,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    item=owned(db,Vehicle,item_id,p.profile.id)
    if data.is_primary: db.execute(update(Vehicle).where(Vehicle.user_id==p.profile.id).values(is_primary=False))
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(item,k,v)
    db.commit();return item
@router.delete("/vehicles/{item_id}",status_code=204)
def archive_vehicle(item_id:uuid.UUID,p:Principal=Depends(current_principal),db:Session=Depends(get_db)): item=owned(db,Vehicle,item_id,p.profile.id);item.is_archived=True;item.is_primary=False;db.commit()
@router.post("/media/upload-url")
def prepare_media(data:MediaPrepare,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    settings=get_settings()
    if data.mime_type not in {"image/jpeg","image/png","image/webp"} or data.file_size>settings.max_upload_bytes: raise HTTPException(422,"Unsupported image or file too large")
    if not (settings.supabase_url and settings.supabase_service_role_key) and not local_media_enabled():raise HTTPException(503,"Private media storage is not configured")
    intent=UploadIntent(user_id=p.profile.id,type=data.type,storage_path=f"{p.profile.id}/{data.type.value.lower()}/{uuid.uuid4()}",mime_type=data.mime_type,file_size=data.file_size,expires_at=datetime.now(timezone.utc)+timedelta(minutes=15));db.add(intent);db.commit()
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            response=httpx.post(f"{settings.supabase_url}/storage/v1/object/upload/sign/private-media/{intent.storage_path}",headers={"authorization":f"Bearer {settings.supabase_service_role_key}","apikey":settings.supabase_service_role_key},json={},timeout=10);response.raise_for_status();signed=response.json();signed_url=signed["url"]
            if not isinstance(signed_url,str) or not signed_url.startswith("/"):raise ValueError("Invalid signed upload URL")
            upload_url=f"{settings.supabase_url}/storage/v1{signed_url}"
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            db.delete(intent);db.commit()
            raise HTTPException(503,"Private media upload is temporarily unavailable") from exc
    elif local_media_enabled():upload_url=f"/api/v1/media/uploads/{intent.id}"
    else:raise HTTPException(503,"Private media storage is not configured")
    return {"storage_token":str(intent.id),"storage_path":intent.storage_path,"upload_url":upload_url,"headers":{"content-type":data.mime_type},"expires_in":900}
@router.put("/media/uploads/{token}",status_code=204)
async def upload_local_media(token:uuid.UUID,request:Request,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    if not local_media_enabled():raise HTTPException(404,"Resource not found")
    intent=db.scalar(select(UploadIntent).where(UploadIntent.id==token,UploadIntent.user_id==p.profile.id))
    expires=intent.expires_at.replace(tzinfo=timezone.utc) if intent else None
    if not intent or intent.completed_at or expires<datetime.now(timezone.utc):raise HTTPException(409,"Upload intent is invalid, expired, or already used")
    if request.headers.get("content-type","").split(";",1)[0].lower()!=intent.mime_type:raise HTTPException(422,"Uploaded content type does not match preparation")
    maximum=min(intent.file_size,get_settings().max_upload_bytes);content=bytearray()
    async for chunk in request.stream():
        if len(content)+len(chunk)>maximum:raise HTTPException(422,"Uploaded content size does not match preparation")
        content.extend(chunk)
    if len(content)!=intent.file_size:raise HTTPException(422,"Uploaded content size does not match preparation")
    path=local_media_path(intent.storage_path)
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open("xb") as output:output.write(content)
    except FileExistsError as exc:raise HTTPException(409,"Upload intent is already used") from exc
@router.post("/media/complete",status_code=201)
def complete_media(data:MediaComplete,response:Response,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    try: token=uuid.UUID(data.storage_token)
    except ValueError as exc: raise HTTPException(422,"Invalid upload token") from exc
    intent=db.scalar(select(UploadIntent).where(UploadIntent.id==token,UploadIntent.user_id==p.profile.id))
    if not intent or intent.completed_at or intent.expires_at.replace(tzinfo=timezone.utc)<datetime.now(timezone.utc):raise HTTPException(409,"Upload intent is invalid, expired, or already used")
    if (data.type,data.mime_type,data.file_size)!=(intent.type,intent.mime_type,intent.file_size):raise HTTPException(422,"Completed upload metadata does not match preparation")
    settings=get_settings()
    trusted_width,trusted_height,content_hash=data.width,data.height,None
    if settings.supabase_url and settings.supabase_service_role_key:
        check=httpx.get(f"{settings.supabase_url}/storage/v1/object/info/private-media/{intent.storage_path}",headers={"authorization":f"Bearer {settings.supabase_service_role_key}","apikey":settings.supabase_service_role_key},timeout=10)
        if check.status_code!=200:raise HTTPException(409,"Uploaded object was not found")
        info=check.json();metadata=info.get("metadata",{});actual_type=metadata.get("mimetype") or info.get("content_type");actual_size=int(metadata.get("size") or info.get("size") or 0)
        if actual_type!=intent.mime_type or actual_size!=intent.file_size:raise HTTPException(422,"Uploaded object metadata does not match preparation")
        try:trusted_width,trusted_height,content_hash=validate_image_content(media_bytes(MediaAsset(storage_bucket="private-media",storage_path=intent.storage_path,mime_type=data.mime_type,file_size=data.file_size,user_id=p.profile.id,type=data.type)),intent.mime_type)
        except ValueError as exc:raise HTTPException(422,"Uploaded content is not a safe supported image") from exc
        if data.type==MediaType.RECEIPT and db.get(ReceiptFingerprint,content_hash):
            if reusable:=reusable_receipt_media(db,p.profile.id,content_hash):return finish_reused_upload(db,intent,reusable,response)
            reject_duplicate_upload(db,intent)
    elif local_media_enabled():
        path=local_media_path(intent.storage_path)
        try:content=path.read_bytes()
        except FileNotFoundError as exc:raise HTTPException(409,"Uploaded object was not found") from exc
        if len(content)!=intent.file_size:
            path.unlink(missing_ok=True)
            raise HTTPException(422,"Uploaded object metadata does not match preparation")
        try:trusted_width,trusted_height,content_hash=validate_image_content(content,intent.mime_type)
        except ValueError as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(422,"Uploaded content is not a safe supported image") from exc
        if data.type==MediaType.RECEIPT and db.get(ReceiptFingerprint,content_hash):
            if reusable:=reusable_receipt_media(db,p.profile.id,content_hash):return finish_reused_upload(db,intent,reusable,response)
            reject_duplicate_upload(db,intent)
    else:raise HTTPException(503,"Private media storage is not configured")
    claimed_at=datetime.now(timezone.utc);claim=db.execute(update(UploadIntent).where(UploadIntent.id==token,UploadIntent.user_id==p.profile.id,UploadIntent.completed_at.is_(None),UploadIntent.expires_at>=claimed_at).values(completed_at=claimed_at).execution_options(synchronize_session=False))
    if claim.rowcount!=1:db.rollback();raise HTTPException(409,"Upload intent is invalid, expired, or already used")
    item=MediaAsset(user_id=p.profile.id,type=data.type,storage_bucket="private-media" if settings.supabase_url and settings.supabase_service_role_key else "local-private-media",storage_path=intent.storage_path,mime_type=data.mime_type,file_size=data.file_size,width=trusted_width,height=trusted_height,content_sha256=content_hash);db.add(item)
    if data.type==MediaType.RECEIPT and content_hash:db.add(ReceiptFingerprint(content_sha256=content_hash))
    try:db.commit()
    except IntegrityError as exc:
        db.rollback()
        if data.type==MediaType.RECEIPT and content_hash:
            if reusable:=reusable_receipt_media(db,p.profile.id,content_hash):return finish_reused_upload(db,intent,reusable,response)
            reject_duplicate_upload(db,intent)
        raise HTTPException(409,"This receipt image cannot be accepted") from exc
    db.refresh(item);return {"id":item.id,"type":item.type,"storage_path":item.storage_path}
@router.get("/media/{item_id}")
def get_media(item_id:uuid.UUID,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    item=owned(db,MediaAsset,item_id,p.profile.id)
    return {"id":item.id,"type":item.type,"mime_type":item.mime_type,"file_size":item.file_size,"width":item.width,"height":item.height,"created_at":item.created_at}
@router.post("/receipts",status_code=201)
def create_receipt(data:ReceiptCreate,response:Response,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    media=owned(db,MediaAsset,data.media_asset_id,p.profile.id)
    if media.type!=MediaType.RECEIPT: raise HTTPException(422,"Receipt media required")
    existing=db.scalar(select(Receipt).where(Receipt.media_asset_id==media.id,Receipt.user_id==p.profile.id))
    if existing:
        if existing.processing_status in {Status.UPLOADED,Status.FAILED} and not db.scalar(select(FillUp.id).where(FillUp.receipt_id==existing.id)):response.status_code=200;return existing
        raise HTTPException(409,"This receipt image cannot be accepted")
    item=Receipt(user_id=p.profile.id,media_asset_id=media.id);db.add(item)
    try:db.commit()
    except IntegrityError as exc:
        db.rollback();existing=db.scalar(select(Receipt).where(Receipt.media_asset_id==media.id,Receipt.user_id==p.profile.id))
        if existing and existing.processing_status in {Status.UPLOADED,Status.FAILED} and not db.scalar(select(FillUp.id).where(FillUp.receipt_id==existing.id)):response.status_code=200;return existing
        raise HTTPException(409,"This receipt image cannot be accepted") from exc
    db.refresh(item);return item
@router.get("/receipts/{item_id}")
def get_receipt(item_id:uuid.UUID,p:Principal=Depends(current_principal),db:Session=Depends(get_db)): return owned(db,Receipt,item_id,p.profile.id)
@router.get("/receipts/{item_id}/station-candidates")
def station_candidates(item_id:uuid.UUID,latitude:float|None=None,longitude:float|None=None,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    receipt=owned(db,Receipt,item_id,p.profile.id);rows=[]
    for station in db.scalars(select(Station).where(Station.is_active.is_(True))):
        distance=haversine_km(latitude,longitude,station.latitude,station.longitude) if latitude is not None and longitude is not None else 5
        score=station_match_score(receipt.station_text or "",(receipt.raw_result_json or {}).get("station_address"),station.name,station.address_line,distance)
        if score>=.2:rows.append({"id":station.id,"name":station.name,"address":station.address_line,"distance_km":round(distance,2),"match_confidence":round(score,3)})
    settings=get_settings()
    if not rows and latitude is not None and settings.maps_provider=="google" and settings.google_maps_api_key:
        enforce_expensive_limit(db,p.profile.id,"station-match",8)
        if not (-48<=latitude<=-34 and longitude is not None and 165<=longitude<=179):raise HTTPException(422,"Google station import is limited to New Zealand")
        try:places=GoogleMapsProvider(settings.google_maps_api_key).nearby_stations(latitude,longitude,10)
        except (httpx.HTTPError,ValueError,TypeError) as exc:raise HTTPException(503,"Station provider is temporarily unavailable") from exc
        for place in places:
            values=place_values(place)
            if not values:continue
            station=import_place(db,values)
            rows.append({"id":station.id,"name":station.name,"address":station.address_line,"distance_km":round(haversine_km(latitude,longitude,station.latitude,station.longitude),2),"match_confidence":.5})
        db.commit()
    return sorted(rows,key=lambda x:x["match_confidence"],reverse=True)[:5]
@router.get("/fuel-stations/search")
def search_stations(q:str=Query(min_length=2,max_length=100),p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    enforce_expensive_limit(db,p.profile.id,"station-search",12)
    rows=list(db.scalars(select(Station).where(Station.is_active.is_(True),(Station.name.ilike(f"%{q}%"))|(Station.address_line.ilike(f"%{q}%"))|(Station.city.ilike(f"%{q}%"))).limit(10)));settings=get_settings()
    if not rows and settings.maps_provider=="google" and settings.google_maps_api_key:
        try:places=GoogleMapsProvider(settings.google_maps_api_key).text_search(q)
        except (httpx.HTTPError,ValueError,TypeError) as exc:raise HTTPException(503,"Station provider is temporarily unavailable") from exc
        for place in places:
            values=place_values(place)
            if not values:continue
            item=import_place(db,values)
            rows.append(item)
        db.commit()
    return rows
@router.post("/receipts/{item_id}/process")
def process_receipt(item_id:uuid.UUID,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    enforce_expensive_limit(db,p.profile.id,"ocr",6)
    item=owned(db,Receipt,item_id,p.profile.id)
    if item.processing_status in {Status.READY,Status.REVIEW_REQUIRED,Status.CONFIRMED}: return item
    item.processing_status=Status.PROCESSING;item.error_code=None;item.error_message=None;db.commit()
    try:
        media=owned(db,MediaAsset,item.media_asset_id,p.profile.id);settings=get_settings();content=validated_media_bytes(db,media)
        if settings.ocr_provider=="openai":
            if not settings.openai_api_key:raise RuntimeError("OpenAI is not configured")
            result=OpenAIOCRProvider(settings.openai_api_key).extract_receipt_bytes(content,media.mime_type)
        else:result=MockOCRProvider().extract_receipt(media.storage_path)
        c=result["confidence"];item.ocr_provider=settings.ocr_provider;item.raw_result_json=result;item.station_text=result.get("station_name");item.station_confidence=c["station"];item.fuel_type=normalize_fuel_type(result["fuel_type"]) if result.get("fuel_type") else None;item.fuel_type_confidence=c["fuel_type"];item.litres=Decimal(str(result["litres"])) if result.get("litres") is not None else None;item.litres_confidence=c["litres"];item.pump_price_per_litre=Decimal(str(result["pump_price_per_litre"])) if result.get("pump_price_per_litre") is not None else None;item.price_confidence=c["price"];item.discount_amount=Decimal(str(result["discount_amount"])) if result.get("discount_amount") is not None else None;item.discount_confidence=c["discount"];item.total_amount=Decimal(str(result["total_amount"])) if result.get("total_amount") is not None else None;item.total_confidence=c["total"];item.transaction_datetime=datetime.fromisoformat(result["transaction_datetime"]) if result.get("transaction_datetime") else None;item.datetime_confidence=c["datetime"];item.overall_confidence=min(c.values());item.processing_status=Status.READY if item.overall_confidence>=Decimal("0.9") else Status.REVIEW_REQUIRED;item.processed_at=datetime.now(timezone.utc)
    except Exception as exc:
        failure_code=receipt_failure_code(exc)
        logger.warning("receipt_ocr_failed receipt_id=%s provider=%s category=%s exception=%s",item.id,get_settings().ocr_provider,failure_code,type(exc).__name__)
        item.processing_status=Status.FAILED;item.error_code=failure_code;item.error_message="We couldn't read this receipt."
    db.commit();return item
@router.post("/receipts/{item_id}/confirm")
def confirm_receipt(item_id:uuid.UUID,data:ReceiptConfirm,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    item=owned(db,Receipt,item_id,p.profile.id)
    if data.transaction_datetime.tzinfo is None:raise HTTPException(422,"transaction_datetime must include a timezone")
    if receipt_arithmetic_suspicious(data.litres,data.pump_price_per_litre,data.total_amount,data.discount_amount or 0) and not data.acknowledge_arithmetic_warning:raise HTTPException(409,"Receipt arithmetic needs explicit confirmation")
    if data.station_id and not db.get(Station,data.station_id):raise HTTPException(422,"Unknown station")
    now=datetime.now(timezone.utc);occurred=data.transaction_datetime if data.transaction_datetime.tzinfo else data.transaction_datetime.replace(tzinfo=timezone.utc)
    if occurred>now+timedelta(hours=1) or occurred<now-timedelta(days=90):raise HTTPException(422,"Receipt transaction time is not plausible")
    item.station_id=data.station_id;item.station_text=data.station_text;item.fuel_type=data.fuel_type;item.litres=data.litres;item.pump_price_per_litre=data.pump_price_per_litre;item.discount_amount=data.discount_amount;item.total_amount=data.total_amount;item.transaction_datetime=data.transaction_datetime;item.processing_status=Status.CONFIRMED;db.commit();return item
@router.post("/odometer-readings",status_code=201)
def create_odo(data:OdometerCreate,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    media=owned(db,MediaAsset,data.media_asset_id,p.profile.id);owned(db,Vehicle,data.vehicle_id,p.profile.id)
    if media.type!=MediaType.ODOMETER: raise HTTPException(422,"Odometer media required")
    item=OdometerReading(user_id=p.profile.id,vehicle_id=data.vehicle_id,media_asset_id=media.id);db.add(item);db.commit();db.refresh(item);return item
@router.get("/odometer-readings/{item_id}")
def get_odo(item_id:uuid.UUID,p:Principal=Depends(current_principal),db:Session=Depends(get_db)): return owned(db,OdometerReading,item_id,p.profile.id)
@router.post("/odometer-readings/{item_id}/process")
def process_odo(item_id:uuid.UUID,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    enforce_expensive_limit(db,p.profile.id,"ocr",6)
    item=owned(db,OdometerReading,item_id,p.profile.id)
    if item.processing_status in {Status.READY,Status.REVIEW_REQUIRED}:return item
    item.processing_status=Status.PROCESSING;db.commit()
    try:
        media=owned(db,MediaAsset,item.media_asset_id,p.profile.id);settings=get_settings();content=validated_media_bytes(db,media)
        if settings.ocr_provider=="openai":
            if not settings.openai_api_key:raise RuntimeError("OpenAI is not configured")
            result=OpenAIOCRProvider(settings.openai_api_key).extract_odometer_bytes(content,media.mime_type)
        else:result=MockOCRProvider().extract_odometer(media.storage_path)
        validated=OdometerExtraction.model_validate(result);item.raw_result_json=validated.model_dump(mode="json");item.reading_km=validated.odometer;item.confidence=validated.confidence;item.processing_status=Status.READY if validated.odometer is not None and item.confidence>=Decimal(".9") else Status.REVIEW_REQUIRED;item.processed_at=datetime.now(timezone.utc)
    except Exception:item.processing_status=Status.FAILED;item.raw_result_json=None;item.error_code="ODOMETER_PROCESSING_FAILED";item.error_message="We couldn't read this odometer image."
    db.commit();return item
@router.get("/fill-ups",response_model=list[FillUpOut])
def fillups(vehicle_id:uuid.UUID|None=None,date_from:datetime|None=None,date_to:datetime|None=None,limit:int=Query(30,ge=1,le=100),cursor:datetime|None=None,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    q=select(FillUp).where(FillUp.user_id==p.profile.id);q=q.where(FillUp.vehicle_id==vehicle_id) if vehicle_id else q;q=q.where(FillUp.occurred_at>=date_from) if date_from else q;q=q.where(FillUp.occurred_at<=date_to) if date_to else q;q=q.where(FillUp.created_at<cursor) if cursor else q;return list(db.scalars(q.order_by(FillUp.occurred_at.desc()).limit(limit)))
def validate_odometer_sequence(db:Session,vehicle_id:uuid.UUID,occurred_at:datetime,odometer_km:int,confirmed:bool,current_id:uuid.UUID|None=None):
    base=select(FillUp).where(FillUp.vehicle_id==vehicle_id)
    if current_id:base=base.where(FillUp.id!=current_id)
    previous=db.scalar(base.where(FillUp.occurred_at<occurred_at).order_by(FillUp.occurred_at.desc()))
    following=db.scalar(base.where(FillUp.occurred_at>occurred_at).order_by(FillUp.occurred_at))
    invalid=(previous and odometer_km<previous.odometer_km) or (following and odometer_km>following.odometer_km)
    if invalid and not confirmed:raise HTTPException(409,"Odometer sequence requires explicit confirmation")
@router.post("/fill-ups",response_model=FillUpOut,status_code=201)
def create_fillup(data:FillUpIn,confirm_lower_odometer:bool=False,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    if data.occurred_at.tzinfo is None:raise HTTPException(422,"occurred_at must include a timezone")
    now=datetime.now(timezone.utc);occurred=data.occurred_at.astimezone(timezone.utc)
    if occurred>now+timedelta(hours=1) or occurred<now-timedelta(days=3650):raise HTTPException(422,"Fill-up time is not plausible")
    vehicle=owned(db,Vehicle,data.vehicle_id,p.profile.id);validate_fillup_sanity(data,vehicle)
    same_time=db.scalar(select(FillUp).where(FillUp.vehicle_id==data.vehicle_id,FillUp.occurred_at==data.occurred_at))
    if same_time:
        if data.receipt_id and same_time.receipt_id==data.receipt_id:return same_time
        raise HTTPException(409,"A fill-up already exists at this exact time")
    validate_odometer_sequence(db,data.vehicle_id,data.occurred_at,data.odometer_km,confirm_lower_odometer)
    if data.station_id and not db.get(Station,data.station_id):raise HTTPException(422,"Unknown station")
    if data.odometer_image_id:
        odo=owned(db,MediaAsset,data.odometer_image_id,p.profile.id)
        if odo.type!=MediaType.ODOMETER:raise HTTPException(422,"Odometer image required")
    verified=False
    if data.receipt_id:
        receipt=owned(db,Receipt,data.receipt_id,p.profile.id)
        existing=db.scalar(select(FillUp).where(FillUp.receipt_id==data.receipt_id))
        if existing:return existing
        if receipt.processing_status!=Status.CONFIRMED: raise HTTPException(409,"Receipt must be confirmed")
        receipt_time=receipt.transaction_datetime if receipt.transaction_datetime.tzinfo else receipt.transaction_datetime.replace(tzinfo=timezone.utc)
        fill_time=data.occurred_at.astimezone(timezone.utc)
        verified=receipt.station_id==data.station_id and receipt.fuel_type==data.fuel_type and receipt.litres==data.litres and receipt.pump_price_per_litre==data.pump_price_per_litre and abs((receipt_time-fill_time).total_seconds())<=3600 and receipt.total_amount==data.total_amount
    fields=data.model_dump(exclude={"acknowledge_fuel_type_mismatch","acknowledge_tank_capacity","acknowledge_arithmetic_warning"});item=FillUp(user_id=p.profile.id,**fields);db.add(item);db.flush();recalculate_vehicle_economy(db,item.vehicle_id)
    if item.station_id and item.pump_price_per_litre:
        enforce_expensive_limit(db,p.profile.id,"price-observation",5)
        obs=Observation(station_id=item.station_id,fuel_type=item.fuel_type,pump_price_per_litre=item.pump_price_per_litre,paid_price_per_litre=item.paid_price_per_litre,source=Source.RECEIPT if verified else Source.COMMUNITY,verification_level=Verification.VERIFIED_RECEIPT if verified else Verification.USER_CONFIRMED,observed_at=item.occurred_at,receipt_id=item.receipt_id if verified else None,fill_up_id=item.id,confidence_score=Decimal(".95") if verified else Decimal(".65"),is_anomaly=observation_anomaly(db,item.station_id,item.fuel_type,item.pump_price_per_litre));db.add(obs);db.flush();resolve_current_price(db,item.station_id,item.fuel_type)
    db.commit();db.refresh(item);return item
@router.get("/fill-ups/{item_id}",response_model=FillUpOut)
def get_fillup(item_id:uuid.UUID,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):return owned(db,FillUp,item_id,p.profile.id)
@router.patch("/fill-ups/{item_id}",response_model=FillUpOut)
def patch_fillup(item_id:uuid.UUID,data:FillUpPatch,confirm_lower_odometer:bool=False,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    item=owned(db,FillUp,item_id,p.profile.id)
    trusted_before=(item.station_id,item.fuel_type,item.litres,item.pump_price_per_litre,item.paid_price_per_litre,item.total_amount,item.occurred_at)
    vehicle=owned(db,Vehicle,item.vehicle_id,p.profile.id);validate_fillup_sanity(data,vehicle,item)
    if data.occurred_at and data.occurred_at.tzinfo is None:raise HTTPException(422,"occurred_at must include a timezone")
    if data.occurred_at and db.scalar(select(FillUp.id).where(FillUp.vehicle_id==item.vehicle_id,FillUp.id!=item.id,FillUp.occurred_at==data.occurred_at)):raise HTTPException(409,"A fill-up already exists at this exact time")
    prospective_time=data.occurred_at if data.occurred_at is not None else item.occurred_at;prospective_odometer=data.odometer_km if data.odometer_km is not None else item.odometer_km
    validate_odometer_sequence(db,item.vehicle_id,prospective_time,prospective_odometer,confirm_lower_odometer,item.id)
    if data.station_id and not db.get(Station,data.station_id):raise HTTPException(422,"Unknown station")
    if data.odometer_image_id:
        media=owned(db,MediaAsset,data.odometer_image_id,p.profile.id)
        if media.type!=MediaType.ODOMETER:raise HTTPException(422,"Odometer image required")
    for k,v in data.model_dump(exclude_unset=True,exclude={"acknowledge_fuel_type_mismatch","acknowledge_tank_capacity","acknowledge_arithmetic_warning"}).items():setattr(item,k,v)
    observation=db.scalar(select(Observation).where(Observation.fill_up_id==item.id));old_station=observation.station_id if observation else None;old_fuel=observation.fuel_type if observation else None;db.flush();recalculate_vehicle_economy(db,item.vehicle_id);trusted_changed=trusted_before!=(item.station_id,item.fuel_type,item.litres,item.pump_price_per_litre,item.paid_price_per_litre,item.total_amount,item.occurred_at)
    if observation:
        if not item.station_id or not item.pump_price_per_litre:observation.is_active=False
        else:
            observation.station_id=item.station_id;observation.fuel_type=item.fuel_type;observation.pump_price_per_litre=item.pump_price_per_litre;observation.paid_price_per_litre=item.paid_price_per_litre;observation.observed_at=item.occurred_at;observation.is_active=True
            if trusted_changed:observation.verification_level=Verification.USER_CONFIRMED;observation.source=Source.COMMUNITY;observation.receipt_id=None;observation.confidence_score=Decimal(".65")
            observation.is_anomaly=observation_anomaly(db,item.station_id,item.fuel_type,item.pump_price_per_litre)
        resolve_current_price(db,old_station,old_fuel);resolve_current_price(db,observation.station_id,observation.fuel_type)
    elif item.station_id and item.pump_price_per_litre:
        enforce_expensive_limit(db,p.profile.id,"price-observation",5);observation=Observation(station_id=item.station_id,fuel_type=item.fuel_type,pump_price_per_litre=item.pump_price_per_litre,paid_price_per_litre=item.paid_price_per_litre,source=Source.COMMUNITY,verification_level=Verification.USER_CONFIRMED,observed_at=item.occurred_at,fill_up_id=item.id,confidence_score=Decimal(".65"),is_anomaly=observation_anomaly(db,item.station_id,item.fuel_type,item.pump_price_per_litre));db.add(observation);db.flush();resolve_current_price(db,item.station_id,item.fuel_type)
    db.commit();return item
@router.delete("/fill-ups/{item_id}",status_code=204)
def delete_fillup(item_id:uuid.UUID,p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    item=owned(db,FillUp,item_id,p.profile.id);obs=db.scalar(select(Observation).where(Observation.fill_up_id==item.id))
    station_id=obs.station_id if obs else None;fuel_type=obs.fuel_type if obs else None;vehicle_id=item.vehicle_id
    if obs:obs.is_active=False;obs.fill_up_id=None
    db.delete(item);db.flush();recalculate_vehicle_economy(db,vehicle_id)
    if station_id:resolve_current_price(db,station_id,fuel_type)
    db.commit()
@router.get("/vehicles/{item_id}/metrics",response_model=Metrics)
def metrics(item_id:uuid.UUID,period:str="30d",p:Principal=Depends(current_principal),db:Session=Depends(get_db)):
    owned(db,Vehicle,item_id,p.profile.id);days={"30d":30,"90d":90,"12m":365,"all":None}.get(period)
    if period not in {"30d","90d","12m","all"}:raise HTTPException(422,"Invalid period")
    cutoff=datetime.now(timezone.utc)-timedelta(days=days) if days else None;q=select(FillUp).where(FillUp.vehicle_id==item_id);q=q.where(FillUp.occurred_at>=cutoff) if cutoff else q;rows=list(db.scalars(q.order_by(FillUp.occurred_at)));inside=lambda value:not cutoff or (value if value.tzinfo else value.replace(tzinfo=timezone.utc))>=cutoff;intervals=[x for x in rows if x.economy_is_valid and x.distance_since_previous_km and x.economy_fuel_litres is not None and x.economy_started_at and inside(x.economy_started_at)];distance=sum(x.distance_since_previous_km for x in intervals);fuel=sum((x.economy_fuel_litres for x in intervals),Decimal(0));cost=sum((x.economy_cost_amount for x in intervals),Decimal(0))
    baseline=db.scalar(select(FillUp).where(FillUp.vehicle_id==item_id,FillUp.occurred_at<=cutoff).order_by(FillUp.occurred_at.desc())) if cutoff else (rows[0] if rows else None);latest=rows[-1] if rows else None
    period_distance=max(0,latest.odometer_km-baseline.odometer_km) if baseline and latest else (max(0,rows[-1].odometer_km-rows[0].odometer_km) if len(rows)>1 else 0)
    return Metrics(distance_km=period_distance,fuel_litres=sum((x.litres for x in rows),Decimal(0)),fuel_spend=sum((x.total_amount for x in rows),Decimal(0)),average_fuel_economy_l_per_100km=(fuel/Decimal(distance)*100).quantize(Decimal(".001")) if distance else None,average_cost_per_100km=(cost/Decimal(distance)*100).quantize(Decimal(".01")) if distance else None,fill_up_count=len(rows))
def nearby_data(db,latitude,longitude,radius_km,fuel_type):
    stations=list(db.scalars(select(Station).where(Station.is_active.is_(True))));out=[]
    for s in stations:
        distance=haversine_km(latitude,longitude,s.latitude,s.longitude)
        if distance<=radius_km:
            prices=list(db.scalars(select(CurrentPrice).where(CurrentPrice.station_id==s.id,CurrentPrice.observed_at>=datetime.now(timezone.utc)-timedelta(days=7))));prices=[x for x in prices if not fuel_type or x.fuel_type==fuel_type]
            for price in prices or [None]:out.append({"station":{"id":s.id,"name":s.name,"address":s.address_line,"latitude":s.latitude,"longitude":s.longitude},"distance_km":round(distance,2),"fuel_type":price.fuel_type if price else fuel_type,"price":price.price if price else None,"observed_at":price.observed_at if price else None,"verification_level":price.verification_level if price else None,"confidence":price.confidence_score if price else None})
    return out
@router.get("/fuel-stations/nearby")
def nearby_stations(latitude:float,longitude:float,radius_km:float=Query(10,gt=0,le=100),fuel_type:FuelType|None=None,db:Session=Depends(get_db)):return nearby_data(db,latitude,longitude,radius_km,fuel_type)
@router.get("/fuel-prices/nearby")
def nearby_prices(latitude:float,longitude:float,radius_km:float=Query(10,gt=0,le=100),fuel_type:FuelType|None=None,sort:str="distance",db:Session=Depends(get_db)):
    if sort not in {"price","distance"}:raise HTTPException(422,"Invalid sort")
    rows=[x for x in nearby_data(db,latitude,longitude,radius_km,fuel_type) if x["price"] is not None];return sorted(rows,key=lambda x:x["price"] if sort=="price" else x["distance_km"])
@router.get("/fuel-stations/{item_id}")
def station(item_id:uuid.UUID,db:Session=Depends(get_db)): item=db.get(Station,item_id); return item or (_ for _ in ()).throw(HTTPException(404,"Station not found"))
@router.get("/fuel-stations/{item_id}/prices")
def station_prices(item_id:uuid.UUID,db:Session=Depends(get_db)):return list(db.scalars(select(CurrentPrice).where(CurrentPrice.station_id==item_id,CurrentPrice.observed_at>=datetime.now(timezone.utc)-timedelta(days=7))))
@router.get("/admin/dashboard")
def admin_dashboard(p=Depends(admin_principal),db:Session=Depends(get_db)):return {"users":db.scalar(select(func.count(Profile.id))),"fill_ups_today":db.scalar(select(func.count(FillUp.id)).where(FillUp.created_at>=datetime.now(timezone.utc)-timedelta(days=1))),"observations_today":db.scalar(select(func.count(Observation.id)).where(Observation.created_at>=datetime.now(timezone.utc)-timedelta(days=1))),"stations_with_recent_prices":db.scalar(select(func.count(CurrentPrice.station_id)).where(CurrentPrice.observed_at>=datetime.now(timezone.utc)-timedelta(days=1))),"ocr_failures":db.scalar(select(func.count(Receipt.id)).where(Receipt.processing_status==Status.FAILED)),"anomalies":db.scalar(select(func.count(Observation.id)).where(Observation.is_anomaly.is_(True)))}
def get_or_404(db:Session,model,item_id:uuid.UUID):
    item=db.get(model,item_id)
    if not item:raise HTTPException(404,"Related record not found")
    return item
@router.get("/admin/stations")
def admin_stations(p=Depends(admin_principal),db:Session=Depends(get_db)):return list(db.scalars(select(Station)))
@router.get("/admin/stations/{item_id}")
def admin_station(item_id:uuid.UUID,p=Depends(admin_principal),db:Session=Depends(get_db)):return get_or_404(db,Station,item_id)
@router.post("/admin/stations/{item_id}/price-board/analyze")
def admin_analyze_price_board(item_id:uuid.UUID,data:AdminPriceBoardAnalyze,p:Principal=Depends(admin_principal),db:Session=Depends(get_db)):
    station=db.get(Station,item_id)
    if not station or not station.is_active:raise HTTPException(404,"Active station not found")
    media=owned(db,MediaAsset,data.media_asset_id,p.profile.id)
    if media.type!=MediaType.OTHER:raise HTTPException(422,"Price-board photo media required")
    if db.scalar(select(Observation.id).where(Observation.media_asset_id==media.id)):raise HTTPException(409,"This price-board photo has already been submitted")
    enforce_expensive_limit(db,p.profile.id,"price-board-ocr",6)
    try:
        settings=get_settings();content=validated_media_bytes(db,media)
        if settings.ocr_provider=="openai":
            if not settings.openai_api_key:raise RuntimeError("OpenAI is not configured")
            result=OpenAIOCRProvider(settings.openai_api_key).extract_price_board_bytes(content,media.mime_type)
        else:result={"prices":[{"fuel_type":"PETROL_91","price_per_litre":"2.459","confidence":.92},{"fuel_type":"DIESEL","price_per_litre":"2.059","confidence":.9}]}
        extracted=PriceBoardExtraction.model_validate(result)
        unique={}
        for entry in extracted.prices:
            if entry.fuel_type not in unique or entry.confidence>unique[entry.fuel_type].confidence:unique[entry.fuel_type]=entry
        db.commit()
        return {"media_asset_id":media.id,"prices":[entry.model_dump(mode="json") for entry in unique.values()]}
    except HTTPException:raise
    except (httpx.HTTPError,ValueError,TypeError,RuntimeError) as exc:
        db.rollback();raise HTTPException(503,"The price-board photo could not be analyzed") from exc
@router.post("/admin/stations/{item_id}/price-board",status_code=201)
def admin_create_price_board(item_id:uuid.UUID,data:AdminPriceBoardCreate,p:Principal=Depends(admin_principal),db:Session=Depends(get_db)):
    if len({entry.fuel_type for entry in data.prices})!=len(data.prices):
        raise HTTPException(422,"Each fuel type may only be entered once")
    station=db.get(Station,item_id)
    if not station or not station.is_active:raise HTTPException(404,"Active station not found")
    media=owned(db,MediaAsset,data.media_asset_id,p.profile.id)
    if media.type!=MediaType.OTHER:raise HTTPException(422,"Price-board photo media required")
    observed_at=data.observed_at if data.observed_at.tzinfo else None
    if observed_at is None:raise HTTPException(422,"Observed time must include a timezone")
    if observed_at>datetime.now(timezone.utc)+timedelta(minutes=5):raise HTTPException(422,"Observed time cannot be in the future")
    if db.scalar(select(Observation.id).where(Observation.media_asset_id==media.id)):
        raise HTTPException(409,"This price-board photo has already been submitted")
    observations=[]
    for entry in data.prices:
        observation=Observation(station_id=station.id,fuel_type=entry.fuel_type,pump_price_per_litre=entry.price,source=Source.ADMIN,verification_level=Verification.USER_CONFIRMED,observed_at=observed_at,media_asset_id=media.id,confidence_score=Decimal("1"),is_anomaly=observation_anomaly(db,station.id,entry.fuel_type,entry.price))
        db.add(observation);observations.append(observation)
    db.flush()
    for observation in observations:resolve_current_price(db,station.id,observation.fuel_type)
    try:db.commit()
    except IntegrityError as exc:
        db.rollback();raise HTTPException(409,"This price-board photo has already been submitted") from exc
    return {"media_asset_id":media.id,"observations":observations}
@router.get("/admin/brands")
def admin_brands(p=Depends(admin_principal),db:Session=Depends(get_db)):return list(db.scalars(select(Brand)))
@router.get("/admin/brands/{item_id}")
def admin_brand(item_id:uuid.UUID,p=Depends(admin_principal),db:Session=Depends(get_db)):return get_or_404(db,Brand,item_id)
@router.patch("/admin/stations/{item_id}")
def admin_edit_station(item_id:uuid.UUID,name:str|None=None,address_line:str|None=None,is_active:bool|None=None,p=Depends(admin_principal),db:Session=Depends(get_db)):
    item=db.get(Station,item_id)
    if not item:raise HTTPException(404,"Station not found")
    if name is not None:item.name=name
    if address_line is not None:item.address_line=address_line
    if is_active is not None:item.is_active=is_active
    db.commit();return item
@router.get("/admin/users")
def admin_users(p=Depends(admin_principal),db:Session=Depends(get_db)):return list(db.scalars(select(Profile).limit(200)))
@router.get("/admin/users/{item_id}")
def admin_user(item_id:uuid.UUID,p=Depends(admin_principal),db:Session=Depends(get_db)):return get_or_404(db,Profile,item_id)
@router.get("/admin/vehicles")
def admin_vehicles(p=Depends(admin_principal),db:Session=Depends(get_db)):return list(db.scalars(select(Vehicle).limit(200)))
@router.get("/admin/vehicles/{item_id}")
def admin_vehicle(item_id:uuid.UUID,p=Depends(admin_principal),db:Session=Depends(get_db)):return get_or_404(db,Vehicle,item_id)
@router.get("/admin/fill-ups")
def admin_fill_ups(p=Depends(admin_principal),db:Session=Depends(get_db)):return list(db.scalars(select(FillUp).order_by(FillUp.occurred_at.desc()).limit(200)))
@router.get("/admin/fill-ups/{item_id}")
def admin_fill_up(item_id:uuid.UUID,p=Depends(admin_principal),db:Session=Depends(get_db)):return get_or_404(db,FillUp,item_id)
@router.get("/admin/receipts/{item_id}")
def admin_receipt(item_id:uuid.UUID,p=Depends(admin_principal),db:Session=Depends(get_db)):return get_or_404(db,Receipt,item_id)
@router.get("/admin/observations")
def admin_observations(p=Depends(admin_principal),db:Session=Depends(get_db)):return list(db.scalars(select(Observation).order_by(Observation.observed_at.desc()).limit(200)))
@router.get("/admin/receipt-failures")
def failures(p=Depends(admin_principal),db:Session=Depends(get_db)):return list(db.scalars(select(Receipt).where(Receipt.processing_status==Status.FAILED)))
@router.get("/admin/unmatched-stations")
def unmatched(p=Depends(admin_principal),db:Session=Depends(get_db)):return list(db.scalars(select(Receipt).where(Receipt.station_text.is_not(None),Receipt.processing_status!=Status.CONFIRMED)))
@router.patch("/admin/observations/{item_id}")
def moderate(item_id:uuid.UUID,is_active:bool,p=Depends(admin_principal),db:Session=Depends(get_db)):
    item=db.get(Observation,item_id)
    if not item:raise HTTPException(404,"Observation not found")
    item.is_active=is_active;db.commit();resolve_current_price(db,item.station_id,item.fuel_type);db.commit();return item
@router.post("/admin/stations/{item_id}/merge")
def merge(item_id:uuid.UUID,duplicate_id:uuid.UUID,p=Depends(admin_principal),db:Session=Depends(get_db)):
    canonical=db.get(Station,item_id);duplicate=db.get(Station,duplicate_id)
    if not canonical or not duplicate or canonical.id==duplicate.id:raise HTTPException(422,"Invalid station merge")
    db.execute(update(FillUp).where(FillUp.station_id==duplicate.id).values(station_id=canonical.id));db.execute(update(Observation).where(Observation.station_id==duplicate.id).values(station_id=canonical.id))
    for price in list(db.scalars(select(CurrentPrice).where(CurrentPrice.station_id==duplicate.id))):
        existing=db.get(CurrentPrice,(canonical.id,price.fuel_type))
        if existing:db.delete(price)
        else:price.station_id=canonical.id
    duplicate.is_active=False;db.commit()
    for fuel_type in FuelType:resolve_current_price(db,canonical.id,fuel_type)
    db.commit();return {"canonical_id":canonical.id,"duplicate_id":duplicate.id}
