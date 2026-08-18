import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.models import FuelType, Observation, Source, Station, Verification
from app.station_admin_tools import duplicate_groups


def station(name: str, latitude: str, longitude: str) -> Station:
    return Station(
        id=uuid.uuid4(),
        name=name,
        address_line=f"{name} address",
        city="Christchurch",
        country_code="NZ",
        latitude=Decimal(latitude),
        longitude=Decimal(longitude),
        timezone="Pacific/Auckland",
        is_active=True,
    )


def test_duplicate_groups_detects_stations_within_five_metres():
    first = station("First", "-43.532100", "172.636200")
    second = station("Second", "-43.532120", "172.636220")
    distant = station("Distant", "-43.533000", "172.636200")

    groups = duplicate_groups([first, second, distant], 5.0)

    assert len(groups) == 1
    assert {item["id"] for item in groups[0]["stations"]} == {
        str(first.id),
        str(second.id),
    }
    assert groups[0]["minimum_distance_m"] <= 5.0


def test_duplicate_groups_exact_location_only_matches_identical_coordinates():
    first = station("First", "-43.532100", "172.636200")
    second = station("Second", "-43.532100", "172.636200")
    nearby = station("Nearby", "-43.532101", "172.636200")

    groups = duplicate_groups([first, second, nearby], 0)

    assert len(groups) == 1
    assert {item["id"] for item in groups[0]["stations"]} == {
        str(first.id),
        str(second.id),
    }


def test_admin_duplicate_groups_and_merge(client, db):
    canonical = station("Canonical", "-43.532100", "172.636200")
    duplicate = station("Duplicate", "-43.532120", "172.636220")
    duplicate_id = duplicate.id
    canonical_id = canonical.id
    db.add_all([canonical, duplicate])
    db.flush()
    observation = Observation(
        station_id=duplicate_id,
        fuel_type=FuelType.PETROL_91,
        pump_price_per_litre=Decimal("2.499"),
        source=Source.ADMIN,
        verification_level=Verification.UNVERIFIED,
        observed_at=datetime.now(timezone.utc),
        confidence_score=Decimal("0.900"),
        is_anomaly=False,
        is_active=True,
    )
    db.add(observation)
    db.commit()
    observation_id = observation.id

    headers = {"Authorization": f"Bearer dev:{uuid.uuid4()}:admin"}
    duplicate_response = client.get(
        "/api/v1/admin/station-duplicate-groups?radius_m=5",
        headers=headers,
    )
    assert duplicate_response.status_code == 200
    payload = duplicate_response.json()
    assert payload["group_count"] == 1
    assert payload["duplicate_station_count"] == 2

    merge_response = client.post(
        f"/api/v1/admin/station-duplicates/{canonical_id}/merge",
        params={"duplicate_id": str(duplicate_id)},
        headers=headers,
    )
    assert merge_response.status_code == 200
    assert merge_response.json()["deleted_station_id"] == str(duplicate_id)

    db.expire_all()
    assert db.get(Station, duplicate_id) is None
    assert db.get(Observation, observation_id).station_id == canonical_id
