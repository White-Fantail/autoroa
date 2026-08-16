from app.models import Station
from app.station_catalog import (
    CatalogCell,
    StationCatalogSaturatedCell,
    nz_catalog_cells,
    refinement_cells,
    sync_catalog_batch,
)


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


def test_refinement_cells_are_smaller_and_deeper():
    parent = CatalogCell(-43.53, 172.64, 8.0, "dense")
    children = refinement_cells(parent)
    assert len(children) == 4
    assert all(child.radius_km < parent.radius_km for child in children)
    assert all(child.refinement_depth == 1 for child in children)
    assert len({(child.latitude, child.longitude) for child in children}) == 4


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


def test_sync_batch_refines_and_persists_saturated_cells(db):
    calls = []

    def search(cell):
        calls.append(cell)
        if cell.refinement_depth == 0:
            return [place(f"parent-{index}", latitude=-43.0 + index * 0.001) for index in range(20)]
        return [place(f"child-{cell.refinement_depth}-{index}", latitude=-43.1 + index * 0.001) for index in range(5)]

    result = sync_catalog_batch(db, start_cursor=0, max_cells=1, search_cell=search)
    assert result["provider_results"] == 40
    assert result["saturated_cells"] == 1
    assert result["refinement_cells"] == 4
    assert result["added"] == 25
    assert len(result["saturated_cell_details"]) == 1
    detail = result["saturated_cell_details"][0]
    assert detail["result_count"] == 20
    assert detail["refinement_depth"] == 0
    saved = db.query(StationCatalogSaturatedCell).one()
    assert saved.result_count == 20
    assert saved.refinement_depth == 0


def test_sync_batch_refines_saturated_children_to_max_depth(db):
    def search(cell):
        return [place(f"depth-{cell.refinement_depth}-{index}", latitude=-43.0 + index * 0.001) for index in range(20)]

    result = sync_catalog_batch(db, start_cursor=0, max_cells=1, search_cell=search)
    assert result["provider_results"] == 21 * 20
    assert result["saturated_cells"] == 21
    assert result["refinement_cells"] == 20
    assert db.query(StationCatalogSaturatedCell).count() == 21
