"use client";

import { createClient } from "@supabase/supabase-js";
import type { CircleMarker, Map as LeafletMap } from "leaflet";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import styles from "./StationMap.module.css";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const NZ_CENTRE: [number, number] = [-41.2, 172.8];

type Station = {
  id: string;
  name: string;
  google_place_id?: string | null;
  address_line: string;
  city: string;
  region?: string | null;
  latitude: number | string;
  longitude: number | string;
  is_active: boolean;
};

type DuplicateGroup = {
  id: string;
  station_count: number;
  minimum_distance_m: number;
  maximum_pair_distance_m: number;
  stations: Station[];
};

type DuplicateResponse = {
  radius_m: number;
  station_count: number;
  group_count: number;
  duplicate_station_count: number;
  groups: DuplicateGroup[];
};

type ViewMode = "duplicates" | "all";

function numberCoordinate(value: number | string): number {
  return typeof value === "number" ? value : Number(value);
}

function StationMapCanvas({ stations }: { stations: Station[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const markersRef = useRef<CircleMarker[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function initialise() {
      if (!containerRef.current || mapRef.current) return;
      const L = await import("leaflet");
      if (cancelled || !containerRef.current) return;
      const map = L.map(containerRef.current, {
        center: NZ_CENTRE,
        zoom: 5,
        preferCanvas: true,
      });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19,
      }).addTo(map);
      leafletRef.current = L;
      mapRef.current = map;
      setReady(true);
    }
    void initialise();
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    if (!ready || !L || !map) return;
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
    const bounds: [number, number][] = [];
    for (const station of stations) {
      const latitude = numberCoordinate(station.latitude);
      const longitude = numberCoordinate(station.longitude);
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) continue;
      const marker = L.circleMarker([latitude, longitude], {
        radius: 6,
        weight: 2,
        fillOpacity: 0.72,
      }).addTo(map);
      marker.bindTooltip(station.name, { direction: "top", opacity: 0.95 });
      marker.bindPopup(
        `<strong>${station.name.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")}</strong><br>${station.address_line.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")}`,
      );
      markersRef.current.push(marker);
      bounds.push([latitude, longitude]);
    }
    if (bounds.length > 1) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 17 });
    else if (bounds.length === 1) map.setView(bounds[0], 16);
    else map.setView(NZ_CENTRE, 5);
  }, [ready, stations]);

  return (
    <div
      ref={containerRef}
      className={styles.map}
      role="region"
      aria-label="Fuel station administration map"
    />
  );
}

