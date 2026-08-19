"use client";

import React, { useEffect, useMemo, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabaseBrowser } from "../../lib/supabase";
import { FuelMapCanvas } from "./FuelMapCanvas";

export type Fuel = "91" | "95" | "98" | "Diesel";
export type Station = {
  id: string;
  name: string;
  address: string;
  distance: number;
  latitude: number;
  longitude: number;
  prices: Partial<Record<Fuel, number>>;
  observedAt: Partial<Record<Fuel, string>>;
};

const fuelTypes: Fuel[] = ["91", "95", "98", "Diesel"];
const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const fuelKeys: Record<string, Fuel> = { PETROL_91: "91", PETROL_95: "95", PETROL_98: "98", DIESEL: "Diesel" };
const defaultLocation = { latitude: -43.5321, longitude: 172.6362 };
function distanceKm(a:{latitude:number;longitude:number},b:{latitude:number;longitude:number}) { const radians=(value:number)=>value*Math.PI/180;const dLat=radians(b.latitude-a.latitude);const dLon=radians(b.longitude-a.longitude);const value=Math.sin(dLat/2)**2+Math.cos(radians(a.latitude))*Math.cos(radians(b.latitude))*Math.sin(dLon/2)**2;return 6371*2*Math.atan2(Math.sqrt(value),Math.sqrt(1-value)); }
function freshness(value:string) { const minutes=Math.max(0,Math.round((Date.now()-new Date(value).getTime())/60000));return minutes<60?`${minutes} min ago`:minutes<1440?`${Math.round(minutes/60)} hr ago`:`${Math.round(minutes/1440)} days ago`; }

