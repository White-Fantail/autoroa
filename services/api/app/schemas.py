import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError
from typing import Literal
from urllib.parse import urlsplit
from .models import FuelType, MediaType

class ORM(BaseModel): model_config=ConfigDict(from_attributes=True)
class ProfileOut(ORM): id: uuid.UUID; display_name: str|None; country_code: str; preferred_currency: str; preferred_distance_unit: str; preferred_efficiency_unit: str
class ProfilePatch(BaseModel): display_name: str|None=Field(None,max_length=100); preferred_currency: Literal["NZD"]|None=None; preferred_distance_unit: Literal["km"]|None=None; preferred_efficiency_unit: Literal["L_PER_100KM"]|None=None
class VehicleIn(BaseModel): nickname: str=Field(min_length=1,max_length=80); make: str=Field(min_length=1,max_length=80); model: str=Field(min_length=1,max_length=80); year: int|None=Field(None,ge=1886,le=2100); variant: str|None=None; fuel_type: FuelType; registration_plate: str|None=Field(None,max_length=16); tank_capacity_litres: Decimal|None=Field(None,gt=0,le=1000); is_primary: bool=False
class VehiclePatch(BaseModel): nickname: str|None=None; make: str|None=None; model: str|None=None; year: int|None=Field(None,ge=1886,le=2100); variant: str|None=None; fuel_type: FuelType|None=None; registration_plate: str|None=None; tank_capacity_litres: Decimal|None=Field(None,gt=0); is_primary: bool|None=None; is_archived: bool|None=None
class VehicleOut(VehicleIn, ORM): id: uuid.UUID; is_archived: bool; created_at: datetime; updated_at: datetime
class MediaPrepare(BaseModel): type: MediaType; mime_type: str; file_size: int=Field(gt=0)
class MediaComplete(MediaPrepare): storage_token: str; width: int|None=None; height: int|None=None
class ReceiptCreate(BaseModel): media_asset_id: uuid.UUID
class AdminPriceBoardAnalyze(BaseModel): media_asset_id: uuid.UUID
class OCRJobCreate(BaseModel):
    kind: Literal["RECEIPT","ODOMETER","PRICE_BOARD"]
    resource_id: uuid.UUID
    station_id: uuid.UUID|None=None
class OdometerConfirm(BaseModel): reading_km: int=Field(ge=0)
class AdminPriceEntry(BaseModel): fuel_type: FuelType; price: Decimal=Field(gt=0,le=20)
class AdminPriceBoardCreate(BaseModel):
    media_asset_id: uuid.UUID|None=None
    observed_at: datetime
    prices: list[AdminPriceEntry]=Field(min_length=1,max_length=5)
