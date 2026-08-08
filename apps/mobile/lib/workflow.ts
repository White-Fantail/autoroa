export type AuthState={session:'loading'|'signed-out'|'signed-in';vehicleCount:number};
export function nextRoute(state:AuthState){if(state.session==='loading')return null;if(state.session==='signed-out')return '/welcome';return state.vehicleCount?'/':'/onboarding/vehicle'}
export function chooseVehicle<T extends {id:string;is_primary:boolean}>(vehicles:T[],selected?:string){return vehicles.find(x=>x.id===selected)??vehicles.find(x=>x.is_primary)??vehicles[0]??null}
export function canSubmitFillUp(values:{litres:number;price:number;total:number;odometer:number},submitting:boolean){return !submitting&&values.litres>0&&values.price>0&&values.total>0&&values.odometer>=0}
export function isOdometerSequenceConflict(error:unknown){return error instanceof Error&&'status' in error&&error.status===409&&error.message.includes('Odometer sequence requires explicit confirmation')}
export function confidenceState(value:number){return value>=.9?'high':value>=.7?'medium':'attention'}

export type EditFillUpWarning='ODOMETER_SEQUENCE_CONFLICT'|'FUEL_TYPE_MISMATCH'|'TANK_CAPACITY_WARNING'|'ARITHMETIC_WARNING';
export type EditFillUpAcknowledgements={confirmLowerOdometer:boolean;fuelTypeMismatch:boolean;tankCapacity:boolean;arithmetic:boolean};
export const emptyEditFillUpAcknowledgements=():EditFillUpAcknowledgements=>({confirmLowerOdometer:false,fuelTypeMismatch:false,tankCapacity:false,arithmetic:false});
export function classifyEditFillUpWarning(error:unknown):EditFillUpWarning|undefined{
  if(!(error instanceof Error)||!('status' in error)||error.status!==409)return undefined;
  const code='code' in error?error.code:undefined;
  if(code==='FUEL_TYPE_MISMATCH'||code==='TANK_CAPACITY_WARNING'||code==='ARITHMETIC_WARNING')return code;
  return error.message.includes('Odometer sequence requires explicit confirmation')?'ODOMETER_SEQUENCE_CONFLICT':undefined;
}
export function acknowledgeEditFillUpWarning(current:EditFillUpAcknowledgements,warning:EditFillUpWarning):EditFillUpAcknowledgements{
  if(warning==='ODOMETER_SEQUENCE_CONFLICT')return {...current,confirmLowerOdometer:true};
  if(warning==='FUEL_TYPE_MISMATCH')return {...current,fuelTypeMismatch:true};
  if(warning==='TANK_CAPACITY_WARNING')return {...current,tankCapacity:true};
  return {...current,arithmetic:true};
}
export const editFillUpWarningMessage=(warning:EditFillUpWarning)=>({
  ODOMETER_SEQUENCE_CONFLICT:'This odometer reading conflicts with another reading before or after this fill-up date. Check the date and odometer value before saving.',
  FUEL_TYPE_MISMATCH:"The selected fuel differs from the vehicle's configured fuel type. Check the fuel type before saving.",
  TANK_CAPACITY_WARNING:'The entered litres are substantially higher than the configured tank capacity. Check the litres before saving.',
  ARITHMETIC_WARNING:'Litres × pump price − discount does not approximately match the entered total. Check the amounts before saving.',
}[warning]);
export function editFillUpRequest(id:string,data:Record<string,unknown>,acknowledgements:EditFillUpAcknowledgements){
  return {
    path:`/fill-ups/${id}?confirm_lower_odometer=${acknowledgements.confirmLowerOdometer}`,
    body:{...data,acknowledge_fuel_type_mismatch:acknowledgements.fuelTypeMismatch,acknowledge_tank_capacity:acknowledgements.tankCapacity,acknowledge_arithmetic_warning:acknowledgements.arithmetic},
  };
}
export async function patchEditedFillUp(patch:(path:string,body:unknown)=>Promise<unknown>,id:string,data:Record<string,unknown>,acknowledgements:EditFillUpAcknowledgements){
  const request=editFillUpRequest(id,data,acknowledgements);
  return patch(request.path,request.body);
}
export async function invalidateEditedFillUpQueries(invalidate:(options:{queryKey:string[]})=>Promise<unknown>){
  await Promise.all([invalidate({queryKey:['fillups']}),invalidate({queryKey:['car-metrics']})]);
}
