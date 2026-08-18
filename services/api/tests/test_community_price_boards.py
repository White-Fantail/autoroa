import io
import uuid

from PIL import Image
from sqlalchemy import select

from app import routes
from app.community_price_boards import _location_diagnostics
from app.models import MediaAsset, OCRJob, Observation, Source, Station, Status


def jpeg_bytes():
    output = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(output, format="JPEG")
    return output.getvalue()


def station(db, *, name="Test Fuel", latitude=-43.5321, longitude=172.6362):
    item = Station(
        name=name,
        address_line=f"1 {name} Road",
        city="Christchurch",
        latitude=latitude,
        longitude=longitude,
        is_active=True,
    )
    db.add(item)
    db.commit()
    return item


def admin_headers():
    return {"Authorization": f"Bearer dev:{uuid.uuid4()}:admin"}


def test_anonymous_fuel_map_photo_uses_shared_ocr_queue(client, db):
    selected = station(db)
    response = client.post(
        f"/api/v1/fuel-stations/{selected.id}/price-board-submissions",
        files={"photo": ("board.jpg", jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 202
    assert "Updated prices will appear on the Fuel Map" in response.json()["message"]

    job = db.scalar(select(OCRJob).order_by(OCRJob.created_at.desc()))
    media = db.get(MediaAsset, job.media_asset_id)
    assert job.user_id is None
    assert media.user_id is None
    assert job.station_id == selected.id

    queued = client.get(
        "/api/v1/ocr-jobs?kind=PRICE_BOARD&limit=20",
        headers=admin_headers(),
    )
    assert queued.status_code == 200
    row = next(item for item in queued.json() if item["id"] == str(job.id))
    assert row["submission_source"] == "FUEL_MAP_USER"

    routes.process_ocr_jobs(bind=db.get_bind(), max_jobs=1)
    db.expire_all()
    job = db.get(OCRJob, job.id)
    assert job.status == Status.REVIEW_REQUIRED
    assert job.requires_confirmation is True
    assert job.result_json["submission_source"] == "FUEL_MAP_USER"
    assert job.result_json["photo_location"]["status"] == "missing"
    assert db.scalar(select(Observation.id).where(Observation.media_asset_id == media.id)) is None


def test_admin_review_can_apply_anonymous_submission(client, db):
    selected = station(db)
    submitted = client.post(
        f"/api/v1/fuel-stations/{selected.id}/price-board-submissions",
        files={"photo": ("board.jpg", jpeg_bytes(), "image/jpeg")},
    )
    job_id = uuid.UUID(submitted.json()["submission_id"])
    routes.process_ocr_jobs(bind=db.get_bind(), max_jobs=1)
    db.expire_all()
    job = db.get(OCRJob, job_id)
    assert job.status == Status.REVIEW_REQUIRED

    prices = [
        {"fuel_type": entry["fuel_type"], "price": entry["price_per_litre"]}
        for entry in job.result_json["prices"]
    ]
    reviewed = client.post(
        f"/api/v1/admin/stations/{selected.id}/price-board",
        headers={**admin_headers(), "content-type": "application/json"},
        json={
            "job_id": str(job.id),
            "media_asset_id": str(job.media_asset_id),
            "observed_at": job.created_at.isoformat(),
            "prices": prices,
        },
    )
    assert reviewed.status_code == 200
    db.expire_all()
    job = db.get(OCRJob, job.id)
    observations = list(db.scalars(select(Observation).where(Observation.media_asset_id == job.media_asset_id)))
    assert job.status == Status.READY
    assert job.requires_confirmation is False
    assert job.result_json["review_resolution"] == "USE_SELECTED_STATION"
    assert observations
    assert {row.source for row in observations} == {Source.COMMUNITY}


def test_location_diagnostic_warns_when_selected_station_differs_from_detected(db, monkeypatch):
    selected = station(db, name="Selected", latitude=-43.55, longitude=172.63)
    detected = station(db, name="Detected", latitude=-43.5321, longitude=172.6362)
    monkeypatch.setattr(
        "app.community_price_boards.extract_image_gps",
        lambda _content: (-43.5321, 172.6362),
    )
    diagnostic, nearest = _location_diagnostics(db, b"photo", selected)
    assert nearest.id == detected.id
    assert diagnostic["station_mismatch"] is True
    assert diagnostic["detected_station_id"] == str(detected.id)
    assert diagnostic["selected_station_distance_km"] > 1
    assert "nearest detected station" in diagnostic["reason"]
