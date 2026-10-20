"""Manual review and two-shot capture protect missing/uncertain OCR fields."""
from datetime import datetime, timezone
import uuid
from sqlalchemy import select

from app.models import FillUp, OCRJobKind, OdometerReading, QuickCapture, Receipt, Status
from app.quick_capture import finalize_quick_captures
from app.routes import process_ocr_jobs
from test_api import jpeg_bytes, upload_media


def setup_capture(client, user_headers):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"Car","make":"Test","model":"One","fuel_type":"PETROL_91"},headers=user_headers).json()
    media=upload_media(client,user_headers).json()
    response=client.post("/api/v1/quick-captures",json={
        "vehicle_id":vehicle["id"], "client_token":"capture_manual_review_123",
        "receipt_media_asset_id":media["id"],
    },headers=user_headers)
    assert response.status_code==201
    return vehicle,response.json()


def test_full_scan_attaches_odometer_without_another_fillup(client,user_headers,db):
    vehicle,capture=setup_capture(client,user_headers)
    media=upload_media(client,user_headers,"ODOMETER",jpeg_bytes("black")).json()
    attached=client.post(f"/api/v1/quick-captures/{capture['id']}/odometer",json={
        "odometer_media_asset_id":media["id"]
    },headers=user_headers)
    assert attached.status_code==200
    duplicate=client.post(f"/api/v1/quick-captures/{capture['id']}/odometer",json={
        "odometer_media_asset_id":media["id"]
    },headers=user_headers)
    assert duplicate.status_code==200
    assert process_ocr_jobs(db.get_bind())==2
    assert finalize_quick_captures(db.get_bind())==1
    state=client.get(f"/api/v1/quick-captures/{capture['id']}",headers=user_headers).json()
    assert state["status"]=="CONFIRMED"
    result=db.get(FillUp,uuid.UUID(state["fill_up_id"]))
    assert result.odometer_km==83421
    assert result.odometer_image_id==uuid.UUID(media["id"])
    assert len(list(db.scalars(select(FillUp))))==1


def test_manual_confirmation_corrects_uncertain_ocr_and_does_not_publish(client,user_headers,db,monkeypatch):
    from app.services import MockOCRProvider
    original=MockOCRProvider.extract_receipt
    def uncertain(self,path):
        payload=original(self,path)
        payload["confidence"]["total"]=.65
        return payload
    monkeypatch.setattr("app.routes.MockOCRProvider.extract_receipt",uncertain)
    vehicle,capture=setup_capture(client,user_headers)
    assert process_ocr_jobs(db.get_bind())==1
    finalize_quick_captures(db.get_bind())
    state=client.get(f"/api/v1/quick-captures/{capture['id']}",headers=user_headers).json()
    assert state["status"]=="REVIEW_REQUIRED"
    payload={
        "occurred_at":datetime.now(timezone.utc).isoformat(),
        "fuel_type":"PETROL_91", "litres":"42.3", "pump_price_per_litre":"2.239",
        "discount_amount":"1.69", "total_amount":"93.02",
    }
    approved=client.post(f"/api/v1/quick-captures/{capture['id']}/confirm",json=payload,headers=user_headers)
    assert approved.status_code==200
    assert approved.json()["status"]=="CONFIRMED"
    fill=db.get(FillUp,uuid.UUID(approved.json()["fill_up_id"]))
    assert fill.odometer_km is None
    assert fill.station_id is None
    repeat=client.post(f"/api/v1/quick-captures/{capture['id']}/confirm",json=payload,headers=user_headers)
    assert repeat.status_code==200
    assert repeat.json()["fill_up_id"]==approved.json()["fill_up_id"]
    assert len(list(db.scalars(select(FillUp))))==1


def test_manual_review_requires_explicit_arithmetic_acknowledgement(client,user_headers,db):
    vehicle,capture=setup_capture(client,user_headers)
    payload={"occurred_at":datetime.now(timezone.utc).isoformat(),"fuel_type":"PETROL_91",
             "litres":"40","pump_price_per_litre":"2","total_amount":"200"}
    rejected=client.post(f"/api/v1/quick-captures/{capture['id']}/confirm",json=payload,headers=user_headers)
    assert rejected.status_code==409
    accepted=client.post(f"/api/v1/quick-captures/{capture['id']}/confirm",json={
        **payload,"acknowledge_arithmetic_warning":True,
    },headers=user_headers)
    assert accepted.status_code==200