export default function AdminStationMapPage() {
  const [authClient] = useState(() =>
    createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost",
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "development-placeholder",
    ),
  );
  const [token, setToken] = useState("");
  const [checkingSession, setCheckingSession] = useState(true);
  const [stations, setStations] = useState<Station[]>([]);
  const [duplicates, setDuplicates] = useState<DuplicateResponse | null>(null);
  const [radius, setRadius] = useState("5");
  const [viewMode, setViewMode] = useState<ViewMode>("duplicates");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [merging, setMerging] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    void authClient.auth.getSession().then(({ data }) => {
      if (!active) return;
      setToken(data.session?.access_token ?? "");
      setCheckingSession(false);
    });
    return () => {
      active = false;
    };
  }, [authClient]);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const headers = { authorization: `Bearer ${token}` };
      const [stationsResponse, duplicateResponse] = await Promise.all([
        fetch(`${api}/admin/stations`, { headers }),
        fetch(`${api}/admin/station-duplicate-groups?radius_m=${radius}`, { headers }),
      ]);
      if (stationsResponse.status === 401 || duplicateResponse.status === 401) {
        await authClient.auth.signOut();
        setToken("");
        throw new Error("Your administrator session has expired.");
      }
      if (stationsResponse.status === 403 || duplicateResponse.status === 403) {
        throw new Error("Administrator access is required.");
      }
      if (!stationsResponse.ok || !duplicateResponse.ok) {
        throw new Error("Station data could not be loaded.");
      }
      setStations(await stationsResponse.json());
      setDuplicates(await duplicateResponse.json());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Station data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [authClient, radius, token]);

  useEffect(() => {
    if (token) void load();
  }, [token, load]);

  const filteredGroups = useMemo(() => {
    const groups = duplicates?.groups ?? [];
    const term = search.trim().toLowerCase();
    if (!term) return groups;
    return groups.filter((group) =>
      group.stations.some((station) =>
        [station.name, station.address_line, station.city, station.google_place_id]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(term)),
      ),
    );
  }, [duplicates, search]);

  const mapStations = useMemo(() => {
    if (viewMode === "all") {
      return stations.filter((station) => station.is_active);
    }
    const ids = new Set(
      filteredGroups.flatMap((group) => group.stations.map((station) => station.id)),
    );
    return stations.filter((station) => ids.has(station.id));
  }, [filteredGroups, stations, viewMode]);

  async function keepStation(group: DuplicateGroup, canonical: Station) {
    const duplicatesToMerge = group.stations.filter((station) => station.id !== canonical.id);
    const confirmed = window.confirm(
      `Keep “${canonical.name}” and merge ${duplicatesToMerge.length} other station record${duplicatesToMerge.length === 1 ? "" : "s"} into it?\n\nThis moves related station records and deletes the duplicate station record${duplicatesToMerge.length === 1 ? "" : "s"}.`,
    );
    if (!confirmed) return;
    setMerging(group.id);
    setError("");
    setNotice("");
    try {
      for (const duplicate of duplicatesToMerge) {
        const response = await fetch(
          `${api}/admin/station-duplicates/${canonical.id}/merge?duplicate_id=${duplicate.id}`,
          {
            method: "POST",
            headers: { authorization: `Bearer ${token}` },
          },
        );
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(
            payload?.error?.message ?? `Could not merge ${duplicate.name}.`,
          );
        }
      }
      setNotice(
        `Kept ${canonical.name} and removed ${duplicatesToMerge.length} duplicate station record${duplicatesToMerge.length === 1 ? "" : "s"}.`,
      );
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Station merge failed.");
      await load();
    } finally {
      setMerging("");
    }
  }

  if (checkingSession) {
    return <main className={styles.page}><p className={styles.status}>Checking administrator access…</p></main>;
  }

  if (!token) {
    return (
      <main className={styles.page}>
        <div className={styles.header}>
          <div>
            <h1>Station map</h1>
            <p>Sign in through Administration before managing station duplicates.</p>
          </div>
        </div>
        <Link className={styles.backLink} href="/admin?section=stations">← Go to administrator sign in</Link>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <Link className={styles.backLink} href="/admin?section=stations">← Back to Stations</Link>
          <h1>Station map & duplicates</h1>
          <p>Review stations that share a location or sit within a small distance of one another.</p>
        </div>
        <button className={styles.refreshButton} disabled={loading} onClick={() => void load()} type="button">
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      {notice && <p className={styles.success} role="status">{notice}</p>}
      {error && <p className={styles.error} role="alert">{error}</p>}

      <section className={styles.controls} aria-label="Station duplicate filters">
        <label>
          Map view
          <select value={viewMode} onChange={(event) => setViewMode(event.target.value as ViewMode)}>
            <option value="duplicates">Duplicate candidates</option>
            <option value="all">All active stations</option>
          </select>
        </label>
        <label>
          Duplicate distance
          <select value={radius} onChange={(event) => setRadius(event.target.value)}>
            <option value="0">Exact coordinates</option>
            <option value="5">Within 5 m</option>
            <option value="10">Within 10 m</option>
            <option value="25">Within 25 m</option>
            <option value="50">Within 50 m</option>
          </select>
        </label>
        <label>
          Find candidate
          <input
            type="search"
            placeholder="Name, address, Place ID"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <div className={styles.summary}>
          {duplicates
            ? `${duplicates.group_count} groups · ${duplicates.duplicate_station_count} station records · ${duplicates.station_count} active stations checked`
            : loading
              ? "Checking stations…"
              : "No duplicate scan loaded"}
        </div>
      </section>

      <div className={styles.layout}>
        <section className={styles.mapCard}>
          <StationMapCanvas stations={mapStations} />
        </section>
        <aside className={styles.listCard} aria-label="Duplicate station groups">
          <div className={styles.listHeader}>
            <h2>Duplicate candidates</h2>
            <p>{filteredGroups.length} groups match the current filters.</p>
          </div>
          {loading && !duplicates ? (
            <p className={styles.status}>Scanning station locations…</p>
          ) : filteredGroups.length === 0 ? (
            <p className={styles.empty}>No duplicate station groups found for this distance.</p>
          ) : (
            filteredGroups.map((group, index) => (
              <section className={styles.group} key={group.id}>
                <div className={styles.groupTitle}>
                  <span>Group {index + 1} · {group.station_count} stations</span>
                  <span>Closest {group.minimum_distance_m.toFixed(1)} m</span>
                </div>
                {group.stations.map((station) => (
                  <div className={styles.station} key={station.id}>
                    <div className={styles.stationName}>
                      <strong>{station.name}</strong>
                      <button
                        className={styles.mergeButton}
                        disabled={Boolean(merging)}
                        onClick={() => void keepStation(group, station)}
                        type="button"
                      >
                        {merging === group.id ? "Merging…" : "Keep this"}
                      </button>
                    </div>
                    <p>{station.address_line}</p>
                    <p className={styles.meta}>{numberCoordinate(station.latitude).toFixed(6)}, {numberCoordinate(station.longitude).toFixed(6)}</p>
                    <p className={styles.meta}>Google: {station.google_place_id || "—"}</p>
                  </div>
                ))}
              </section>
            ))
          )}
        </aside>
      </div>
    </main>
  );
}
