import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
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
class OdometerCreate(BaseModel): media_asset_id: uuid.UUID; vehicle_id: uuid.UUID
class FillUpIn(BaseModel):
    vehicle_id: uuid.UUID; station_id: uuid.UUID|None=None; occurred_at: datetime; fuel_type: FuelType; litres: Decimal=Field(gt=0,le=1000); pump_price_per_litre: Decimal|None=Field(None,gt=0,le=20); paid_price_per_litre: Decimal|None=Field(None,gt=0,le=20); subtotal: Decimal|None=Field(None,ge=0); discount_amount: Decimal|None=Field(None,ge=0); total_amount: Decimal=Field(gt=0); odometer_km: int=Field(ge=0); full_tank: bool=True; missed_previous_fill: bool=False; notes: str|None=Field(None,max_length=1000); receipt_id: uuid.UUID|None=None; odometer_image_id: uuid.UUID|None=None
class FillUpPatch(BaseModel): station_id: uuid.UUID|None=None; occurred_at: datetime|None=None; fuel_type:FuelType|None=None; litres: Decimal|None=Field(None,gt=0); pump_price_per_litre: Decimal|None=Field(None,gt=0); paid_price_per_litre: Decimal|None=Field(None,gt=0); subtotal:Decimal|None=Field(None,ge=0);discount_amount:Decimal|None=Field(None,ge=0);total_amount: Decimal|None=Field(None,gt=0); odometer_km: int|None=Field(None,ge=0); full_tank: bool|None=None; missed_previous_fill: bool|None=None; notes: str|None=None;odometer_image_id:uuid.UUID|None=None
class FillUpOut(FillUpIn, ORM): id: uuid.UUID; distance_since_previous_km: int|None; fuel_economy_l_per_100km: Decimal|None; cost_per_100km: Decimal|None; created_at: datetime
class ReceiptConfirm(BaseModel): station_id: uuid.UUID|None=None; station_text: str|None=None; fuel_type: FuelType; litres: Decimal=Field(gt=0); pump_price_per_litre: Decimal=Field(gt=0); discount_amount: Decimal|None=Field(None,ge=0); total_amount: Decimal=Field(gt=0); transaction_datetime: datetime; acknowledge_arithmetic_warning:bool=False
class Metrics(BaseModel): distance_km:int; fuel_litres:Decimal; fuel_spend:Decimal; average_fuel_economy_l_per_100km:Decimal|None; average_cost_per_100km:Decimal|None; fill_up_count:int
