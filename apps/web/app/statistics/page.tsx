"use client";

import React, { useEffect, useState } from "react";
import { SiteFooter, SiteHeader } from "../components/SiteChrome";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const fuelNames:Record<string,string>={PETROL_91:"Regular 91",PETROL_95:"Premium 95",PETROL_98:"Premium 98",DIESEL:"Diesel",OTHER:"Other"};
const tones=["green","gold","blue","ink"];
type Snapshot={averages:{fuel_type:string;average_price:number;station_count:number}[];stations:{id:string;name:string;city:string;prices:Record<string,number>}[];priced_station_count:number;reports_week:number;generated_at:string};

export default function StatisticsPage() {
  const [snapshot,setSnapshot]=useState<Snapshot>();const [error,setError]=useState(false);
  useEffect(()=>{let active=true;void fetch(`${api}/fuel-prices/snapshot`).then(async response=>{if(!response.ok)throw new Error();const body=await response.json();if(active)setSnapshot(body)}).catch(()=>{if(active)setError(true)});return()=>{active=false}},[]);
  const cheapest=(snapshot?.stations??[]).filter(station=>Number.isFinite(Number(station.prices?.PETROL_91))).sort((a,b)=>Number(a.prices.PETROL_91)-Number(b.prices.PETROL_91)).slice(0,5);
  return (
    <>
      <SiteHeader />
      <main className="wrap page-shell">
        <section className="page-heading">
          <p className="eyebrow">Community fuel snapshot</p>
          <h1>New Zealand fuel statistics</h1>
          <p>
            See the shape of today&apos;s market at a glance, then find the best
            price for your own journey.
          </p>
          <span className="data-note">Current community-reported data · Updated {snapshot ? new Date(snapshot.generated_at).toLocaleString("en-NZ") : "when loaded"}</span>
        </section>
        {!snapshot && !error && <p role="status" className="location-message">Loading fuel statistics…</p>}
        {error && <p role="alert" className="location-message">Fuel statistics could not be loaded. Please try again later.</p>}
        {snapshot && snapshot.averages.length === 0 && <p role="status" className="location-message">No current fuel-price statistics are available.</p>}
        {snapshot && snapshot.averages.length > 0 && <>
        <section className="average-grid" aria-label="Average fuel prices">
          {snapshot.averages.map((item,index) => (
            <article className="average-card" key={item.fuel_type}>
              <div className={`fuel-strip ${tones[index%tones.length]}`}>{fuelNames[item.fuel_type]??item.fuel_type}</div>
              <div className="average-value">
                <span>$</span>
                {Number(item.average_price).toFixed(3)}
                <small>/L</small>
              </div>
              <p>{item.station_count} current station {item.station_count===1?"price":"prices"}</p>
            </article>
          ))}
        </section>
        <section className="stats-layout">
          <article className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Best value</p>
                <h2>Lowest Regular 91 prices</h2>
              </div>
              <a href="/fuel-map">Open map →</a>
            </div>
            <div className="price-table" role="table">
              <div className="table-row table-head" role="row">
                <span>Station</span>
                <span>Area</span>
                <span>Price/L</span>
              </div>
              {cheapest.map((row) => (
                <div className="table-row" role="row" key={row.id}>
                  <strong>{row.name}</strong>
                  <span>{row.city}</span>
                  <strong>${Number(row.prices.PETROL_91).toFixed(3)}</strong>
                </div>
              ))}
              {cheapest.length===0&&<p className="muted">No current Regular 91 prices are available.</p>}
            </div>
          </article>
          <aside className="panel insight-panel">
            <p className="eyebrow">Market pulse</p>
            <h2>Live coverage</h2>
            <p className="insight-number">{snapshot.priced_station_count}</p>
            <p className="muted">
              Stations currently represented by reports from the last seven days.
            </p>
            <div className="watch-grid">
              <div>
                <strong>{snapshot.priced_station_count.toLocaleString()}</strong>
                <span>Stations watched</span>
              </div>
              <div>
                <strong>{snapshot.reports_week.toLocaleString()}</strong>
                <span>Reports this week</span>
              </div>
            </div>
          </aside>
        </section>
        </>}
        <section className="map-cta">
          <div>
            <p className="eyebrow">Make it local</p>
            <h2>National averages are only the start.</h2>
            <p>
              Use the fuel map to compare prices around your current location by
              fuel type.
            </p>
          </div>
          <a className="button button-light" href="/fuel-map">
            Find fuel near me
          </a>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
