import {describe,expect,it,vi} from 'vitest';import {ApiError,createApiClient} from '../../../packages/api-client/src';import {acknowledgeEditFillUpWarning,canSubmitFillUp,chooseVehicle,classifyEditFillUpWarning,confidenceState,editFillUpWarningMessage,emptyEditFillUpAcknowledgements,invalidateEditedFillUpQueries,isOdometerSequenceConflict,nextRoute,patchEditedFillUp,restoredFillUpStep} from './workflow';
describe('critical mobile workflow',()=>{it('routes auth and onboarding state',()=>{expect(nextRoute({session:'signed-out',vehicleCount:0})).toBe('/welcome');expect(nextRoute({session:'signed-in',vehicleCount:0})).toBe('/onboarding/vehicle')});it('defaults to primary vehicle',()=>expect(chooseVehicle([{id:'a',is_primary:false},{id:'b',is_primary:true}])?.id).toBe('b'));it('validates and locks fill-up submissions',()=>{const valid={litres:42,price:2.2,total:92,odometer:80000};expect(canSubmitFillUp(valid,false)).toBe(true);expect(canSubmitFillUp(valid,true)).toBe(false);expect(canSubmitFillUp({...valid,litres:0},false)).toBe(false)});it('makes low OCR confidence explicit',()=>{expect(confidenceState(.95)).toBe('high');expect(confidenceState(.75)).toBe('medium');expect(confidenceState(.4)).toBe('attention')});it('exposes parsed server odometer conflicts for histories beyond the client preview',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'Odometer sequence requires explicit confirmation'}),{status:409,headers:{'content-type':'application/json'}})));const client=createApiClient('http://api.test',async()=>null);let error:unknown;try{await client.post('/fill-ups',{})}catch(caught){error=caught}expect(isOdometerSequenceConflict(error)).toBe(true);vi.unstubAllGlobals()})});

describe('fill-up draft restoration',()=>{
  it('returns a persisted success step to review because results are not persisted',()=>{
    expect(restoredFillUpStep(4)).toBe(3);
    expect(restoredFillUpStep(2)).toBe(2);
  });
});

