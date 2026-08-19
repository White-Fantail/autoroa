import io
from PIL import Image
from sqlalchemy import select

from app.models import Station
from app.user_price_boards import CommunityPriceBoardSubmission


def jpeg_bytes():
    output = io.BytesIO()
    Image.new("RGB", (120, 80), "white").save(output, format="JPEG")
    return output.getvalue()


def add_station(db):
    station = Station(
        name="Test Fuel",
        address_line="1 Test Street",
        city="Christchurch",
        region="Canterbury",
        latitude=-43.5321,
        longitude=172.6362,
        is_active=True,
    )
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


def test_user_price_board_requires_authentication(client, db):
    station = add_station(db)
    response = client.post(
        f"/api/v1/fuel-stations/{station.id}/user-price-board-submissions",
        files={"photo": ("board.jpg", jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 401


def test_user_price_board_links_authenticated_user_to_community_ocr(client, db, user_headers):
    station = add_station(db)
    response = client.post(
        f"/api/v1/fuel-stations/{station.id}/user-price-board-submissions",
        headers=user_headers,
        files={"photo": ("board.jpg", jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["selected_station_id"] == str(station.id)
    assert body["location_status"] == "missing"

    contribution = db.scalar(select(CommunityPriceBoardSubmission))
    assert contribution is not None
    assert str(contribution.id) == body["submission_id"]
    assert contribution.selected_station_id == station.id
    assert contribution.ocr_job_id is not None
    assert contribution.content_sha256
