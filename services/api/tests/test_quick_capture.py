"""Focused Quick Capture API, OCR and idempotency tests."""
from datetime import datetime, timezone
import uuid

from app.models import FillUp, QuickCapture, Receipt, Vehicle
from app.quick_capture import finalize_quick_captures
from app.routes import process_ocr_jobs
from test_api import upload_media


def _vehicle(client, headers):
    response = client.post("/api/v1/vehicles", json={
        "nickname": "Quick car", "make": "Test", "model": "One", "fuel_type": "PETROL_91"
    }, headers=headers)
    assert response.status_code == 201
    return response.json()


def test_quick_capture_receipt_only_auto_commits_and_is_idempotent(client, user_headers, db):
    vehicle = _vehicle(client, user_headers)
    media = upload_media(client, user_headers).json()
    payload = {"vehicle_id": vehicle["id"], "client_token": "capture_receipt_only_001",
               "receipt_media_asset_id": media["id"]}
    first = client.post("/api/v1/quick-captures", json=payload, headers=user_headers)
    assert first.status_code == 201
    second = client.post("/api/v1/quick-captures", json=payload, headers=user_headers)
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert process_ocr_jobs(db.get_bind()) == 1
    assert finalize_quick_captures(db.get_bind()) == 1
    state = client.get(f"/api/v1/quick-captures/{first.json()['id']}", headers=user_headers).json()
    assert state["status"] == "CONFIRMED", {"state": state, "receipt": {key: str(getattr(db.get(Receipt, uuid.UUID(state["receipt_id"])), key)) for key in ("processing_status", "fuel_type", "litres", "pump_price_per_litre", "discount_amount", "total_amount", "transaction_datetime", "fuel_type_confidence", "litres_confidence", "price_confidence", "total_confidence", "datetime_confidence")}, "vehicle_fuel": str(db.get(Vehicle, uuid.UUID(vehicle["id"])).fuel_type)}
    assert state["fill_up_id"] is not None
    fill = db.get(FillUp, uuid.UUID(state["fill_up_id"]))
    assert fill.odometer_km is None
    assert fill.station_id is None
    assert finalize_quick_captures(db.get_bind()) == 0


def test_quick_capture_is_owner_scoped_and_token_cannot_change_media(client, user_headers, db):
    vehicle = _vehicle(client, user_headers)
    first_media = upload_media(client, user_headers).json()
    payload = {"vehicle_id": vehicle["id"], "client_token": "capture_owner_scoped_01",
               "receipt_media_asset_id": first_media["id"]}
    created = client.post("/api/v1/quick-captures", json=payload, headers=user_headers)
    assert created.status_code == 201
    other = {"Authorization": f"Bearer dev:{uuid.uuid4()}"}
    assert client.get(f"/api/v1/quick-captures/{created.json()['id']}", headers=other).status_code == 404
    assert client.get("/api/v1/quick-captures", headers=other).json() == []
    second_media = upload_media(client, user_headers, content=__import__("test_api").jpeg_bytes("black")).json()
    duplicate = client.post("/api/v1/quick-captures", json={
        **payload, "receipt_media_asset_id": second_media["id"]
    }, headers=user_headers)
    assert duplicate.status_code == 409
    assert db.query(QuickCapture).count() == 1
