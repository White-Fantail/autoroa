import type { Metadata } from "next";
import { SiteFooter, SiteHeader } from "../components/SiteChrome";
import { FuelMapExplorer } from "./FuelMapExplorer";
import { parseFuel } from "./share-links";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
type SearchParams = Promise<Record<string,string|string[]|undefined>>;

async function snapshot(){try{const response=await fetch(`${api}/fuel-stations/snapshot`,{next:{revalidate:300}});if(!response.ok)return null;return await response.json()}catch{return null}}
function first(value:string|string[]|undefined){return Array.isArray(value)?value[0]:value}

export async function generateMetadata({searchParams}:{searchParams:SearchParams}):Promise<Metadata>{
  const params=await searchParams;const fuel=parseFuel(first(params.fuel)??null)??"91";const stationId=first(params.station);const region=first(params.region);const view=first(params.view);
  const data=(stationId||region)?await snapshot():null;const rows:Array<any>=data?.stations??[];
  if(stationId){const station=rows.find(item=>String(item.id)===stationId);if(station){const raw=station.prices?.[{"91":"PETROL_91","95":"PETROL_95","98":"PETROL_98","Diesel":"DIESEL"}[fuel]];const price=Number(raw);const priceText=Number.isFinite(price)?` — $${price.toFixed(3)}/L`:"";const title=`${station.name} ${fuel} fuel price${priceText} | Autoroa`;const description=`See the latest community-reported ${fuel} fuel price at ${station.name}, ${station.city||"New Zealand"}, and compare nearby stations on Autoroa.`;return {title,description,alternates:{canonical:`/fuel-map?station=${encodeURIComponent(stationId)}&fuel=${encodeURIComponent(fuel)}`},openGraph:{title,description,type:"website"},twitter:{card:"summary_large_image",title,description}}}}
  if(region&&view==="cheapest"){const regional=rows.filter(item=>String(item.city??"").localeCompare(region,undefined,{sensitivity:"base"})===0);const key={"91":"PETROL_91","95":"PETROL_95","98":"PETROL_98","Diesel":"DIESEL"}[fuel];const priced=regional.map(item=>({item,price:Number(item.prices?.[key])})).filter(x=>Number.isFinite(x.price)).sort((a,b)=>a.price-b.price);const winner=priced[0];const detail=winner?` — $${winner.price.toFixed(3)}/L at ${winner.item.name}`:"";const title=`Cheapest ${fuel} in ${region}${detail} | Autoroa`;const description=`Compare current community-reported ${fuel} prices in ${region} and find the cheapest fuel on Autoroa.`;return {title,description,alternates:{canonical:`/fuel-map?region=${encodeURIComponent(region)}&fuel=${encodeURIComponent(fuel)}&view=cheapest`},openGraph:{title,description,type:"website"},twitter:{card:"summary_large_image",title,description}}}
  return {title:"Fuel map | Autoroa",description:"Compare community-reported fuel prices around New Zealand."};
}

export default function FuelMapPage(){return <><SiteHeader /><main className="wrap page-shell map-page"><section className="page-heading compact"><p className="eyebrow">Nearby prices</p><h1>Fuel map</h1><p>Choose a fuel type and compare visible pump prices around you.</p></section><FuelMapExplorer /></main><SiteFooter /></>}
