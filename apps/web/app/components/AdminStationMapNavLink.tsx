"use client";

import { createClient } from "@supabase/supabase-js";
import type { CircleMarker, Map as LeafletMap } from "leaflet";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const NZ_CENTRE: [number, number] = [-41.2, 172.8];

type Station = {
  id: string;
  name: string;
  google_place_id?: string | null;
  address_line: string;
  city: string;
  latitude: number | string;
  longitude: number | string;
  is_active: boolean;
};

type DuplicateGroup = {
  id: string;
  station_count: number;
  minimum_distance_m: number;
  stations: Station[];
};

type DuplicateResponse = {
  station_count: number;
  group_count: number;
  duplicate_station_count: number;
  groups: DuplicateGroup[];
};

type StationRelatedData = {
  counts: Record<string, number>;
};

type Report = {
  id: string;
  station_id: string;
  station_name: string;
  station_address?: string | null;
  reporter_name?: string | null;
  reason: string;
  details?: string | null;
  status: "OPEN" | "CLOSED";
  created_at: string;
  updated_at: string;
  station?: Record<string, unknown> | null;
};

type StationView = "list" | "map";
type ReportFilter = "OPEN" | "CLOSED" | "ALL";

const reasonLabels: Record<string, string> = {
  CLOSED: "Permanently closed",
  NOT_A_STATION: "Not a fuel station",
  DUPLICATE: "Duplicate station listing",
  WRONG_NAME_OR_BRAND: "Wrong name or brand",
  WRONG_LOCATION: "Wrong address or map location",
  OTHER: "Other issue",
};

function currentSection() {
  return new URLSearchParams(window.location.search).get("section") ?? "dashboard";
}

function humanize(value: string) {
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/(^|\s)\S/g, (letter) => letter.toUpperCase());
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function coordinate(value: number | string) {
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
    void import("leaflet").then((L) => {
      if (cancelled || !containerRef.current || mapRef.current) return;
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
    });
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
      const lat = coordinate(station.latitude);
      const lng = coordinate(station.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
      const marker = L.circleMarker([lat, lng], {
        radius: 6,
        weight: 2,
        fillOpacity: 0.72,
      }).addTo(map);
      marker.bindTooltip(station.name, { direction: "top" });
      markersRef.current.push(marker);
      bounds.push([lat, lng]);
    }
    if (bounds.length > 1) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 17 });
    else if (bounds.length === 1) map.setView(bounds[0], 16);
    else map.setView(NZ_CENTRE, 5);
  }, [ready, stations]);

  return (
    <div
      ref={containerRef}
      role="region"
      aria-label="Fuel station administration map"
      style={{ height: "min(68vh, 720px)", minHeight: 420, borderRadius: 14, overflow: "hidden" }}
    />
  );
}

