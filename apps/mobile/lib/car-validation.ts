import {z} from 'zod';
export const fuels=['PETROL_91','PETROL_95','PETROL_98','DIESEL','OTHER'] as const;
const optionalNumber=(schema:z.ZodNumber)=>z.union([z.null(),z.literal(''),z.coerce.number().pipe(schema)]).transform(value=>value===''?null:value);
const optionalText=(max:number)=>z.string().max(max).nullable().transform(value=>value??'');
export const vehicleEditSchema=z.object({nickname:z.string().trim().min(1),make:z.string().trim().min(1),model:z.string().trim().min(1),year:optionalNumber(z.number().int().min(1886).max(2100)),variant:optionalText(100),fuel_type:z.enum(fuels),registration_plate:optionalText(16),tank_capacity_litres:optionalNumber(z.number().positive().max(1000))});
export const fillEditSchema=z.object({station_id:z.union([z.null(),z.literal(''),z.string().uuid()]).transform(value=>value||null),occurred_at:z.string().datetime(),fuel_type:z.enum(fuels),litres:z.coerce.number().positive().max(1000),pump_price_per_litre:optionalNumber(z.number().positive().max(20)),discount_amount:optionalNumber(z.number().nonnegative()),total_amount:z.coerce.number().positive(),odometer_km:z.coerce.number().int().nonnegative(),notes:optionalText(1000),full_tank:z.boolean(),missed_previous_fill:z.boolean()});
export function selectStation<T extends {id:string}>(current:T|undefined){return current?.id??null}
