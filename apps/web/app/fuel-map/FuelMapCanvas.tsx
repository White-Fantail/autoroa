"use client";

import type { Map as LeafletMap, Marker } from "leaflet";
import React, { useEffect, useRef, useState } from "react";
import type { Fuel, Station } from "./FuelMapExplorer";

type Coordinates = { latitude: number; longitude: number };

type Props = {
  fuel: Fuel;
  stations: Station[];
  selectedStation: Station;
  userLocation: Coordinates | null;
  onSelect: (stationName: string) => void;
};

const CHRISTCHURCH_CENTRE: [number, number] = [-43.5321, 172.6362];

export function FuelMapCanvas({
  fuel,
  stations,
  selectedStation,
  userLocation,
  onSelect,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const stationMarkersRef = useRef<Marker[]>([]);
  const userMarkerRef = useRef<Marker | null>(null);
  const onSelectRef = useRef(onSelect);
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    let cancelled = false;

    async function initialiseMap() {
      if (!containerRef.current || mapRef.current) return;
      const L = await import("leaflet");
      if (cancelled || !containerRef.current) return;

      const map = L.map(containerRef.current, {
        center: CHRISTCHURCH_CENTRE,
        zoom: 13,
        zoomControl: true,
      });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19,
      }).addTo(map);
      leafletRef.current = L;
      mapRef.current = map;
      setMapReady(true);
    }

    void initialiseMap();
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const L = leafletRef.current;
    if (!L || !mapRef.current) return;

    stationMarkersRef.current.forEach((marker) => marker.remove());
    stationMarkersRef.current = stations.map((station) => {
      const isSelected = station.id === selectedStation.id;
      const price = station.prices[fuel]!.toFixed(3);
      const icon = L.divIcon({
        className: "fuel-marker-shell",
        html: `<span class="fuel-marker${isSelected ? " selected" : ""}">$${price}</span>`,
        iconSize: [72, 40],
        iconAnchor: [36, 40],
      });
      const marker = L.marker([station.latitude, station.longitude], {
        icon,
        title: `${station.name}, $${price} per litre`,
        alt: `${station.name}, $${price} per litre`,
        riseOnHover: true,
      }).addTo(mapRef.current!);
      marker.on("click", () => onSelectRef.current(station.id));
      return marker;
    });
  }, [fuel, mapReady, selectedStation.id, stations]);

  useEffect(() => {
    mapRef.current?.flyTo(
      [selectedStation.latitude, selectedStation.longitude],
      Math.max(mapRef.current.getZoom(), 14),
      { duration: 0.6 },
    );
  }, [mapReady, selectedStation]);

  useEffect(() => {
    const L = leafletRef.current;
    if (!userLocation || !L || !mapRef.current) return;

    userMarkerRef.current?.remove();
    const icon = L.divIcon({
      className: "user-location-shell",
      html: '<span class="user-location-dot"></span>',
      iconSize: [24, 24],
      iconAnchor: [12, 12],
    });
    userMarkerRef.current = L.marker(
      [userLocation.latitude, userLocation.longitude],
      { icon, title: "Your location", alt: "Your location", zIndexOffset: 1000 },
    ).addTo(mapRef.current);
    mapRef.current.flyTo(
      [userLocation.latitude, userLocation.longitude],
      14,
      { duration: 0.8 },
    );
  }, [mapReady, userLocation]);

  return (
    <div className="map-canvas-wrap">
      <div
        ref={containerRef}
        className="map-canvas"
        role="region"
        aria-label={`Interactive map showing ${fuel} fuel prices`}
      />
      <div className="map-detail" aria-live="polite">
        <strong>{selectedStation.name}</strong>
        <span>
          ${selectedStation.prices[fuel]!.toFixed(3)}/L ·{" "}
          {selectedStation.distance.toFixed(1)} km
        </span>
      </div>
    </div>
  );
}
