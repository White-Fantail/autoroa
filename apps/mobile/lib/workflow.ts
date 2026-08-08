export type AuthState={session:'loading'|'signed-out'|'signed-in';vehicleCount:number};
export function nextRoute(state:AuthState){if(state.session==='loading')return null;if(state.session==='signed-out')return '/welcome';return state.vehicleCount?'/':'/onboarding/vehicle'}
export function chooseVehicle<T extends {id:string;is_primary:boolean}>(vehicles:T[],selected?:string){return vehicles.find(x=>x.id===selected)??vehicles.find(x=>x.is_primary)??vehicles[0]??null}
export function canSubmitFillUp(values:{litres:number;price:number;total:number;odometer:number},submitting:boolean){return !submitting&&values.litres>0&&values.price>0&&values.total>0&&values.odometer>=0}
export function isOdometerSequenceConflict(error:unknown){return error instanceof Error&&'status' in error&&error.status===409&&error.message.includes('Odometer sequence requires explicit confirmation')}
export function confidenceState(value:number){return value>=.9?'high':value>=.7?'medium':'attention'}
