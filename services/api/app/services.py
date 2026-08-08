import base64, math, re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol
import httpx
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import FillUp, FuelType, Observation, CurrentPrice, Verification

ALIASES={"91":FuelType.PETROL_91,"REGULAR":FuelType.PETROL_91,"UNLEADED91":FuelType.PETROL_91,"ULP91":FuelType.PETROL_91,"95":FuelType.PETROL_95,"98":FuelType.PETROL_98,"DIESEL":FuelType.DIESEL}
def normalize_fuel_type(value:str)->FuelType: return ALIASES.get(re.sub(r"[^A-Z0-9]","",value.upper()),FuelType.OTHER)
def haversine_km(a,b,c,d):
    r=6371; p1,p2=math.radians(float(a)),math.radians(float(c)); dp=math.radians(float(c)-float(a)); dl=math.radians(float(d)-float(b)); x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2; return 2*r*math.asin(math.sqrt(x))
def receipt_arithmetic_suspicious(litres, price, total, discount=Decimal("0")):
    expected=Decimal(litres)*Decimal(price)-Decimal(discount or 0); tolerance=max(Decimal("2.00"),expected*Decimal("0.10")); return abs(expected-Decimal(total))>tolerance
def apply_economy(db:Session, fill:FillUp):
    fill.distance_since_previous_km=fill.fuel_economy_l_per_100km=fill.cost_per_100km=None
    if not fill.full_tank or fill.missed_previous_fill: return
    prior=list(db.scalars(select(FillUp).where(FillUp.vehicle_id==fill.vehicle_id,FillUp.occurred_at<fill.occurred_at).order_by(FillUp.occurred_at.desc())))
    litres=fill.litres; cost=fill.total_amount
    for item in prior:
        if item.missed_previous_fill: return
        if item.odometer_km>=fill.odometer_km: return
        if item.full_tank:
            distance=fill.odometer_km-item.odometer_km; fill.distance_since_previous_km=distance; fill.fuel_economy_l_per_100km=(litres/Decimal(distance)*100).quantize(Decimal(".001")); fill.cost_per_100km=(cost/Decimal(distance)*100).quantize(Decimal(".01")); return
        litres+=item.litres; cost+=item.total_amount
def recalculate_vehicle_economy(db:Session,vehicle_id):
    rows=list(db.scalars(select(FillUp).where(FillUp.vehicle_id==vehicle_id).order_by(FillUp.occurred_at)))
    for row in rows:
        apply_economy(db,row);db.flush()
def observation_anomaly(db:Session, station_id, fuel_type, price):
    if price<=0:return True
    recent=list(db.scalars(select(Observation).where(Observation.station_id==station_id,Observation.fuel_type==fuel_type,Observation.is_active.is_(True),Observation.is_anomaly.is_(False)).order_by(Observation.observed_at.desc()).limit(10)))
    vals=[x.pump_price_per_litre for x in recent if x.pump_price_per_litre]
    if not vals:return False
    avg=sum(vals,Decimal(0))/len(vals); return abs(price-avg)>max(Decimal("0.40"),avg*Decimal("0.20"))
def resolve_current_price(db:Session, station_id, fuel_type):
    rows=list(db.scalars(select(Observation).where(Observation.station_id==station_id,Observation.fuel_type==fuel_type,Observation.is_active.is_(True),Observation.is_anomaly.is_(False),Observation.pump_price_per_litre.is_not(None)).order_by(Observation.observed_at.desc()).limit(20)))
    if not rows:
        current=db.get(CurrentPrice,(station_id,fuel_type))
        if current:db.delete(current)
        return None
    now=datetime.now(timezone.utc)
    def score(o):
        observed=o.observed_at if o.observed_at.tzinfo else o.observed_at.replace(tzinfo=timezone.utc)
        age=max(0,(now-observed).total_seconds()/3600); verification={Verification.VERIFIED_RECEIPT:1,Verification.USER_CONFIRMED:.65,Verification.UNVERIFIED:.3}[o.verification_level]; agreement=sum(abs(x.pump_price_per_litre-o.pump_price_per_litre)<=Decimal(".03") for x in rows); return float(o.confidence_score)*verification*(1/(1+age/24))*(1+min(agreement,3)*.1)
    best=max(rows,key=score); current=db.get(CurrentPrice,(station_id,fuel_type)) or CurrentPrice(station_id=station_id,fuel_type=fuel_type)
    current.price=best.pump_price_per_litre; current.observed_at=best.observed_at; current.observation_id=best.id; current.confidence_score=best.confidence_score; current.verification_level=best.verification_level; db.add(current); return current
class ReceiptOCRProvider(Protocol):
    def extract_receipt(self, storage_path:str)->dict: ...
class OdometerOCRProvider(Protocol):
    def extract_odometer(self, storage_path:str)->dict: ...
class MockOCRProvider:
    def extract_receipt(self,path): return {"station_name":"NPD Moorhouse","station_address":"100 Moorhouse Avenue, Christchurch","transaction_datetime":datetime.now(timezone.utc).isoformat(),"fuel_type":"PETROL_91","litres":"42.300","pump_price_per_litre":"2.2390","paid_price_per_litre":"2.1990","discount_amount":"1.69","total_amount":"93.02","currency":"NZD","confidence":{"station":.96,"datetime":.92,"fuel_type":.98,"litres":.99,"price":.98,"discount":.93,"total":.99}}
    def extract_odometer(self,path): return {"odometer":83421,"unit":"KM","confidence":.96}
