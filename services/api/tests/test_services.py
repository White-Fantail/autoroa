from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from app.services import GoogleMapsProvider
from app.models import FillUp, FuelType, Observation, Source, Verification
from app.services import apply_economy, normalize_fuel_type, observation_anomaly, receipt_arithmetic_suspicious, resolve_current_price
def fill(vehicle,when,odo,litres,full=True,missed=False):return FillUp(user_id=uuid.uuid4(),vehicle_id=vehicle,occurred_at=when,fuel_type=FuelType.PETROL_91,litres=Decimal(litres),total_amount=Decimal("50"),odometer_km=odo,full_tank=full,missed_previous_fill=missed)
def test_fuel_aliases_and_arithmetic():
    assert normalize_fuel_type("Unleaded 91")==FuelType.PETROL_91
    assert not receipt_arithmetic_suspicious(Decimal("40"),Decimal("2.5"),Decimal("100"))
    assert receipt_arithmetic_suspicious(Decimal("40"),Decimal("2.5"),Decimal("150"))
def test_full_to_full_with_partial(db):
    v=uuid.uuid4();now=datetime.now(timezone.utc);first=fill(v,now-timedelta(days=2),80000,"40");partial=fill(v,now-timedelta(days=1),80300,"20",False);db.add_all([first,partial]);db.commit();current=fill(v,now,80650,"25");apply_economy(db,current)
    assert current.distance_since_previous_km==650
    assert current.fuel_economy_l_per_100km==Decimal("6.923")
def test_missed_fill_breaks_chain(db):
    v=uuid.uuid4();now=datetime.now(timezone.utc);db.add_all([fill(v,now-timedelta(days=2),80000,"40"),fill(v,now-timedelta(days=1),80300,"20",False,True)]);db.commit();current=fill(v,now,80650,"25");apply_economy(db,current);assert current.fuel_economy_l_per_100km is None
def test_price_resolution_ignores_anomaly(db):
    station=uuid.uuid4();now=datetime.now(timezone.utc)
    for price,anomaly in [("2.20",False),("9.99",True)]:db.add(Observation(station_id=station,fuel_type=FuelType.PETROL_91,pump_price_per_litre=Decimal(price),source=Source.RECEIPT,verification_level=Verification.VERIFIED_RECEIPT,observed_at=now,confidence_score=Decimal(".95"),is_anomaly=anomaly))
    db.commit();assert resolve_current_price(db,station,FuelType.PETROL_91).price==Decimal("2.2000")
    assert observation_anomaly(db,station,FuelType.PETROL_91,Decimal("4"))
def test_google_provider_rejects_malformed_json(monkeypatch):
    class Response:
        def raise_for_status(self):pass
        def json(self):return {"places":"not-a-list"}
    monkeypatch.setattr("app.services.httpx.post",lambda *args,**kwargs:Response())
    with pytest.raises(ValueError):GoogleMapsProvider("key").text_search("Christchurch")
