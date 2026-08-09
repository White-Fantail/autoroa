import {describe,expect,it} from 'vitest';
import {fuelEconomyText} from './fuel-economy';

describe('fuelEconomyText',()=>{
  it('formats a calculated economy value',()=>{
    expect(fuelEconomyText({fuel_economy_l_per_100km:'6.923',full_tank:true})).toBe('6.923 L/100km');
  });

  it('explains baseline and partial fill-ups',()=>{
    expect(fuelEconomyText({full_tank:true})).toBe('Economy baseline — calculated at next full tank');
    expect(fuelEconomyText({full_tank:false})).toBe('Added to next full-tank calculation');
  });

  it.each([
    ['MISSED_PREVIOUS_FILL','Previous fill-up missing — economy unavailable'],
    ['MISSED_FILL_CHAIN','Fill-up history incomplete — economy unavailable'],
    ['NON_INCREASING_ODOMETER','Check odometer reading — economy unavailable'],
    ['DISTANCE_TOO_SHORT','Not enough distance to calculate economy'],
    ['ECONOMY_OUTLIER','Unusual result — check fill-up details'],
  ])('explains the %s warning',(economy_warning,message)=>{
    expect(fuelEconomyText({full_tank:true,economy_warning})).toBe(message);
  });

  it('uses a safe fallback for unknown warnings',()=>{
    expect(fuelEconomyText({full_tank:true,economy_warning:'NEW_WARNING'})).toBe('Fuel economy unavailable');
  });
});