class ReceiptConfidence(BaseModel):
    model_config=ConfigDict(extra="forbid");station:float=Field(ge=0,le=1);datetime:float=Field(ge=0,le=1);fuel_type:float=Field(ge=0,le=1);litres:float=Field(ge=0,le=1);price:float=Field(ge=0,le=1);discount:float=Field(ge=0,le=1);total:float=Field(ge=0,le=1)
class ReceiptExtraction(BaseModel):
    model_config=ConfigDict(extra="forbid");station_name:str|None;station_address:str|None;transaction_datetime:datetime|None;fuel_type:Literal["PETROL_91","PETROL_95","PETROL_98","DIESEL","OTHER"]|None;litres:Decimal|None=Field(None,gt=0);pump_price_per_litre:Decimal|None=Field(None,gt=0);paid_price_per_litre:Decimal|None=Field(None,gt=0);discount_amount:Decimal|None=Field(None,ge=0);total_amount:Decimal|None=Field(None,gt=0);currency:Literal["NZD"];confidence:ReceiptConfidence
class OdometerExtraction(BaseModel):
    model_config=ConfigDict(extra="forbid");odometer:int|None=Field(None,ge=0);unit:Literal["KM","MI"];confidence:float=Field(ge=0,le=1)
class OpenAIOCRProvider:
    """Vision adapter whose validated domain result is independent of provider response shape."""
    def __init__(self,api_key:str,model:str="gpt-4.1-mini"):self.api_key=api_key;self.model=model
    def _extract(self,image:bytes,prompt:str,schema:dict):
        payload={"model":self.model,"input":[{"role":"user","content":[{"type":"input_text","text":prompt},{"type":"input_image","image_url":f"data:image/jpeg;base64,{base64.b64encode(image).decode()}"}]}],"text":{"format":{"type":"json_schema","name":"extraction","strict":True,"schema":schema}}}
        for attempt in range(3):
            try:
                response=httpx.post("https://api.openai.com/v1/responses",headers={"authorization":f"Bearer {self.api_key}"},json=payload,timeout=45);response.raise_for_status();return response.json()["output"][0]["content"][0]["text"]
            except (httpx.TimeoutException,httpx.NetworkError,httpx.HTTPStatusError):
                if attempt==2:raise
    def extract_receipt_bytes(self,image:bytes):
        prompt="Extract only visible NZ fuel receipt values. Use null when uncertain; never infer missing values. Return per-field confidence from 0 to 1."
        return ReceiptExtraction.model_validate_json(self._extract(image,prompt,ReceiptExtraction.model_json_schema())).model_dump(mode="json")
    def extract_odometer_bytes(self,image:bytes):
        prompt="Read the main vehicle odometer, distinguishing it from trip, range and speed displays. Lower confidence instead of guessing."
        return OdometerExtraction.model_validate_json(self._extract(image,prompt,OdometerExtraction.model_json_schema())).model_dump(mode="json")
class MapsProvider(Protocol):
    def nearby_stations(self,latitude:float,longitude:float,radius_km:float)->list[dict]: ...
class MockMapsProvider:
    def nearby_stations(self,latitude,longitude,radius_km):return []
class GoogleMapsProvider:
    def __init__(self,api_key:str):self.api_key=api_key
    def nearby_stations(self,latitude,longitude,radius_km):
        response=httpx.post("https://places.googleapis.com/v1/places:searchNearby",headers={"X-Goog-Api-Key":self.api_key,"X-Goog-FieldMask":"places.id,places.displayName,places.formattedAddress,places.location,places.addressComponents"},json={"includedTypes":["gas_station"],"maxResultCount":10,"regionCode":"NZ","locationRestriction":{"circle":{"center":{"latitude":latitude,"longitude":longitude},"radius":min(radius_km*1000,50000)}}},timeout=15);response.raise_for_status();payload=response.json()
        if not isinstance(payload,dict) or not isinstance(payload.get("places",[]),list):raise ValueError("Invalid Google Places response")
        return payload.get("places",[])
    def text_search(self,query:str):
        response=httpx.post("https://places.googleapis.com/v1/places:searchText",headers={"X-Goog-Api-Key":self.api_key,"X-Goog-FieldMask":"places.id,places.displayName,places.formattedAddress,places.location,places.addressComponents"},json={"textQuery":f"{query} fuel station New Zealand","includedType":"gas_station","regionCode":"NZ","maxResultCount":10},timeout=15);response.raise_for_status();payload=response.json()
        if not isinstance(payload,dict) or not isinstance(payload.get("places",[]),list):raise ValueError("Invalid Google Places response")
        return payload.get("places",[])
def station_match_score(query_name:str,address:str|None,station_name:str,station_address:str,distance_km:float):
    words=lambda value:set(re.sub(r"[^a-z0-9 ]","",(value or "").lower()).split())
    q,s=words(query_name),words(station_name);name=len(q&s)/max(1,len(q|s));address_score=len(words(address)&words(station_address))/max(1,len(words(address)|words(station_address)));distance=max(0,1-distance_km/10);return .6*name+.25*address_score+.15*distance
