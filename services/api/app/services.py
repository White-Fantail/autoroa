import base64, hashlib, io, math, re, warnings
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Protocol
import httpx
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, model_validator
from typing import Literal
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import FillUp, FuelType, Observation, CurrentPrice, Receipt, Verification

ALIASES={"91":FuelType.PETROL_91,"REGULAR":FuelType.PETROL_91,"UNLEADED91":FuelType.PETROL_91,"ULP91":FuelType.PETROL_91,"95":FuelType.PETROL_95,"98":FuelType.PETROL_98,"DIESEL":FuelType.DIESEL}
def normalize_fuel_type(value:str)->FuelType: return ALIASES.get(re.sub(r"[^A-Z0-9]","",value.upper()),FuelType.OTHER)
def haversine_km(a,b,c,d):
    r=6371; p1,p2=math.radians(float(a)),math.radians(float(c)); dp=math.radians(float(c)-float(a)); dl=math.radians(float(d)-float(b)); x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2; return 2*r*math.asin(math.sqrt(x))
def receipt_arithmetic_suspicious(litres, price, total, discount=Decimal("0")):
    expected=Decimal(litres)*Decimal(price)-Decimal(discount or 0); tolerance=max(Decimal("2.00"),expected*Decimal("0.10")); return abs(expected-Decimal(total))>tolerance
def apply_economy(db:Session, fill:FillUp):
    fill.distance_since_previous_km=fill.fuel_economy_l_per_100km=fill.cost_per_100km=None
    fill.economy_fuel_litres=fill.economy_cost_amount=fill.economy_started_at=None;fill.economy_is_valid=False;fill.economy_warning=None
    if not fill.full_tank:return
    if fill.missed_previous_fill:fill.economy_warning="MISSED_PREVIOUS_FILL";return
    prior=list(db.scalars(select(FillUp).where(FillUp.vehicle_id==fill.vehicle_id,FillUp.id!=fill.id,FillUp.occurred_at<fill.occurred_at).order_by(FillUp.occurred_at.desc(),FillUp.id.desc())))
    litres=fill.litres; cost=fill.total_amount
    for item in prior:
        if item.missed_previous_fill:fill.economy_warning="MISSED_FILL_CHAIN";return
        if item.odometer_km>=fill.odometer_km:fill.economy_warning="NON_INCREASING_ODOMETER";return
        if item.full_tank:
            distance=fill.odometer_km-item.odometer_km; economy=litres/Decimal(distance)*100
            fill.distance_since_previous_km=distance;fill.economy_fuel_litres=litres;fill.economy_cost_amount=cost;fill.economy_started_at=item.occurred_at
            if distance<10:fill.economy_warning="DISTANCE_TOO_SHORT";return
            if economy<Decimal("0.5") or economy>Decimal("100"):fill.economy_warning="ECONOMY_OUTLIER";return
            fill.fuel_economy_l_per_100km=economy.quantize(Decimal(".001"));fill.cost_per_100km=(cost/Decimal(distance)*100).quantize(Decimal(".01"));fill.economy_is_valid=True;return
        litres+=item.litres; cost+=item.total_amount
def recalculate_vehicle_economy(db:Session,vehicle_id):
    rows=list(db.scalars(select(FillUp).where(FillUp.vehicle_id==vehicle_id).order_by(FillUp.occurred_at)))
    for row in rows:
        apply_economy(db,row);db.flush()

