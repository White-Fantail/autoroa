"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useAdminAuth } from "./AdminAuthShell";
import { AdminRow, adminMutationError, formatAdminValue, humanizeField, shortId } from "./admin-utils";

const listBackedSections = new Set(["stations","brands","observations","receipt-failures","unmatched-stations","users","vehicles","fill-ups"]);
const relationTargets: Record<string,string> = { brand_id:"brands", user_id:"users", vehicle_id:"vehicles", station_id:"stations", fill_up_id:"fill-ups", receipt_id:"receipt-failures" };

function listEndpoint(section: string) { return `/admin/${section}`; }
function detailEndpoint(section: string, id: string) {
  if (section === "ocr-queue") return `/ocr-jobs/${encodeURIComponent(id)}`;
  if (section === "station-reports") return `/admin/station-reports/${encodeURIComponent(id)}`;
  return null;
}

function titleFor(row: AdminRow) {
  return String(row.name ?? row.display_name ?? row.nickname ?? row.station_name ?? row.station_text ?? row.reason ?? "Record");
}

export default function AdminDetailPageClient({ section, id }: { section: string; id: string }) {
  const { token, api } = useAdminAuth();
  const router = useRouter();
  const [row, setRow] = useState<AdminRow>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [stationRelated, setStationRelated] = useState<Record<string, unknown> | null>(null);

  async function load() {
    setLoading(true); setError("");
    try {
      const direct = detailEndpoint(section,id);
      if (direct) {
        const response = await fetch(`${api}${direct}`, { headers: { authorization: `Bearer ${token}` } });
        if (!response.ok) throw new Error(adminMutationError(response.status));
        setRow(await response.json());
        return;
      }
      if (!listBackedSections.has(section)) throw new Error("This admin detail route is not supported.");
      const response = await fetch(`${api}${listEndpoint(section)}`, { headers: { authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error(adminMutationError(response.status));
      const rows = await response.json();
      const found = Array.isArray(rows) ? rows.find((item) => String(item.id) === id) : undefined;
      if (!found) throw new Error("The requested record could not be found.");
      setRow(found);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The record could not be loaded.");
    } finally { setLoading(false); }
  }

  useEffect(() => { void load(); }, [api, id, section, token]);

  useEffect(() => {
    if (section !== "stations" || !row) return;
    let active = true;
    void fetch(`${api}/admin/stations/${encodeURIComponent(id)}/related-data`, { headers: { authorization: `Bearer ${token}` } })
      .then((response) => response.ok ? response.json() : null)
      .then((payload) => { if (active) setStationRelated(payload); });
    return () => { active = false; };
  }, [api,id,row,section,token]);

  const entries = useMemo(() => row ? Object.entries(row) : [], [row]);

  async function toggleObservation() {
    if (!row || busy) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`${api}/admin/observations/${encodeURIComponent(id)}?is_active=${!Boolean(row.is_active)}`, { method:"PATCH", headers:{ authorization:`Bearer ${token}` } });
      if (!response.ok) throw new Error(adminMutationError(response.status));
      await load();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Observation update failed."); }
    finally { setBusy(false); }
  }

  async function closeReport() {
    if (!row || busy || row.status === "CLOSED") return;
    if (!window.confirm("Close this station report?")) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`${api}/admin/station-reports/${encodeURIComponent(id)}/close`, { method:"PATCH", headers:{ authorization:`Bearer ${token}` } });
      if (!response.ok) throw new Error(adminMutationError(response.status));
      setRow(await response.json());
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The report could not be closed."); }
    finally { setBusy(false); }
  }

  async function deleteStation() {
    if (!row || busy) return;
    const counts = (stationRelated?.counts ?? {}) as Record<string,number>;
    const total = Object.values(counts).reduce((sum,value) => sum + Number(value || 0),0);
    if (!window.confirm(`Permanently delete “${titleFor(row)}”? ${total} related record${total === 1 ? "" : "s"} may also be removed. This cannot be undone.`)) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`${api}/admin/stations/${encodeURIComponent(id)}?cascade=true`, { method:"DELETE", headers:{ authorization:`Bearer ${token}` } });
      if (!response.ok) throw new Error(adminMutationError(response.status));
      router.replace("/admin/stations");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Station deletion failed."); setBusy(false); }
  }

  if (loading) return <p className="admin-empty" role="status">Loading detail…</p>;
  if (!row) return <><Link className="admin-back" href={`/admin/${section}`}>← Back to {humanizeField(section)}</Link><p className="admin-alert" role="alert">{error || "The record could not be loaded."}</p></>;

  return <><Link className="admin-back" href={`/admin/${section}`}>← Back to {humanizeField(section)}</Link><header className="admin-detail-header"><div><p className="admin-kicker">{humanizeField(section)} detail</p><h1>{titleFor(row)}</h1><p className="admin-detail-id">ID {shortId(id)}</p></div><div className="admin-detail-actions">{section === "observations" && <button type="button" disabled={busy} onClick={() => void toggleObservation()}>{row.is_active ? "Disable" : "Enable"} observation</button>}{section === "station-reports" && row.status !== "CLOSED" && <button className="admin-primary" type="button" disabled={busy} onClick={() => void closeReport()}>{busy ? "Closing…" : "Close issue"}</button>}{section === "stations" && <button type="button" disabled={busy} onClick={() => void deleteStation()}>{busy ? "Deleting…" : "Delete station"}</button>}</div></header>{error && <p className="admin-alert" role="alert">{error}</p>}{section === "stations" && stationRelated && <section className="admin-detail-section"><header><h2>Related data</h2></header><dl className="admin-detail-grid">{Object.entries((stationRelated.counts ?? {}) as Record<string,unknown>).map(([key,value]) => <div key={key}><dt>{humanizeField(key)}</dt><dd>{String(value)}</dd></div>)}</dl></section>}<div className="admin-detail-sections"><section className="admin-detail-section"><header><h2>Record</h2></header><dl className="admin-detail-grid">{entries.map(([field,value]) => {
    const target = relationTargets[field];
    const rendered = target && value ? <Link href={`/admin/${target}/${encodeURIComponent(String(value))}`}>{String(value)}</Link> : formatAdminValue(field,value);
    return <div className={typeof value === "object" && value !== null ? "admin-detail-wide" : ""} key={field}><dt>{humanizeField(field)}</dt><dd className={field === "id" || field.endsWith("_id") ? "admin-mono" : ""}>{rendered}</dd></div>;
  })}</dl></section></div></>;
}