export function FuelMapExplorer() {
  const [fuel, setFuel] = useState<Fuel>("91");
  const [sort, setSort] = useState<"distance" | "price">("price");
  const [stations, setStations] = useState<Station[]>([]);
  const [selected, setSelected] = useState("");
  const [dataState, setDataState] = useState<"loading"|"ready"|"error">("loading");
  const [locationState, setLocationState] = useState<"idle" | "locating" | "found" | "denied">("idle");
  const [userLocation, setUserLocation] = useState<{ latitude: number; longitude: number } | null>(null);
  const [pricePhotoState,setPricePhotoState]=useState<"idle"|"uploading"|"success"|"error">("idle");
  const [pricePhotoMessage,setPricePhotoMessage]=useState("");
  const [session,setSession]=useState<Session|null>(null);
  const [authReady,setAuthReady]=useState(false);
  const [authMessage,setAuthMessage]=useState("");

  useEffect(()=>{let active=true;void fetch(`${api}/fuel-stations/snapshot`).then(async response=>{if(!response.ok)throw new Error();const body=await response.json();const rows:Station[]=(body.stations??[]).flatMap((item:any)=>{const latitude=Number(item.latitude),longitude=Number(item.longitude);if(!Number.isFinite(latitude)||!Number.isFinite(longitude))return [];const prices:Partial<Record<Fuel,number>>={};const observedAt:Partial<Record<Fuel,string>>={};for(const [key,value] of Object.entries(item.prices??{})){const fuelKey=fuelKeys[key];const price=Number(value);if(fuelKey&&Number.isFinite(price))prices[fuelKey]=price}for(const [key,value] of Object.entries(item.observed_at??{})){const fuelKey=fuelKeys[key];if(fuelKey&&typeof value==="string")observedAt[fuelKey]=value}return [{id:String(item.id),name:String(item.name),address:String(item.address),latitude,longitude,distance:0,prices,observedAt}]});if(active){setStations(rows);setSelected(rows[0]?.id??"");setDataState("ready")}}).catch(()=>{if(active)setDataState("error")});return()=>{active=false}},[]);

  useEffect(()=>{
    let active=true;
    try {
      const client=supabaseBrowser();
      void client.auth.getSession().then(({data,error})=>{if(!active)return;if(error)setAuthMessage("Sign-in is temporarily unavailable.");setSession(data.session);setAuthReady(true)});
      const {data:{subscription}}=client.auth.onAuthStateChange((_event,nextSession)=>{if(active){setSession(nextSession);setAuthReady(true);setAuthMessage("")}});
      return()=>{active=false;subscription.unsubscribe()};
    } catch {
      setAuthReady(true);setAuthMessage("Sign-in is not configured for this environment.");
      return()=>{active=false};
    }
  },[]);

  const origin=userLocation??defaultLocation;
  const visible = useMemo(() => stations.map(station=>({...station,distance:distanceKm(origin,station)})).filter(station=>station.distance<=15).sort((a, b) => {
    if (sort === "distance") return a.distance - b.distance;
    const aPrice=a.prices[fuel],bPrice=b.prices[fuel];
    if(aPrice!==undefined&&bPrice!==undefined)return aPrice-bPrice;
    if(aPrice!==undefined)return -1;
    if(bPrice!==undefined)return 1;
    return a.distance-b.distance;
  }), [fuel, origin, sort, stations]);
  const selectedStation = visible.find((station) => station.id === selected) ?? visible[0];
  const pricedCount=visible.filter(station=>station.prices[fuel]!==undefined).length;

  useEffect(()=>{setPricePhotoState("idle");setPricePhotoMessage("")},[selectedStation?.id]);

  function locate() {
    if (!navigator.geolocation) return setLocationState("denied");
    setLocationState("locating");
    navigator.geolocation.getCurrentPosition(({ coords }) => { setUserLocation({ latitude: coords.latitude, longitude: coords.longitude }); setLocationState("found"); }, () => setLocationState("denied"), { timeout: 8000 });
  }

  async function signIn(provider:"google"|"apple"|"facebook") {
    setAuthMessage("");
    try {
      const client=supabaseBrowser();
      const {error}=await client.auth.signInWithOAuth({provider,options:{redirectTo:window.location.href}});
      if(error)throw error;
    } catch(error) {
      setAuthMessage(error instanceof Error?error.message:"Sign-in could not be started.");
    }
  }

  async function submitPricePhoto(file:File) {
    if(!selectedStation||!session)return;
    setPricePhotoState("uploading");setPricePhotoMessage("");
    try {
      const body=new FormData();body.append("photo",file);
      const response=await fetch(`${api}/fuel-stations/${encodeURIComponent(selectedStation.id)}/user-price-board-submissions`,{method:"POST",headers:{Authorization:`Bearer ${session.access_token}`},body});
      const result=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(result?.error?.message||"The price-board photo could not be submitted.");
      setPricePhotoState("success");
      const matchNote=result.station_mismatch?" We detected that the photo may belong to another nearby station, so it will be reviewed before prices are applied.":"";
      setPricePhotoMessage((result.message||"Thanks! Your photo was submitted for verification.")+matchNote);
    } catch(error) {
      setPricePhotoState("error");setPricePhotoMessage(error instanceof Error?error.message:"The price-board photo could not be submitted.");
    }
  }

  return (
    <section className="map-explorer">
      <div className="map-toolbar">
        <div>
          <span className="control-label">Fuel type</span>
          <div className="segments" role="radiogroup" aria-label="Fuel type">
            {fuelTypes.map((item) => <button key={item} type="button" role="radio" aria-checked={fuel === item} className={fuel === item ? "active" : ""} onClick={() => setFuel(item)}>{item}</button>)}
          </div>
        </div>
        <button className="locate-button" type="button" onClick={locate} disabled={locationState === "locating"}>⌖ {locationState === "locating" ? "Locating…" : locationState === "found" ? "Location found" : "Use my location"}</button>
      </div>
      {locationState === "denied" && <p className="location-message" role="status">Location is unavailable. Showing the Christchurch preview area instead.</p>}
      {locationState === "found" && <p className="location-message" role="status">Your current location is marked on the map.</p>}
      {dataState === "loading" && <p className="location-message" role="status">Loading fuel stations…</p>}
      {dataState === "error" && <p className="location-message" role="alert">Fuel stations could not be loaded. Please try again later.</p>}
      {dataState === "ready" && visible.length === 0 && <p className="location-message" role="status">No fuel stations are available within 15 km.</p>}
      {selectedStation && <div className="map-layout">
        <FuelMapCanvas fuel={fuel} stations={visible} selectedStation={selectedStation} userLocation={userLocation} onSelect={setSelected} />
        <aside className="station-list">
          <div className="station-list-head">
            <div><h2>Nearby {fuel}</h2><span>{visible.length} stations · {pricedCount} with current prices</span></div>
            <select aria-label="Sort stations" value={sort} onChange={(event) => setSort(event.target.value as "distance" | "price")}><option value="price">Cheapest</option><option value="distance">Nearest</option></select>
          </div>
          <div className="location-message" aria-live="polite" style={{ display: "grid", gap: 10, paddingBlock: 12 }}>
            <div>
              <strong>{selectedStation.prices[fuel]===undefined?`No current ${fuel} price at ${selectedStation.name} yet.`:`Price looks wrong at ${selectedStation.name}?`}</strong>{" "}
              Take a photo of the station price board. We’ll verify its location and prices in the background before applying updates.
            </div>
            {!authReady ? <span>Checking sign-in…</span> : session ?
              <label className="locate-button" style={{ display: "inline-flex", alignItems: "center", width: "fit-content" }}>
                {pricePhotoState==="uploading"?"Uploading…":selectedStation.prices[fuel]===undefined?"Add price with a photo":"Update prices with a photo"}
                <input hidden type="file" accept="image/jpeg,image/png,image/webp" disabled={pricePhotoState==="uploading"} onChange={event=>{const file=event.target.files?.[0];if(file)void submitPricePhoto(file);event.target.value=""}} />
              </label>
            : <div style={{display:"grid",gap:8}}>
              <strong>Sign in to contribute price photos and earn points.</strong>
              <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
                <button className="locate-button" type="button" onClick={()=>void signIn("google")}>Continue with Google</button>
                <button className="locate-button" type="button" onClick={()=>void signIn("apple")}>Continue with Apple</button>
                <button className="locate-button" type="button" onClick={()=>void signIn("facebook")}>Continue with Facebook</button>
              </div>
            </div>}
            {authMessage&&<p style={{margin:0}} role="alert">{authMessage}</p>}
            {pricePhotoMessage&&<p style={{ margin: 0 }} role={pricePhotoState==="error"?"alert":"status"}>{pricePhotoMessage}</p>}
          </div>
          {visible.map((station, index) => { const stationPrice=station.prices[fuel]; return <button type="button" className={`station-row ${selectedStation.id === station.id ? "selected" : ""}`} onClick={() => setSelected(station.id)} key={station.id}>
            <span className="rank">{index + 1}</span>
            <span className="station-meta"><strong>{station.name}</strong><small>{station.address} · {station.distance.toFixed(1)} km</small><small className="fresh">{station.observedAt[fuel] ? `Updated ${freshness(station.observedAt[fuel]!)}` : `No current ${fuel} price — add one`}</small></span>
            <span className="station-price">{stationPrice===undefined?<><strong>—</strong><small>No price</small></>:<><>{`$${stationPrice.toFixed(3)}`}</><small>/L</small></>}</span>
          </button>})}
          <p className="disclaimer">Prices are community-reported. Always confirm the pump price before filling up.</p>
        </aside>
      </div>}
    </section>
  );
}
