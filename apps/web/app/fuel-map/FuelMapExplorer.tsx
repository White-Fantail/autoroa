"use client";

import React, { useMemo, useState } from "react";

type Fuel = "91" | "95" | "98" | "Diesel";
type Station = {
  name: string;
  address: string;
  distance: number;
  x: number;
  y: number;
  prices: Record<Fuel, number>;
  fresh: string;
};

const fuelTypes: Fuel[] = ["91", "95", "98", "Diesel"];
const stations: Station[] = [
  {
    name: "NPD Moorhouse",
    address: "Moorhouse Avenue",
    distance: 1.2,
    x: 48,
    y: 48,
    prices: { "91": 2.239, "95": 2.399, "98": 2.489, Diesel: 1.739 },
    fresh: "18 min ago",
  },
  {
    name: "Waitomo Fitzgerald",
    address: "Fitzgerald Avenue",
    distance: 0.8,
    x: 70,
    y: 25,
    prices: { "91": 2.259, "95": 2.419, "98": 2.519, Diesel: 1.759 },
    fresh: "42 min ago",
  },
  {
    name: "Gull Stanmore",
    address: "Stanmore Road",
    distance: 3.1,
    x: 82,
    y: 58,
    prices: { "91": 2.279, "95": 2.439, "98": 2.529, Diesel: 1.779 },
    fresh: "1 hr ago",
  },
  {
    name: "Pak'nSave Fuel Hornby",
    address: "Main South Road",
    distance: 6.8,
    x: 22,
    y: 70,
    prices: { "91": 2.289, "95": 2.449, "98": 2.539, Diesel: 1.789 },
    fresh: "2 hrs ago",
  },
  {
    name: "Mobil Papanui",
    address: "Papanui Road",
    distance: 5.3,
    x: 40,
    y: 16,
    prices: { "91": 2.309, "95": 2.469, "98": 2.559, Diesel: 1.809 },
    fresh: "3 hrs ago",
  },
];

export function FuelMapExplorer() {
  const [fuel, setFuel] = useState<Fuel>("91");
  const [sort, setSort] = useState<"distance" | "price">("price");
  const [selected, setSelected] = useState(stations[0].name);
  const [locationState, setLocationState] = useState<
    "idle" | "locating" | "found" | "denied"
  >("idle");
  const visible = useMemo(
    () =>
      [...stations].sort((a, b) =>
        sort === "price"
          ? a.prices[fuel] - b.prices[fuel]
          : a.distance - b.distance,
      ),
    [fuel, sort],
  );
  const selectedStation =
    stations.find((station) => station.name === selected) ?? stations[0];

  function locate() {
    if (!navigator.geolocation) return setLocationState("denied");
    setLocationState("locating");
    navigator.geolocation.getCurrentPosition(
      () => setLocationState("found"),
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
          Location access confirmed. Live location-based results are not yet
          connected, so this remains a Christchurch preview.
        </p>
      )}
      <div className="map-layout">
        <div
          className="map-canvas"
          aria-label={`Map preview showing ${fuel} fuel prices`}
        >
          <div className="road road-one" />
          <div className="road road-two" />
          <div className="road road-three" />
          <span className="map-label label-one">CITY CENTRE</span>
          <span className="map-label label-two">HAGLEY PARK</span>
          {stations.map((station) => (
            <button
              type="button"
              key={station.name}
              className={`price-pin ${selected === station.name ? "selected" : ""}`}
              style={{ left: `${station.x}%`, top: `${station.y}%` }}
              aria-label={`${station.name}, $${station.prices[fuel].toFixed(3)} per litre`}
              onClick={() => setSelected(station.name)}
            >
              <span>${station.prices[fuel].toFixed(3)}</span>
            </button>
          ))}
          <div className="map-detail">
            <strong>{selectedStation.name}</strong>
            <span>
              ${selectedStation.prices[fuel].toFixed(3)}/L ·{" "}
              {selectedStation.distance.toFixed(1)} km
            </span>
          </div>
          <span className="preview-badge">Illustrative map</span>
        </div>
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
              className={`station-row ${selected === station.name ? "selected" : ""}`}
              onClick={() => setSelected(station.name)}
              key={station.name}
            >
              <span className="rank">{index + 1}</span>
              <span className="station-meta">
                <strong>{station.name}</strong>
                <small>
                  {station.address} · {station.distance.toFixed(1)} km
                </small>
                <small className="fresh">Updated {station.fresh}</small>
              </span>
              <span className="station-price">
                ${station.prices[fuel].toFixed(3)}
                <small>/L</small>
              </span>
            </button>
          ))}
          <p className="disclaimer">
            Preview prices are illustrative. Always confirm the pump price
            before filling up.
          </p>
        </aside>
      </div>
    </section>
  );
}