describe('edit fill-up confirmations',()=>{
  it('normalizes structured FastAPI warnings',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:{code:'FUEL_TYPE_MISMATCH',message:'Choose carefully'}}),{status:409,headers:{'content-type':'application/json'}})));
    const client=createApiClient('http://api.test',async()=>null);
    await expect(client.patch('/fill-ups/1',{})).rejects.toMatchObject({status:409,code:'FUEL_TYPE_MISMATCH',message:'Choose carefully'});
    vi.unstubAllGlobals();
  });
  it.each([
    ['FUEL_TYPE_MISMATCH','fuelTypeMismatch'],
    ['TANK_CAPACITY_WARNING','tankCapacity'],
    ['ARITHMETIC_WARNING','arithmetic'],
  ] as const)('classifies and acknowledges %s only after confirmation',(code,key)=>{
    const initial=emptyEditFillUpAcknowledgements();
    const warning=classifyEditFillUpWarning(new ApiError(409,code,'warning'))!;
    expect(initial[key]).toBe(false);
    expect(acknowledgeEditFillUpWarning(initial,warning)[key]).toBe(true);
  });
  it('recognizes odometer conflicts and supplies a human-readable warning',()=>{
    const warning=classifyEditFillUpWarning(new ApiError(409,'REQUEST_FAILED','Odometer sequence requires explicit confirmation'))!;
    const acknowledged=acknowledgeEditFillUpWarning(emptyEditFillUpAcknowledgements(),warning);
    expect(warning).toBe('ODOMETER_SEQUENCE_CONFLICT');expect(acknowledged.confirmLowerOdometer).toBe(true);expect(editFillUpWarningMessage(warning)).toContain('before or after');
  });
  it('accumulates sequential warnings without approving later warnings',()=>{
    const first=acknowledgeEditFillUpWarning(emptyEditFillUpAcknowledgements(),'FUEL_TYPE_MISMATCH');
    expect(first).toEqual({confirmLowerOdometer:false,fuelTypeMismatch:true,tankCapacity:false,arithmetic:false});
    const second=acknowledgeEditFillUpWarning(first,'TANK_CAPACITY_WARNING');
    expect(second).toEqual({confirmLowerOdometer:false,fuelTypeMismatch:true,tankCapacity:true,arithmetic:false});
  });
  it('does not classify unknown conflicts and creates fresh state for another fill-up',()=>{
    expect(classifyEditFillUpWarning(new ApiError(409,'REQUEST_FAILED','Duplicate fill-up'))).toBeUndefined();
    const accepted=acknowledgeEditFillUpWarning(emptyEditFillUpAcknowledgements(),'ARITHMETIC_WARNING');
    expect(accepted.arithmetic).toBe(true);expect(emptyEditFillUpAcknowledgements().arithmetic).toBe(false);
  });
  it('sends one unacknowledged PATCH and waits for explicit odometer confirmation',async()=>{
    const patch=vi.fn().mockRejectedValueOnce(new ApiError(409,'REQUEST_FAILED','Odometer sequence requires explicit confirmation')).mockResolvedValueOnce({id:'one'});
    const initial=emptyEditFillUpAcknowledgements();let warning;
    try{await patchEditedFillUp(patch,'one',{odometer_km:200},initial)}catch(error){warning=classifyEditFillUpWarning(error)}
    expect(patch).toHaveBeenCalledTimes(1);expect(patch).toHaveBeenLastCalledWith('/fill-ups/one?confirm_lower_odometer=false',expect.objectContaining({acknowledge_fuel_type_mismatch:false,acknowledge_tank_capacity:false,acknowledge_arithmetic_warning:false}));
    const confirmed=acknowledgeEditFillUpWarning(initial,warning!);await patchEditedFillUp(patch,'one',{odometer_km:200},confirmed);
    expect(patch).toHaveBeenCalledTimes(2);expect(patch).toHaveBeenLastCalledWith('/fill-ups/one?confirm_lower_odometer=true',expect.anything());
  });
  it('uses the correct body acknowledgements and preserves them across sequential warnings',async()=>{
    const patch=vi.fn().mockRejectedValueOnce(new ApiError(409,'FUEL_TYPE_MISMATCH','fuel')).mockRejectedValueOnce(new ApiError(409,'TANK_CAPACITY_WARNING','tank')).mockRejectedValueOnce(new ApiError(409,'ARITHMETIC_WARNING','math')).mockResolvedValueOnce({id:'one'});
    let acknowledgements=emptyEditFillUpAcknowledgements();
    for(const expected of ['FUEL_TYPE_MISMATCH','TANK_CAPACITY_WARNING','ARITHMETIC_WARNING'] as const){
      let warning;try{await patchEditedFillUp(patch,'one',{},acknowledgements)}catch(error){warning=classifyEditFillUpWarning(error)}
      expect(warning).toBe(expected);acknowledgements=acknowledgeEditFillUpWarning(acknowledgements,warning!);
    }
    await patchEditedFillUp(patch,'one',{},acknowledgements);
    expect(patch).toHaveBeenLastCalledWith('/fill-ups/one?confirm_lower_odometer=false',expect.objectContaining({acknowledge_fuel_type_mismatch:true,acknowledge_tank_capacity:true,acknowledge_arithmetic_warning:true}));
  });
  it('surfaces unknown conflicts without retrying',async()=>{
    const error=new ApiError(409,'REQUEST_FAILED','Duplicate fill-up');const patch=vi.fn().mockRejectedValue(error);
    await expect(patchEditedFillUp(patch,'one',{},emptyEditFillUpAcknowledgements())).rejects.toBe(error);
    expect(classifyEditFillUpWarning(error)).toBeUndefined();expect(patch).toHaveBeenCalledTimes(1);
  });
  it('invalidates history and metrics after success',async()=>{
    const invalidate=vi.fn().mockResolvedValue(undefined);await invalidateEditedFillUpQueries(invalidate);
    expect(invalidate.mock.calls).toEqual([[{queryKey:['fillups']}],[{queryKey:['car-metrics']}]]);
  });
  it('selecting another fill-up starts with no prior acknowledgement',()=>{
    const previous=acknowledgeEditFillUpWarning(emptyEditFillUpAcknowledgements(),'FUEL_TYPE_MISMATCH');expect(previous.fuelTypeMismatch).toBe(true);
    const nextSelection=emptyEditFillUpAcknowledgements();expect(nextSelection).toEqual({confirmLowerOdometer:false,fuelTypeMismatch:false,tankCapacity:false,arithmetic:false});
  });
});
