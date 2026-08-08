export type FuelType='PETROL_91'|'PETROL_95'|'PETROL_98'|'DIESEL'|'OTHER';
export interface Vehicle {id:string;nickname:string;make:string;model:string;year?:number;fuel_type:FuelType;is_primary:boolean;is_archived:boolean}
export interface FillUp {id:string;vehicle_id:string;station_id?:string;occurred_at:string;fuel_type:FuelType;litres:string;pump_price_per_litre?:string;total_amount:string;odometer_km:number;full_tank:boolean;fuel_economy_l_per_100km?:string;cost_per_100km?:string}
export interface NearbyPrice {station:{id:string;name:string;address:string;latitude:string;longitude:string};distance_km:number;fuel_type:FuelType;price:string;observed_at:string;verification_level:string;confidence:string}
