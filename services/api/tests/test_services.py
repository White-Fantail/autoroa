from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
import io
from PIL import Image
from app.services import GoogleMapsProvider, validate_image_content
from app.models import FillUp, FuelType, Observation, Profile, Source, Station, Vehicle, Verification

def test_image_content_validation_checks_decode_signature_mime_and_dimensions():
    output=io.BytesIO();Image.new("RGB",(8,6),"white").save(output,"JPEG");content=output.getvalue()
    assert validate_image_content(content,"image/jpeg")[:2]==(8,6)
    with pytest.raises(ValueError):validate_image_content(b"not an image","image/jpeg")
    with pytest.raises(ValueError):validate_image_content(content,"image/png")
    with pytest.raises(ValueError):validate_image_content(content,"image/jpeg",max_pixels=10)
from app.services import apply_economy, normalize_fuel_type, observation_anomaly, receipt_arithmetic_suspicious, resolve_current_price
def owner_vehicle(db):
    owner=Profile(auth_user_id=str(uuid.uuid4()));db.add(owner);db.flush();vehicle=Vehicle(user_id=owner.id,nickname="Test",make="Test",model="Car",fuel_type=FuelType.PETROL_91);db.add(vehicle);db.flush();return owner.id,vehicle.id
def fill(owner,vehicle,when,odo,litres,full=True,missed=False):return FillUp(user_id=owner,vehicle_id=vehicle,occurred_at=when,fuel_type=FuelType.PETROL_91,litres=Decimal(litres),total_amount=Decimal("50"),odometer_km=odo,full_tank=full,missed_previous_fill=missed)
def test_fuel_aliases_and_arithmetic():
    assert normalize_fuel_type("Unleaded 91")==FuelType.PETROL_91
    assert not receipt_arithmetic_suspicious(Decimal("40"),Decimal("2.5"),Decimal("100"))
    assert receipt_arithmetic_suspicious(Decimal("40"),Decimal("2.5"),Decimal("150"))
def test_full_to_full_with_partial(db):
    owner,v=owner_vehicle(db);now=datetime.now(timezone.utc);first=fill(owner,v,now-timedelta(days=2),80000,"40");partial=fill(owner,v,now-timedelta(days=1),80300,"20",False);db.add_all([first,partial]);db.commit();current=fill(owner,v,now,80650,"25");apply_economy(db,current)
    assert current.distance_since_previous_km==650
    assert current.fuel_economy_l_per_100km==Decimal("6.923")
def test_missed_fill_breaks_chain(db):
    owner,v=owner_vehicle(db);now=datetime.now(timezone.utc);db.add_all([fill(owner,v,now-timedelta(days=2),80000,"40"),fill(owner,v,now-timedelta(days=1),80300,"20",False,True)]);db.commit();current=fill(owner,v,now,80650,"25");apply_economy(db,current);assert current.fuel_economy_l_per_100km is None
def test_price_resolution_ignores_anomaly(db):
    station_row=Station(name="Price",address_line="1 Test",city="Test",latitude=Decimal("-40"),longitude=Decimal("175"));db.add(station_row);db.flush();station=station_row.id;now=datetime.now(timezone.utc)
    for price,anomaly in [("2.20",False),("9.99",True)]:db.add(Observation(station_id=station,fuel_type=FuelType.PETROL_91,pump_price_per_litre=Decimal(price),source=Source.RECEIPT,verification_level=Verification.VERIFIED_RECEIPT,observed_at=now,confidence_score=Decimal(".95"),is_anomaly=anomaly))
    db.commit();assert resolve_current_price(db,station,FuelType.PETROL_91).price==Decimal("2.2000")
    assert observation_anomaly(db,station,FuelType.PETROL_91,Decimal("4"))
def price_station(db):
    station=Station(name=str(uuid.uuid4()),address_line="1 Test",city="Test",latitude=Decimal("-40"),longitude=Decimal("175"));db.add(station);db.flush();return station
def test_current_price_prefers_verified_over_manual_and_fresh_over_stale(db):
    station=price_station(db);now=datetime.now(timezone.utc);db.add_all([
        Observation(station_id=station.id,fuel_type=FuelType.PETROL_91,pump_price_per_litre=Decimal("2.20"),source=Source.RECEIPT,verification_level=Verification.VERIFIED_RECEIPT,observed_at=now-timedelta(hours=1),confidence_score=Decimal(".95")),
        Observation(station_id=station.id,fuel_type=FuelType.PETROL_91,pump_price_per_litre=Decimal("2.30"),source=Source.COMMUNITY,verification_level=Verification.USER_CONFIRMED,observed_at=now,confidence_score=Decimal(".95")),
        Observation(station_id=station.id,fuel_type=FuelType.PETROL_91,pump_price_per_litre=Decimal("1.00"),source=Source.RECEIPT,verification_level=Verification.VERIFIED_RECEIPT,observed_at=now-timedelta(days=8),confidence_score=Decimal("1"))]);db.commit()
    assert resolve_current_price(db,station.id,FuelType.PETROL_91).price==Decimal("2.2000")
def test_independent_agreement_beats_same_user_repetition(db):
    station=price_station(db);now=datetime.now(timezone.utc);fills=[]
    for index in range(7):
        owner,vehicle=owner_vehicle(db) if index<2 else (fills[2].user_id,fills[2].vehicle_id) if index>2 else owner_vehicle(db);row=FillUp(user_id=owner,vehicle_id=vehicle,occurred_at=now-timedelta(minutes=index),fuel_type=FuelType.PETROL_91,litres=Decimal("10"),total_amount=Decimal("20"),odometer_km=100+index);db.add(row);db.flush();fills.append(row)
    for index,row in enumerate(fills):
        independently_agreed=index<2;db.add(Observation(station_id=station.id,fuel_type=FuelType.PETROL_91,pump_price_per_litre=Decimal("2.20") if independently_agreed else Decimal("2.40"),source=Source.COMMUNITY,verification_level=Verification.USER_CONFIRMED,observed_at=now,fill_up_id=row.id,confidence_score=Decimal(".65")))
    db.commit();assert resolve_current_price(db,station.id,FuelType.PETROL_91).price==Decimal("2.2000")
def test_google_provider_rejects_malformed_json(monkeypatch):
    class Response:
        def raise_for_status(self):pass
        def json(self):return {"places":"not-a-list"}
    monkeypatch.setattr("app.services.httpx.post",lambda *args,**kwargs:Response())
    with pytest.raises(ValueError):GoogleMapsProvider("key").text_search("Christchurch")
