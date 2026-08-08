from decimal import Decimal
import pytest
from app.services import OdometerExtraction, ReceiptExtraction, station_match_score

CONFIDENCE={"station":.95,"datetime":.94,"fuel_type":.98,"litres":.99,"price":.98,"discount":.9,"total":.99}
BASE={"station_name":"Z Energy","station_address":"1 Queen Street, Auckland","transaction_datetime":"2026-08-01T10:30:00+12:00","fuel_type":"PETROL_91","litres":"40","pump_price_per_litre":"2.50","paid_price_per_litre":"2.50","discount_amount":"0","total_amount":"100","currency":"NZD","confidence":CONFIDENCE}
@pytest.mark.parametrize("name,changes",[
    ("valid_nz_petrol",{}),("discounted",{"paid_price_per_litre":"2.40","discount_amount":"4","total_amount":"96"}),
    ("unclear",{"station_name":None,"litres":None,"confidence":{**CONFIDENCE,"station":.2,"litres":.3}}),
    ("non_fuel",{"fuel_type":None,"litres":None,"pump_price_per_litre":None,"paid_price_per_litre":None}),
    ("other_purchases",{"total_amount":"112.50"}),
])
def test_receipt_fixture_variants(name,changes):
    value=ReceiptExtraction.model_validate({**BASE,**changes});assert value.currency=="NZD";assert 0<=value.confidence.total<=1
    if name=="discounted":assert value.discount_amount==Decimal("4")
def test_odometer_and_ambiguous_dashboard_fixtures():
    assert OdometerExtraction.model_validate({"odometer":83421,"unit":"KM","confidence":.98}).odometer==83421
    ambiguous=OdometerExtraction.model_validate({"odometer":None,"unit":"KM","confidence":.2});assert ambiguous.odometer is None
def test_station_matching_prefers_name_address_and_distance():
    close=station_match_score("Z Energy Queen St","1 Queen Street","Z Energy Queen Street","1 Queen Street",.2)
    far=station_match_score("Z Energy Queen St","1 Queen Street","Another Fuel","99 Other Road",9)
    assert close>far and close>.7
def _media(client,headers,kind):
    import io
    from PIL import Image
    output=io.BytesIO();Image.new("RGB",(4,4),"white").save(output,"JPEG");content=output.getvalue();prepared=client.post("/api/v1/media/upload-url",json={"type":kind,"mime_type":"image/jpeg","file_size":len(content)},headers=headers).json();assert client.put(prepared["upload_url"],content=content,headers={**headers,"content-type":"image/jpeg"}).status_code==204;return client.post("/api/v1/media/complete",json={"storage_token":prepared["storage_token"],"type":kind,"mime_type":"image/jpeg","file_size":len(content)},headers=headers).json()
@pytest.mark.parametrize("confidence,status",[(.96,"READY"),(.55,"REVIEW_REQUIRED")])
def test_receipt_api_uses_substituted_mock_and_persists(client,user_headers,monkeypatch,confidence,status):
    result={**BASE,"confidence":{key:confidence for key in CONFIDENCE}}
    monkeypatch.setattr("app.routes.MockOCRProvider.extract_receipt",lambda self,path:result)
    receipt=client.post("/api/v1/receipts",json={"media_asset_id":_media(client,user_headers,"RECEIPT")["id"]},headers=user_headers).json();processed=client.post(f"/api/v1/receipts/{receipt['id']}/process",headers=user_headers).json();assert processed["processing_status"]==status;assert processed["station_text"]=="Z Energy";assert Decimal(str(processed["litres"]))==Decimal("40")
def test_receipt_api_provider_failure_is_persisted(client,user_headers,monkeypatch):
    monkeypatch.setattr("app.routes.MockOCRProvider.extract_receipt",lambda self,path:(_ for _ in ()).throw(RuntimeError("fixture failure")))
    receipt=client.post("/api/v1/receipts",json={"media_asset_id":_media(client,user_headers,"RECEIPT")["id"]},headers=user_headers).json();processed=client.post(f"/api/v1/receipts/{receipt['id']}/process",headers=user_headers).json();assert processed["processing_status"]=="FAILED";assert processed["error_code"]=="RECEIPT_PROCESSING_FAILED"
def test_odometer_api_ready_review_and_failure(client,user_headers,monkeypatch):
    vehicle=client.post("/api/v1/vehicles",json={"nickname":"OCR","make":"Test","model":"Car","fuel_type":"PETROL_91"},headers=user_headers).json()
    for value,status in [({"odometer":83421,"unit":"KM","confidence":.96},"READY"),({"odometer":None,"unit":"KM","confidence":.2},"REVIEW_REQUIRED")]:
        monkeypatch.setattr("app.routes.MockOCRProvider.extract_odometer",lambda self,path,value=value:value);reading=client.post("/api/v1/odometer-readings",json={"media_asset_id":_media(client,user_headers,"ODOMETER")["id"],"vehicle_id":vehicle["id"]},headers=user_headers).json();processed=client.post(f"/api/v1/odometer-readings/{reading['id']}/process",headers=user_headers).json();assert processed["processing_status"]==status