function StationMapWorkspace({ token }: { token: string }) {
  const [stations, setStations] = useState<Station[]>([]);
  const [duplicates, setDuplicates] = useState<DuplicateResponse | null>(null);
  const [radius, setRadius] = useState("5");
  const [mode, setMode] = useState<"duplicates" | "all">("duplicates");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const headers = { authorization: `Bearer ${token}` };
      const [stationResponse, duplicateResponse] = await Promise.all([
        fetch(`${api}/admin/stations`, { headers }),
        fetch(`${api}/admin/station-duplicate-groups?radius_m=${radius}`, { headers }),
      ]);
      if (!stationResponse.ok || !duplicateResponse.ok) {
        throw new Error("Station map data could not be loaded.");
      }
      setStations(await stationResponse.json());
      setDuplicates(await duplicateResponse.json());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Station map data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [radius, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const groups = useMemo(() => {
    const term = search.trim().toLowerCase();
    const rows = duplicates?.groups ?? [];
    if (!term) return rows;
    return rows.filter((group) =>
      group.stations.some((station) =>
        [station.name, station.address_line, station.city, station.google_place_id]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(term)),
      ),
    );
  }, [duplicates, search]);

  const mapStations = useMemo(() => {
    if (mode === "all") return stations.filter((station) => station.is_active);
    const ids = new Set(groups.flatMap((group) => group.stations.map((station) => station.id)));
    return stations.filter((station) => ids.has(station.id));
  }, [groups, mode, stations]);

  async function keepStation(group: DuplicateGroup, canonical: Station) {
    const others = group.stations.filter((station) => station.id !== canonical.id);
    if (!window.confirm(`Keep “${canonical.name}” and merge ${others.length} duplicate record${others.length === 1 ? "" : "s"} into it?`)) return;
    setBusy(group.id);
    setError("");
    try {
      for (const duplicate of others) {
        const response = await fetch(
          `${api}/admin/station-duplicates/${canonical.id}/merge?duplicate_id=${duplicate.id}`,
          { method: "POST", headers: { authorization: `Bearer ${token}` } },
        );
        if (!response.ok) throw new Error(`Could not merge ${duplicate.name}.`);
      }
      setNotice(`Kept ${canonical.name} and removed ${others.length} duplicate record${others.length === 1 ? "" : "s"}.`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Station merge failed.");
    } finally {
      setBusy("");
    }
  }

  async function deleteStation(station: Station) {
    setBusy(station.id);
    setError("");
    try {
      const headers = { authorization: `Bearer ${token}` };
      const relatedResponse = await fetch(`${api}/admin/stations/${station.id}/related-data`, { headers });
      if (!relatedResponse.ok) throw new Error("Related station data could not be checked.");
      const related = (await relatedResponse.json()) as StationRelatedData;
      const relatedCount = Object.values(related.counts).reduce((sum, count) => sum + Number(count || 0), 0);
      if (!window.confirm(`Permanently delete “${station.name}”? ${relatedCount} related record${relatedCount === 1 ? "" : "s"} may also be removed. This cannot be undone.`)) return;
      const response = await fetch(`${api}/admin/stations/${station.id}?cascade=true`, {
        method: "DELETE",
        headers,
      });
      if (!response.ok) throw new Error("Station deletion failed.");
      setNotice(`Deleted ${station.name}.`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Station deletion failed.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="admin-detail-sections" style={{ marginTop: 20 }}>
      {notice && <p className="admin-success" role="status">{notice}</p>}
      {error && <p className="admin-alert" role="alert">{error}</p>}
      <section className="admin-detail-section">
        <header>
          <div>
            <h2>Station map</h2>
            <p>Review all stations or focus on likely duplicate locations.</p>
          </div>
          <button className="admin-primary" type="button" disabled={loading} onClick={() => void load()}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </header>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end", marginBottom: 16 }}>
          <label>Map view<select value={mode} onChange={(event) => setMode(event.target.value as "duplicates" | "all")}><option value="duplicates">Duplicate candidates</option><option value="all">All active stations</option></select></label>
          <label>Duplicate distance<select value={radius} onChange={(event) => setRadius(event.target.value)}><option value="0">Exact coordinates</option><option value="5">Within 5 m</option><option value="10">Within 10 m</option><option value="25">Within 25 m</option><option value="50">Within 50 m</option></select></label>
          <label style={{ flex: "1 1 240px" }}>Find candidate<input type="search" placeholder="Name, address, Place ID" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
          <span className="admin-count">{duplicates ? `${duplicates.group_count} groups · ${duplicates.duplicate_station_count} records` : "Scanning…"}</span>
        </div>
        <StationMapCanvas stations={mapStations} />
      </section>
      <section className="admin-detail-section">
        <header><div><h2>Duplicate candidates</h2><p>{groups.length} groups match the current filters.</p></div></header>
        {groups.length === 0 ? <p className="admin-empty">No duplicate station groups found.</p> : groups.map((group, index) => (
          <div key={group.id} style={{ borderTop: "1px solid var(--border)", padding: "16px 0" }}>
            <strong>Group {index + 1} · {group.station_count} stations · closest {group.minimum_distance_m.toFixed(1)} m</strong>
            <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
              {group.stations.map((station) => (
                <div key={station.id} style={{ display: "flex", justifyContent: "space-between", gap: 14, alignItems: "center" }}>
                  <div><strong>{station.name}</strong><div className="admin-muted">{station.address_line}</div></div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button type="button" disabled={Boolean(busy)} onClick={() => void keepStation(group, station)}>{busy === group.id ? "Merging…" : "Keep this"}</button>
                    <button type="button" disabled={Boolean(busy)} onClick={() => void deleteStation(station)}>{busy === station.id ? "Checking…" : "Delete"}</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}

function StationReportsWorkspace({ token }: { token: string }) {
  const [reports, setReports] = useState<Report[]>([]);
  const [selected, setSelected] = useState<Report | null>(null);
  const [filter, setFilter] = useState<ReportFilter>("OPEN");
  const [loading, setLoading] = useState(true);
  const [closing, setClosing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${api}/admin/station-reports`, {
        headers: { authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("Station reports could not be loaded.");
      setReports(await response.json());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Station reports could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function openReport(id: string) {
    setError("");
    try {
      const response = await fetch(`${api}/admin/station-reports/${encodeURIComponent(id)}`, {
        headers: { authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("The station report could not be loaded.");
      setSelected(await response.json());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The station report could not be loaded.");
    }
  }

  async function closeIssue() {
    if (!selected || selected.status === "CLOSED" || closing) return;
    if (!window.confirm("Close this station report?")) return;
    setClosing(true);
    setError("");
    try {
      const response = await fetch(`${api}/admin/station-reports/${encodeURIComponent(selected.id)}/close`, {
        method: "PATCH",
        headers: { authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("The report could not be closed.");
      const updated = await response.json();
      setSelected(updated);
      setReports((rows) => rows.map((row) => row.id === updated.id ? updated : row));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The report could not be closed.");
    } finally {
      setClosing(false);
    }
  }

  if (selected) {
    return (
      <>
        <button className="admin-back" type="button" onClick={() => setSelected(null)}>← Back to station reports</button>
        <header className="admin-detail-header">
          <div><p className="admin-kicker">Station report detail</p><h1>{reasonLabels[selected.reason] ?? humanize(selected.reason)}</h1><p>{selected.station_name}</p></div>
          <div className="admin-detail-actions"><span className={`admin-status-badge admin-status-${selected.status.toLowerCase()}`}>{humanize(selected.status)}</span>{selected.status === "OPEN" && <button className="admin-primary" type="button" disabled={closing} onClick={() => void closeIssue()}>{closing ? "Closing…" : "Close issue"}</button>}</div>
        </header>
        {error && <p className="admin-alert" role="alert">{error}</p>}
        <div className="admin-detail-sections">
          <section className="admin-detail-section"><header><h2>Report</h2></header><dl className="admin-detail-grid"><div><dt>Reason</dt><dd>{reasonLabels[selected.reason] ?? humanize(selected.reason)}</dd></div><div><dt>Status</dt><dd>{humanize(selected.status)}</dd></div><div><dt>Reported</dt><dd>{formatDate(selected.created_at)}</dd></div><div><dt>Last updated</dt><dd>{formatDate(selected.updated_at)}</dd></div><div><dt>Reporter</dt><dd>{selected.reporter_name || "Member"}</dd></div><div><dt>Report ID</dt><dd className="admin-mono">{selected.id}</dd></div></dl></section>
          <section className="admin-detail-section"><header><h2>Additional information</h2></header><p style={{ whiteSpace: "pre-wrap" }}>{selected.details || "No additional information was provided."}</p></section>
          <section className="admin-detail-section"><header><h2>Station</h2><p>Current station record linked to this report.</p></header><dl className="admin-detail-grid"><div><dt>Name</dt><dd>{selected.station_name}</dd></div><div><dt>Address</dt><dd>{selected.station_address || "—"}</dd></div><div><dt>Station ID</dt><dd className="admin-mono">{selected.station_id}</dd></div>{selected.station && Object.entries(selected.station).filter(([key]) => !["id", "name", "address_line", "created_at", "updated_at"].includes(key)).slice(0, 8).map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{value == null || value === "" ? "—" : String(value)}</dd></div>)}</dl></section>
        </div>
      </>
    );
  }

  const filtered = filter === "ALL" ? reports : reports.filter((report) => report.status === filter);
  return (
    <>
      <header className="admin-page-header">
        <div><p className="admin-kicker">Operations</p><h1>Station Reports</h1><p>Review community reports about incorrect, duplicate, closed, or misplaced fuel stations.</p></div>
        <div className="admin-page-actions"><span className="admin-count">{filtered.length} records</span></div>
      </header>
      {error && <p className="admin-alert" role="alert">{error}</p>}
      <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
        {(["OPEN", "CLOSED", "ALL"] as const).map((value) => <button key={value} type="button" className={filter === value ? "admin-primary" : ""} onClick={() => setFilter(value)}>{value === "ALL" ? "All" : humanize(value)}</button>)}
      </div>
      {loading ? <p className="admin-empty">Loading station reports…</p> : filtered.length === 0 ? <p className="admin-empty">No station reports.</p> : (
        <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Reported</th><th>Station</th><th>Reason</th><th>Status</th><th>Reporter</th><th><span className="sr-only">Open</span></th></tr></thead><tbody>{filtered.map((report) => <tr key={report.id} role="button" tabIndex={0} onClick={() => void openReport(report.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") void openReport(report.id); }}><td>{formatDate(report.created_at)}</td><td><strong>{report.station_name}</strong>{report.station_address && <><br /><small>{report.station_address}</small></>}</td><td>{reasonLabels[report.reason] ?? humanize(report.reason)}</td><td><span className={`admin-status-badge admin-status-${report.status.toLowerCase()}`}>{humanize(report.status)}</span></td><td>{report.reporter_name || "Member"}</td><td className="admin-row-arrow">→</td></tr>)}</tbody></table></div>
      )}
    </>
  );
}

export default function AdminStationMapNavLink() {
  const [token, setToken] = useState("");
  const [stationView, setStationView] = useState<StationView>("list");
  const [reportsActive, setReportsActive] = useState(false);
  const [mapHost, setMapHost] = useState<HTMLElement | null>(null);
  const [reportsHost, setReportsHost] = useState<HTMLElement | null>(null);
  const toggleRef = useRef<HTMLDivElement | null>(null);
  const reportsButtonRef = useRef<HTMLButtonElement | null>(null);
  const hiddenChildrenRef = useRef<Array<{ element: HTMLElement; display: string }>>([]);
  const nativeContentRef = useRef<HTMLElement | null>(null);
  const [authClient] = useState(() => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost",
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "development-placeholder",
  ));

  useEffect(() => {
    void authClient.auth.getSession().then(({ data }) => setToken(data.session?.access_token ?? ""));
    const { data } = authClient.auth.onAuthStateChange((_, session) => setToken(session?.access_token ?? ""));
    return () => data.subscription.unsubscribe();
  }, [authClient]);

  const restoreStationList = useCallback(() => {
    hiddenChildrenRef.current.forEach(({ element, display }) => { element.style.display = display; });
    hiddenChildrenRef.current = [];
    mapHost?.remove();
    setMapHost(null);
  }, [mapHost]);

  const showStationMap = useCallback(() => {
    const content = document.querySelector<HTMLElement>(".admin-shell > .admin-content");
    if (!content) return;
    restoreStationList();
    const header = content.querySelector<HTMLElement>(".admin-page-header");
    hiddenChildrenRef.current = Array.from(content.children)
      .filter((element): element is HTMLElement => element instanceof HTMLElement && element !== header)
      .map((element) => ({ element, display: element.style.display }));
    hiddenChildrenRef.current.forEach(({ element }) => { element.style.display = "none"; });
    const host = document.createElement("div");
    host.dataset.adminStationMapHost = "true";
    content.append(host);
    setMapHost(host);
  }, [restoreStationList]);

  useEffect(() => {
    if (stationView === "map") showStationMap();
    else restoreStationList();
  }, [restoreStationList, showStationMap, stationView]);

  useEffect(() => {
    if (reportsActive) {
      const shell = document.querySelector<HTMLElement>(".admin-shell");
      const nativeContent = shell?.querySelector<HTMLElement>(":scope > .admin-content");
      if (!shell || !nativeContent) return;
      nativeContentRef.current = nativeContent;
      nativeContent.style.display = "none";
      const host = document.createElement("section");
      host.className = "admin-content";
      host.dataset.adminStationReportsHost = "true";
      shell.append(host);
      setReportsHost(host);
      return () => {
        host.remove();
        nativeContent.style.display = "";
        setReportsHost(null);
      };
    }
    nativeContentRef.current?.style.removeProperty("display");
    nativeContentRef.current = null;
  }, [reportsActive]);

  useEffect(() => {
    const sync = () => {
      const shell = document.querySelector<HTMLElement>(".admin-shell");
      const navigation = shell?.querySelector<HTMLElement>(".admin-sidebar nav");
      if (!shell || !navigation) return;

      if (!reportsButtonRef.current?.isConnected) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Station Reports";
        button.dataset.adminStationReportsLink = "true";
        button.addEventListener("click", () => {
          const params = new URLSearchParams(window.location.search);
          params.set("section", "station-reports");
          window.history.pushState({ section: "station-reports" }, "", `${window.location.pathname}?${params.toString()}`);
          setStationView("list");
          setReportsActive(true);
        });
        const ocrButton = Array.from(navigation.querySelectorAll<HTMLButtonElement>("button")).find((item) => item.textContent?.trim() === "OCR Queue");
        if (ocrButton) ocrButton.insertAdjacentElement("afterend", button);
        else navigation.append(button);
        reportsButtonRef.current = button;
      }

      const section = currentSection();
      const stationPage = section === "stations" && !reportsActive;
      if (!stationPage) {
        toggleRef.current?.remove();
        toggleRef.current = null;
        if (stationView !== "list") setStationView("list");
      } else if (!toggleRef.current?.isConnected) {
        const actions = document.querySelector<HTMLElement>(".admin-page-actions");
        if (actions) {
          const toggle = document.createElement("div");
          toggle.setAttribute("role", "group");
          toggle.setAttribute("aria-label", "Station view");
          toggle.style.display = "flex";
          toggle.style.gap = "6px";
          const list = document.createElement("button");
          const map = document.createElement("button");
          list.type = "button";
          map.type = "button";
          list.textContent = "List";
          map.textContent = "Map";
          const paint = (view: StationView) => {
            list.className = view === "list" ? "admin-primary" : "";
            map.className = view === "map" ? "admin-primary" : "";
          };
          paint(stationView);
          list.addEventListener("click", () => { setStationView("list"); paint("list"); });
          map.addEventListener("click", () => { setStationView("map"); paint("map"); });
          toggle.append(list, map);
          actions.prepend(toggle);
          toggleRef.current = toggle;
        }
      }

      const reportButton = reportsButtonRef.current;
      if (reportButton) reportButton.classList.toggle("active", reportsActive);
      if (reportsActive) {
        navigation.querySelectorAll("button").forEach((button) => {
          if (button !== reportButton) button.classList.remove("active");
        });
      } else if (section !== "station-reports") {
        setReportsActive(false);
      }
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    const onPopState = () => {
      if (currentSection() !== "station-reports") setReportsActive(false);
      sync();
    };
    window.addEventListener("popstate", onPopState);
    return () => {
      observer.disconnect();
      window.removeEventListener("popstate", onPopState);
      toggleRef.current?.remove();
      reportsButtonRef.current?.remove();
      restoreStationList();
    };
  }, [reportsActive, restoreStationList, stationView]);

  return (
    <>
      {mapHost && stationView === "map" && token && createPortal(<StationMapWorkspace token={token} />, mapHost)}
      {reportsHost && reportsActive && token && createPortal(<StationReportsWorkspace token={token} />, reportsHost)}
    </>
  );
}
