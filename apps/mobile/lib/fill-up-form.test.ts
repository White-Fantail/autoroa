import {describe,expect,it} from 'vitest';
import {calculatedTotal,formatLocalDateTime,latestOdometer,localDateTimeToIso} from './fill-up-form';

describe('fill-up review helpers',()=>{
  it('calculates a discounted total rounded to cents',()=>expect(calculatedTotal('40.125','2.499','1.50')).toBe('98.77'));
  it('rounds exact half cents up without binary floating-point drift',()=>expect(calculatedTotal('1','2.675','0')).toBe('2.68'));
  it('rounds values immediately below a half cent down',()=>expect(calculatedTotal('1','2.6749','0')).toBe('2.67'));
  it('applies discounts before cent rounding',()=>expect(calculatedTotal('1','2.685','0.01')).toBe('2.68'));
  it('does not calculate until valid operands are present',()=>expect(calculatedTotal('','2.5','0')).toBe(''));
  it('round trips an instant through the system local time zone',()=>{const iso='2026-01-02T03:04:00.000Z';expect(localDateTimeToIso(formatLocalDateTime(iso))).toBe(iso)});
  it('uses the chronologically latest odometer',()=>expect(latestOdometer([{occurred_at:'2026-02-01T00:00:00Z',odometer_km:20},{occurred_at:'2026-01-01T00:00:00Z',odometer_km:10}])).toBe(20));
});
