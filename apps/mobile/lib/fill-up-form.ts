export const fuelTypes = ['PETROL_91','PETROL_95','PETROL_98','DIESEL','OTHER'] as const;

function pad(value:number){return String(value).padStart(2,'0')}

export function formatLocalDateTime(value:string){
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return value;
  return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function localDateTimeToIso(value:string){
  const match=value.trim().match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})$/);
  if(!match)return undefined;
  const [,year,month,day,hour,minute]=match;
  const date=new Date(Number(year),Number(month)-1,Number(day),Number(hour),Number(minute));
  if(date.getFullYear()!==Number(year)||date.getMonth()!==Number(month)-1||date.getDate()!==Number(day)||date.getHours()!==Number(hour)||date.getMinutes()!==Number(minute))return undefined;
  return date.toISOString();
}

export function calculatedTotal(litres:string,price:string,discount:string){
  function decimal(value:string){
    const match=value.trim().match(/^(\d+)(?:\.(\d*))?$/);if(!match)return undefined;
    const places=match[2]?.length??0;return {integer:BigInt(`${match[1]}${match[2]??''}`),scale:10n**BigInt(places)};
  }
  const quantity=decimal(litres);const unitPrice=decimal(price);const discountAmount=decimal(discount||'0');
  if(!quantity||quantity.integer<=0n||!unitPrice||unitPrice.integer<=0n||!discountAmount)return '';
  const grossInteger=quantity.integer*unitPrice.integer;const grossScale=quantity.scale*unitPrice.scale;
  const commonScale=grossScale*discountAmount.scale;
  const amountInteger=grossInteger*discountAmount.scale-discountAmount.integer*grossScale;
  if(amountInteger<=0n)return '0.00';
  const centNumerator=amountInteger*100n;let cents=centNumerator/commonScale;
  if((centNumerator%commonScale)*2n>=commonScale)cents+=1n;
  return `${cents/100n}.${String(cents%100n).padStart(2,'0')}`;
}

export function latestOdometer(history:Array<{occurred_at:string;odometer_km:number}>){
  return history.reduce<{occurred_at:string;odometer_km:number}|undefined>((latest,item)=>!latest||new Date(item.occurred_at).getTime()>new Date(latest.occurred_at).getTime()?item:latest,undefined)?.odometer_km;
}