class AdminBrandCreate(BaseModel):
    name: str=Field(min_length=1,max_length=120)
    slug: str=Field(min_length=1,max_length=120,pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    logo_url: str|None=Field(None,max_length=2048)
    @field_validator("name","slug")
    @classmethod
    def strip_required(cls,value:str)->str:
        value=value.strip()
        if not value:raise PydanticCustomError("blank","must not be blank")
        return value
    @field_validator("logo_url")
    @classmethod
    def normalize_optional(cls,value:str|None)->str|None:
        value=value.strip() or None if value is not None else None
        if value:
            try:parsed=urlsplit(value);parsed.port
            except ValueError as exc:raise PydanticCustomError("url","must be a valid HTTP(S) URL") from exc
            if parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password:raise PydanticCustomError("url","must be a valid HTTP(S) URL without credentials")
        return value
class AdminBrandPatch(BaseModel):
    name: str=Field(default=None,min_length=1,max_length=120)
    slug: str=Field(default=None,min_length=1,max_length=120,pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    logo_url: str|None=Field(None,max_length=2048)
    @field_validator("name","slug")
    @classmethod
    def strip_required(cls,value:str|None)->str|None:
        value=value.strip() if value is not None else None
        if value is not None and not value:raise PydanticCustomError("blank","must not be blank")
        return value
    @field_validator("logo_url")
    @classmethod
    def normalize_optional(cls,value:str|None)->str|None:
        value=value.strip() or None if value is not None else None
        if value:
            try:parsed=urlsplit(value);parsed.port
            except ValueError as exc:raise PydanticCustomError("url","must be a valid HTTP(S) URL") from exc
            if parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password:raise PydanticCustomError("url","must be a valid HTTP(S) URL without credentials")
        return value
class AdminStationCreate(BaseModel):
    brand_id: uuid.UUID|None=None
    name: str=Field(min_length=1,max_length=160)
    google_place_id: str|None=Field(None,max_length=255)
    address_line: str=Field(min_length=1,max_length=255)
    suburb: str|None=Field(None,max_length=120)
    city: str=Field(min_length=1,max_length=120)
    region: str|None=Field(None,max_length=120)
    postal_code: str|None=Field(None,max_length=20)
    country_code: str=Field("NZ",min_length=2,max_length=2,pattern=r"^[A-Za-z]{2}$")
    latitude: Decimal=Field(ge=-90,le=90)
    longitude: Decimal=Field(ge=-180,le=180)
    timezone: str=Field("Pacific/Auckland",min_length=1,max_length=100)
    is_active: bool=True
    @field_validator("name","address_line","city","timezone")
    @classmethod
    def strip_required(cls,value:str)->str:
        value=value.strip()
        if not value:raise PydanticCustomError("blank","must not be blank")
        return value
    @field_validator("google_place_id","suburb","region","postal_code")
    @classmethod
    def normalize_optional(cls,value:str|None)->str|None:return value.strip() or None if value is not None else None
    @field_validator("country_code")
    @classmethod
    def uppercase_country(cls,value:str)->str:return value.upper()
class AdminStationPatch(BaseModel):
    brand_id: uuid.UUID|None=None
    name: str=Field(default=None,min_length=1,max_length=160)
    google_place_id: str|None=Field(None,max_length=255)
    address_line: str=Field(default=None,min_length=1,max_length=255)
    suburb: str|None=Field(None,max_length=120)
    city: str=Field(default=None,min_length=1,max_length=120)
    region: str|None=Field(None,max_length=120)
    postal_code: str|None=Field(None,max_length=20)
    country_code: str=Field(default=None,min_length=2,max_length=2,pattern=r"^[A-Za-z]{2}$")
    latitude: Decimal=Field(default=None,ge=-90,le=90)
    longitude: Decimal=Field(default=None,ge=-180,le=180)
    timezone: str=Field(default=None,min_length=1,max_length=100)
    is_active: bool=None
    @field_validator("name","address_line","city","timezone")
    @classmethod
    def strip_required(cls,value:str|None)->str|None:
        value=value.strip() if value is not None else None
        if value is not None and not value:raise PydanticCustomError("blank","must not be blank")
        return value
    @field_validator("google_place_id","suburb","region","postal_code")
    @classmethod
    def normalize_optional(cls,value:str|None)->str|None:return value.strip() or None if value is not None else None
    @field_validator("country_code")
    @classmethod
    def uppercase_country(cls,value:str|None)->str|None:return value.upper() if value else value
class OdometerCreate(BaseModel): media_asset_id: uuid.UUID; vehicle_id: uuid.UUID
class FillUpIn(BaseModel):
    vehicle_id: uuid.UUID; station_id: uuid.UUID|None=None; occurred_at: datetime; fuel_type: FuelType; litres: Decimal=Field(gt=0,le=1000); pump_price_per_litre: Decimal|None=Field(None,gt=0,le=20); paid_price_per_litre: Decimal|None=Field(None,gt=0,le=20); subtotal: Decimal|None=Field(None,ge=0); discount_amount: Decimal|None=Field(None,ge=0); total_amount: Decimal=Field(gt=0); odometer_km: int=Field(ge=0); full_tank: bool=True; missed_previous_fill: bool=False; notes: str|None=Field(None,max_length=1000); receipt_id: uuid.UUID|None=None; odometer_image_id: uuid.UUID|None=None; acknowledge_fuel_type_mismatch:bool=False; acknowledge_tank_capacity:bool=False; acknowledge_arithmetic_warning:bool=False
class FillUpPatch(BaseModel): station_id: uuid.UUID|None=None; occurred_at: datetime|None=None; fuel_type:FuelType|None=None; litres: Decimal|None=Field(None,gt=0); pump_price_per_litre: Decimal|None=Field(None,gt=0); paid_price_per_litre: Decimal|None=Field(None,gt=0); subtotal:Decimal|None=Field(None,ge=0);discount_amount:Decimal|None=Field(None,ge=0);total_amount: Decimal|None=Field(None,gt=0); odometer_km: int|None=Field(None,ge=0); full_tank: bool|None=None; missed_previous_fill: bool|None=None; notes: str|None=None;odometer_image_id:uuid.UUID|None=None;acknowledge_fuel_type_mismatch:bool=False;acknowledge_tank_capacity:bool=False;acknowledge_arithmetic_warning:bool=False
class FillUpOut(ORM):
    id:uuid.UUID;vehicle_id:uuid.UUID;station_id:uuid.UUID|None;occurred_at:datetime;fuel_type:FuelType;litres:Decimal;pump_price_per_litre:Decimal|None;paid_price_per_litre:Decimal|None;subtotal:Decimal|None;discount_amount:Decimal|None;total_amount:Decimal;odometer_km:int;full_tank:bool;missed_previous_fill:bool;notes:str|None;receipt_id:uuid.UUID|None;odometer_image_id:uuid.UUID|None;distance_since_previous_km:int|None;fuel_economy_l_per_100km:Decimal|None;cost_per_100km:Decimal|None;economy_is_valid:bool;economy_warning:str|None;created_at:datetime
class ReceiptConfirm(BaseModel): station_id: uuid.UUID|None=None; station_text: str|None=None; fuel_type: FuelType; litres: Decimal=Field(gt=0); pump_price_per_litre: Decimal=Field(gt=0); discount_amount: Decimal|None=Field(None,ge=0); total_amount: Decimal=Field(gt=0); transaction_datetime: datetime; acknowledge_arithmetic_warning:bool=False
class Metrics(BaseModel): distance_km:int; fuel_litres:Decimal; fuel_spend:Decimal; average_fuel_economy_l_per_100km:Decimal|None; average_cost_per_100km:Decimal|None; fill_up_count:int