SUPPORTED_IMAGE_FORMATS={"JPEG":"image/jpeg","PNG":"image/png","WEBP":"image/webp"}
def validate_image_content(content:bytes,declared_mime:str,max_pixels:int=40_000_000):
    """Decode uploaded bytes with Pillow and return their trusted metadata and hash."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error",Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                width,height=image.size;fmt=image.format
                if width*height>max_pixels:raise ValueError("Image dimensions are too large")
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                image.load()
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise ValueError("Uploaded content is not a safe supported image") from exc
    actual_mime=SUPPORTED_IMAGE_FORMATS.get(fmt or "")
    if not actual_mime or actual_mime!=declared_mime:
        raise ValueError("Uploaded content is not a safe supported image")
    return width,height,hashlib.sha256(content).hexdigest()
def observation_anomaly(db:Session, station_id, fuel_type, price):
    if price<=0:return True
    recent=list(db.scalars(select(Observation).where(Observation.station_id==station_id,Observation.fuel_type==fuel_type,Observation.is_active.is_(True),Observation.is_anomaly.is_(False)).order_by(Observation.observed_at.desc()).limit(10)))
    vals=[x.pump_price_per_litre for x in recent if x.pump_price_per_litre]
    if not vals:return False
    avg=sum(vals,Decimal(0))/len(vals); return abs(price-avg)>max(Decimal("0.40"),avg*Decimal("0.20"))
def resolve_current_price(db:Session, station_id, fuel_type):
    rows=list(db.scalars(select(Observation).where(Observation.station_id==station_id,Observation.fuel_type==fuel_type,Observation.is_active.is_(True),Observation.is_anomaly.is_(False),Observation.pump_price_per_litre.is_not(None)).order_by(Observation.observed_at.desc()).limit(20)))
    now=datetime.now(timezone.utc)
    rows=[row for row in rows if now-(row.observed_at if row.observed_at.tzinfo else row.observed_at.replace(tzinfo=timezone.utc))<=timedelta(days=7)]
    if not rows:
        current=db.get(CurrentPrice,(station_id,fuel_type))
        if current:db.delete(current)
        return None
    fill_owners={fill.id:fill.user_id for fill in db.scalars(select(FillUp).where(FillUp.id.in_([row.fill_up_id for row in rows if row.fill_up_id])))}
    receipt_owners={receipt.id:receipt.user_id for receipt in db.scalars(select(Receipt).where(Receipt.id.in_([row.receipt_id for row in rows if row.receipt_id])))}
    def contributor(o):return fill_owners.get(o.fill_up_id) or receipt_owners.get(o.receipt_id) or o.id
    def score(o):
        observed=o.observed_at if o.observed_at.tzinfo else o.observed_at.replace(tzinfo=timezone.utc)
        age=max(0,(now-observed).total_seconds()/3600); verification={Verification.VERIFIED_RECEIPT:1,Verification.USER_CONFIRMED:.65,Verification.UNVERIFIED:.3}[o.verification_level]; agreement=len({contributor(x) for x in rows if abs(x.pump_price_per_litre-o.pump_price_per_litre)<=Decimal(".03")}); return float(o.confidence_score)*verification*(1/(1+age/24))*(1+min(agreement,3)*.1)
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
ReceiptPositiveNumber=Annotated[Decimal,Field(gt=0),WithJsonSchema({"type":"number","exclusiveMinimum":0})]
ReceiptDiscountNumber=Annotated[Decimal,WithJsonSchema({"type":"number"})]
class ReceiptExtraction(BaseModel):
    model_config=ConfigDict(extra="forbid");station_name:str|None;station_address:str|None;transaction_datetime:datetime|None;fuel_type:Literal["PETROL_91","PETROL_95","PETROL_98","DIESEL","OTHER"]|None;litres:ReceiptPositiveNumber|None;pump_price_per_litre:ReceiptPositiveNumber|None;paid_price_per_litre:ReceiptPositiveNumber|None;discount_amount:ReceiptDiscountNumber|None=Field(ge=0);total_amount:ReceiptPositiveNumber|None;currency:Literal["NZD"];confidence:ReceiptConfidence

    @model_validator(mode="before")
    @classmethod
    def normalize_signed_discount(cls,value):
        if not isinstance(value,dict) or value.get("discount_amount") is None:return value
        normalized=dict(value);raw=normalized["discount_amount"]
        try:amount=Decimal(str(raw).strip().replace("$","").replace(",",""))
        except Exception:return value
        if amount<0:
            normalized["discount_amount"]=abs(amount)
            confidence=normalized.get("confidence")
            if isinstance(confidence,dict):normalized["confidence"]={**confidence,"discount":min(float(confidence.get("discount",0)),.89)}
        return normalized
class OdometerExtraction(BaseModel):
    model_config=ConfigDict(extra="forbid");odometer:int|None=Field(None,ge=0);unit:Literal["KM","MI"];confidence:float=Field(ge=0,le=1)
PricePerLitre=Annotated[Decimal,Field(gt=0,le=20),WithJsonSchema({"type":"number","exclusiveMinimum":0,"maximum":20})]
class PriceBoardEntry(BaseModel):
    model_config=ConfigDict(extra="forbid");fuel_type:Literal["PETROL_91","PETROL_95","PETROL_98","DIESEL","OTHER"];price_per_litre:PricePerLitre;confidence:float=Field(ge=0,le=1)
class PriceBoardExtraction(BaseModel):
    model_config=ConfigDict(extra="forbid");prices:list[PriceBoardEntry]=Field(max_length=5)
class OCRProviderResponseError(ValueError):
    """The OCR provider returned a successful but unusable response envelope."""
class OpenAIOCRProvider:
    """Vision adapter whose validated domain result is independent of provider response shape."""
    def __init__(self,api_key:str,model:str="gpt-4.1-mini"):self.api_key=api_key;self.model=model
    @staticmethod
    def _structured_output_text(body)->str:
        if not isinstance(body,dict) or not isinstance(body.get("output"),list):raise OCRProviderResponseError("OpenAI response envelope is invalid")
        for output in body["output"]:
            if not isinstance(output,dict):raise OCRProviderResponseError("OpenAI response envelope is invalid")
            if output.get("type")!="message":continue
            if not isinstance(output.get("content"),list):raise OCRProviderResponseError("OpenAI response envelope is invalid")
            for content in output["content"]:
                if not isinstance(content,dict):raise OCRProviderResponseError("OpenAI response envelope is invalid")
                if content.get("type")=="output_text" and isinstance(content.get("text"),str):return content["text"]
        raise OCRProviderResponseError("OpenAI response did not contain structured output text")
    def _extract(self,image:bytes,prompt:str,schema:dict,mime_type:str="image/jpeg"):
        payload={"model":self.model,"input":[{"role":"user","content":[{"type":"input_text","text":prompt},{"type":"input_image","image_url":f"data:{mime_type};base64,{base64.b64encode(image).decode()}"}]}],"text":{"format":{"type":"json_schema","name":"extraction","strict":True,"schema":schema}}}
        for attempt in range(3):
            try:
                response=httpx.post("https://api.openai.com/v1/responses",headers={"authorization":f"Bearer {self.api_key}"},json=payload,timeout=45);response.raise_for_status()
                try:body=response.json()
                except (ValueError,TypeError) as exc:raise OCRProviderResponseError("OpenAI response body is not valid JSON") from exc
                return self._structured_output_text(body)
            except (httpx.TimeoutException,httpx.NetworkError,httpx.HTTPStatusError):
                if attempt==2:raise
    def extract_receipt_bytes(self,image:bytes,mime_type:str="image/jpeg"):
        prompt=("Extract only visible NZ fuel receipt values. Use null when uncertain; never infer missing values. "
                "Return discount_amount as a non-negative discount magnitude even when the receipt prints it with a minus sign; "
                "for example, -$1.74 means discount_amount 1.74. Return per-field confidence from 0 to 1.")
        return ReceiptExtraction.model_validate_json(self._extract(image,prompt,ReceiptExtraction.model_json_schema(),mime_type)).model_dump(mode="json")
    def extract_odometer_bytes(self,image:bytes,mime_type:str="image/jpeg"):
        prompt="Read the main vehicle odometer, distinguishing it from trip, range and speed displays. Lower confidence instead of guessing."
        return OdometerExtraction.model_validate_json(self._extract(image,prompt,OdometerExtraction.model_json_schema(),mime_type)).model_dump(mode="json")
    def extract_price_board_bytes(self,image:bytes,mime_type:str="image/jpeg"):
        prompt=("Extract only fuel types and visibly paired prices from this New Zealand fuel-station price board. "
                "Return prices as NZD per litre (for example, 245.9 cents is 2.459 NZD). "
                "Map regular/unleaded to PETROL_91 and premium labels only when their octane is visible. "
                "Use OTHER only for a clearly visible fuel that cannot be mapped. Omit uncertain or unpaired values; never infer missing values.")
        return PriceBoardExtraction.model_validate_json(self._extract(image,prompt,PriceBoardExtraction.model_json_schema(),mime_type)).model_dump(mode="json")
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
