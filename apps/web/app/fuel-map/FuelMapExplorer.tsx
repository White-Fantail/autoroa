"use client";

import React, { useEffect, useMemo, useState } from "react";
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
  const [locationState, setLocationState] = useState<
    "idle" | "locating" | "found" | "denied"
  >("idle");
  const [userLocation, setUserLocation] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);
  useEffect(()=>{let active=true;void fetch(`${api}/fuel-prices/snapshot`).then(async response=>{if(!response.ok)throw new Error();const body=await response.json();const rows:Station[]=(body.stations??[]).flatMap((item:any)=>{const latitude=Number(item.latitude),longitude=Number(item.longitude);if(!Number.isFinite(latitude)||!Number.isFinite(longitude))return [];const prices:Partial<Record<Fuel,number>>={};const observedAt:Partial<Record<Fuel,string>>={};for(const [key,value] of Object.entries(item.prices??{})){const fuelKey=fuelKeys[key];const price=Number(value);if(fuelKey&&Number.isFinite(price))prices[fuelKey]=price}for(const [key,value] of Object.entries(item.observed_at??{})){const fuelKey=fuelKeys[key];if(fuelKey&&typeof value==="string")observedAt[fuelKey]=value}return [{id:String(item.id),name:String(item.name),address:String(item.address),latitude,longitude,distance:0,prices,observedAt}]});if(active){setStations(rows);setSelected(rows[0]?.id??"");setDataState("ready")}}).catch(()=>{if(active)setDataState("error")});return()=>{active=false}},[]);
  const origin=userLocation??defaultLocation;
  const visible = useMemo(
    () =>
      stations.filter(station=>station.prices[fuel]!==undefined).map(station=>({...station,distance:distanceKm(origin,station)})).filter(station=>station.distance<=15).sort((a, b) =>
        sort === "price"
          ? a.prices[fuel]! - b.prices[fuel]!
          : a.distance - b.distance,
      ),
    [fuel, origin, sort, stations],
  );
  const selectedStation =
    visible.find((station) => station.id === selected) ?? visible[0];

  function locate() {
    if (!navigator.geolocation) return setLocationState("denied");
    setLocationState("locating");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setUserLocation({
          latitude: coords.latitude,
          longitude: coords.longitude,
        });
        setLocationState("found");
      },
      () => setLocationState("denied"),
      { timeout: 8000 },
    );
  }

  return (
    <section className="map-explorer">
      <div className="map-toolbar">
        <div>
          <span className="control-label">Fuel type</span>
          <div className="segments" role="radiogroup" aria-label="Fuel type">
            {fuelTypes.map((item) => (
              <button
                key={item}
                type="button"
                role="radio"
                aria-checked={fuel === item}
                className={fuel === item ? "active" : ""}
                onClick={() => setFuel(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
        <button
          className="locate-button"
          type="button"
          onClick={locate}
          disabled={locationState === "locating"}
        >
          ⌖{" "}
          {locationState === "locating"
            ? "Locating…"
            : locationState === "found"
              ? "Location found"
              : "Use my location"}
        </button>
      </div>
      {locationState === "denied" && (
        <p className="location-message" role="status">
          Location is unavailable. Showing the Christchurch preview area
          instead.
        </p>
      )}
      {locationState === "found" && (
        <p className="location-message" role="status">
          Your current location is marked on the map.
        </p>
      )}
      {dataState === "loading" && <p className="location-message" role="status">Loading current fuel prices…</p>}
      {dataState === "error" && <p className="location-message" role="alert">Current fuel prices could not be loaded. Please try again later.</p>}
      {dataState === "ready" && visible.length === 0 && <p className="location-message" role="status">No current {fuel} prices are available.</p>}
      {selectedStation &&
      <div className="map-layout">
        <FuelMapCanvas
          fuel={fuel}
          stations={visible}
          selectedStation={selectedStation}
          userLocation={userLocation}
          onSelect={setSelected}
        />
        <aside className="station-list">
          <div className="station-list-head">
            <div>
              <h2>Nearby {fuel}</h2>
              <span>{visible.length} prices · within 15 km</span>
            </div>
            <select
              aria-label="Sort stations"
              value={sort}
              onChange={(event) =>
                setSort(event.target.value as "distance" | "price")
              }
            >
              <option value="price">Cheapest</option>
              <option value="distance">Nearest</option>
            </select>
          </div>
          {visible.map((station, index) => (
            <button
              type="button"
              className={`station-row ${selectedStation.id === station.id ? "selected" : ""}`}
              onClick={() => setSelected(station.id)}
              key={station.id}
            >
              <span className="rank">{index + 1}</span>
              <span className="station-meta">
                <strong>{station.name}</strong>
                <small>
                  {station.address} · {station.distance.toFixed(1)} km
                </small>
                <small className="fresh">Updated {station.observedAt[fuel] ? freshness(station.observedAt[fuel]!) : "unknown"}</small>
              </span>
              <span className="station-price">
                ${station.prices[fuel]!.toFixed(3)}
                <small>/L</small>
              </span>
            </button>
          ))}
          <p className="disclaimer">
            Prices are community-reported. Always confirm the pump price
            before filling up.
          </p>
        </aside>
      </div>}
    </section>
  );
}
