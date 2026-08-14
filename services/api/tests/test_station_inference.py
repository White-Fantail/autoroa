import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.models import MediaAsset, MediaType, OCRJob, OCRJobKind, Profile, Station, Status
from app.station_inference import (
    _post_process_job,
    board_candidate_rows,
    extract_image_gps,
    receipt_candidate_rows,
)


def station(name: str, address: str, latitude: str, longitude: str):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        address_line=address,
        latitude=Decimal(latitude),
        longitude=Decimal(longitude),
    )


def test_extract_image_gps_supports_southern_and_eastern_hemispheres(monkeypatch):
    class Exif:
        def get_ifd(self, tag):
            assert tag == 0x8825
            return {
                1: b"S",
                2: (43, 32, 30),
                3: "E",
                4: (172, 38, 15),
            }

        def __bool__(self):
            return True

    class FakeImage:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def getexif(self):
            return Exif()

    monkeypatch.setattr("app.station_inference.Image.open", lambda *args, **kwargs: FakeImage())
    latitude, longitude = extract_image_gps(b"image")
    assert round(latitude, 6) == -43.541667
    assert round(longitude, 6) == 172.6375


def test_receipt_text_has_priority_over_conflicting_photo_location():
    receipt_match = station("Z Moorhouse", "250 Moorhouse Ave, Christchurch", "-43.536", "172.640")
    gps_match = station("NPD Nearby", "1 Nearby Road, Christchurch", "-43.5301", "172.6201")
    rows = receipt_candidate_rows(
        [gps_match, receipt_match],
        "Z Moorhouse",
        "250 Moorhouse Avenue, Christchurch",
        -43.5300,
        172.6200,
    )
    assert rows[0]["id"] == str(receipt_match.id)
    assert rows[0]["text_confidence"] > rows[1]["text_confidence"]


def test_price_board_candidates_use_nearest_station_and_limit_radius():
    near = station("Near", "1 Near Road", "-43.5305", "172.6200")
    farther = station("Farther", "2 Far Road", "-43.5380", "172.6200")
    outside = station("Outside", "3 Outside Road", "-43.5600", "172.6200")
    rows = board_candidate_rows([farther, outside, near], -43.5300, 172.6200)
    assert rows[0]["id"] == str(near.id)
    assert all(row["id"] != str(outside.id) for row in rows)


def test_unassigned_price_board_is_preselected_but_stays_review_required(db, monkeypatch):
    owner = Profile(auth_user_id=str(uuid.uuid4()))
    db.add(owner)
    db.flush()
    selected = Station(
        name="Closest",
        address_line="1 Test Road",
        city="Christchurch",
        latitude=Decimal("-43.5305"),
        longitude=Decimal("172.6200"),
    )
    media = MediaAsset(
        user_id=owner.id,
        type=MediaType.OTHER,
        storage_bucket="local-private-media",
        storage_path="test/board.jpg",
        mime_type="image/jpeg",
        file_size=10,
    )
    db.add_all([selected, media])
    db.flush()
    job = OCRJob(
        user_id=owner.id,
        kind=OCRJobKind.PRICE_BOARD,
        resource_id=media.id,
        media_asset_id=media.id,
        status=Status.REVIEW_REQUIRED,
        requires_confirmation=True,
        result_json={"prices": []},
    )
    db.add(job)
    db.commit()

    monkeypatch.setattr("app.station_inference.extract_image_gps", lambda content: (-43.5300, 172.6200))
    routes = SimpleNamespace(
        media_bytes=lambda item: b"image",
        place_values=lambda place: None,
        import_place=lambda session, values: None,
    )
    _post_process_job(job.id, db.get_bind(), routes)
    db.expire_all()
    refreshed = db.get(OCRJob, job.id)
    assert refreshed.station_id == selected.id
    assert refreshed.status == Status.REVIEW_REQUIRED
    assert refreshed.requires_confirmation is True
    assert refreshed.applied_at is None
    assert refreshed.result_json["station_candidates"][0]["id"] == str(selected.id)


def test_explicit_price_board_station_is_never_replaced(db):
    owner = Profile(auth_user_id=str(uuid.uuid4()))
    db.add(owner)
    db.flush()
    explicit = Station(
        name="Explicit",
        address_line="1 Explicit Road",
        city="Christchurch",
        latitude=Decimal("-43.5300"),
        longitude=Decimal("172.6200"),
    )
    media = MediaAsset(
        user_id=owner.id,
        type=MediaType.OTHER,
        storage_bucket="local-private-media",
        storage_path="test/explicit.jpg",
        mime_type="image/jpeg",
        file_size=10,
    )
    db.add_all([explicit, media])
    db.flush()
    job = OCRJob(
        user_id=owner.id,
        kind=OCRJobKind.PRICE_BOARD,
        resource_id=media.id,
        station_id=explicit.id,
        media_asset_id=media.id,
        status=Status.READY,
        requires_confirmation=False,
        result_json={"prices": []},
    )
    db.add(job)
    db.commit()

    routes = SimpleNamespace(media_bytes=lambda item: (_ for _ in ()).throw(AssertionError("must not read photo")))
    _post_process_job(job.id, db.get_bind(), routes)
    db.expire_all()
    refreshed = db.get(OCRJob, job.id)
    assert refreshed.station_id == explicit.id
    assert refreshed.status == Status.READY
    assert refreshed.requires_confirmation is False
