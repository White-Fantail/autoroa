import {z} from 'zod';
export const fuelTypes=['PETROL_91','PETROL_95','PETROL_98','DIESEL','OTHER'] as const;
export const vehicleSchema=z.object({nickname:z.string().min(1),make:z.string().min(1),model:z.string().min(1),year:z.coerce.number().int().min(1886).max(2100).optional(),fuel_type:z.enum(fuelTypes)});
export const fillUpSchema=z.object({vehicle_id:z.string().uuid(),station_id:z.string().uuid().optional(),occurred_at:z.string().datetime(),fuel_type:z.enum(fuelTypes),litres:z.coerce.number().positive(),pump_price_per_litre:z.coerce.number().positive(),total_amount:z.coerce.number().positive(),odometer_km:z.coerce.number().int().nonnegative(),full_tank:z.boolean(),missed_previous_fill:z.boolean()});
export type FillUpForm=z.infer<typeof fillUpSchema>;
