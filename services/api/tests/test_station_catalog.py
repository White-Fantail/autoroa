from app.models import Station
from app.station_catalog import nz_catalog_cells, sync_catalog_batch


def place(place_id: str, *, name: str = "Test Fuel", latitude: float = -43.53, longitude: float = 172.64):
    return {
        "id": place_id,
        "displayName": {"text": name},
        "formattedAddress": "1 Test Street, Christchurch 8011, New Zealand",
        "location": {"latitude": latitude, "longitude": longitude},
        "addressComponents": [
            {"longText": "Christchurch", "types": ["locality"]},
            {"longText": "Canterbury", "types": ["administrative_area_level_1"]},
        ],
    }


def test_catalog_plan_has_mainland_and_dense_overlay_cells():
    cells = nz_catalog_cells()
    assert len(cells) > 400
    assert any(cell.density == "base" for cell in cells)
    assert any(cell.density == "dense" for cell in cells)
    assert all(cell.radius_km <= 35 for cell in cells)


def test_sync_batch_deduplicates_place_ids_and_is_idempotent(db):
    calls = []

    def search(cell):
        calls.append(cell)
        return [place("google-place-1"), place("google-place-1")]

    first = sync_catalog_batch(db, start_cursor=0, max_cells=2, search_cell=search)
    assert len(calls) == 2
    assert first["added"] == 1
    assert first["existing"] == 0
    assert db.query(Station).count() == 1

    calls.clear()
    second = sync_catalog_batch(db, start_cursor=0, max_cells=2, search_cell=search)
    assert len(calls) == 2
    assert second["added"] == 0
    assert second["existing"] == 1
    assert db.query(Station).count() == 1


def test_sync_batch_refreshes_existing_provider_fields(db):
    state = {"name": "Old Fuel"}

    def search(cell):
        return [place("google-place-2", name=state["name"])]

    sync_catalog_batch(db, start_cursor=0, max_cells=1, search_cell=search)
    state["name"] = "Renamed Fuel"
    result = sync_catalog_batch(db, start_cursor=0, max_cells=1, search_cell=search)
    station = db.query(Station).filter(Station.google_place_id == "google-place-2").one()
    assert result["updated"] == 1
    assert station.name == "Renamed Fuel"


def test_sync_batch_reports_saturated_cells(db):
    def search(cell):
        return [place(f"place-{index}", latitude=-43.0 + index * 0.001) for index in range(20)]

    result = sync_catalog_batch(db, start_cursor=0, max_cells=1, search_cell=search)
    assert result["provider_results"] == 20
    assert result["saturated_cells"] == 1
    assert result["added"] == 20
