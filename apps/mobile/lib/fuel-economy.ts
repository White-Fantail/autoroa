import type {FillUp} from '../../../packages/types/src';

type EconomyFields=Pick<FillUp,'fuel_economy_l_per_100km'|'full_tank'|'economy_warning'>;

const warningMessages:Record<string,string>={
  MISSED_PREVIOUS_FILL:'Previous fill-up missing — economy unavailable',
  MISSED_FILL_CHAIN:'Fill-up history incomplete — economy unavailable',
  NON_INCREASING_ODOMETER:'Check odometer reading — economy unavailable',
  DISTANCE_TOO_SHORT:'Not enough distance to calculate economy',
  ECONOMY_OUTLIER:'Unusual result — check fill-up details',
};

export function fuelEconomyText(fill:EconomyFields){
  if(fill.fuel_economy_l_per_100km)return `${fill.fuel_economy_l_per_100km} L/100km`;
  if(fill.economy_warning)return warningMessages[fill.economy_warning]??'Fuel economy unavailable';
  return fill.full_tank
    ? 'Economy baseline — calculated at next full tank'
    : 'Added to next full-tank calculation';
}
