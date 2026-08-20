"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useAdminAuth } from "./AdminAuthShell";
import { AdminRow, filterAdminRows, formatAdminValue, humanizeField, listFields } from "./admin-utils";

const supportedSections = new Set(["dashboard","ocr-queue","station-reports","stations","brands","observations","receipt-failures","unmatched-stations","users","vehicles","fill-ups"]);

const descriptions: Record<string, string> = {
  dashboard: "A current overview of activity and items needing attention.",
  "ocr-queue": "Upload price-board photos and review extracted prices before applying them.",
  "station-reports": "Review community reports about incorrect, duplicate, closed, or misplaced fuel stations.",
  stations: "Fuel stations available throughout the product.",
  brands: "Fuel station brands used to identify station networks.",
  observations: "Submitted fuel prices and their moderation status.",
  "receipt-failures": "Receipts that could not be processed successfully.",
  "unmatched-stations": "Receipts whose station still needs to be matched.",
  users: "Customer profiles registered with Autoroa.",
  vehicles: "Vehicles added by customers.",
  "fill-ups": "Recent fuel purchases recorded by customers.",
};

const fieldOverrides: Record<string, string[]> = {
  observations: ["station_name","fuel_type","pump_price_per_litre","observed_at","source","verification_level","is_anomaly","is_active"],
  "station-reports": ["created_at","station_name","reason","status","reporter_name"],
  "ocr-queue": ["created_at","submission_source","station_id","status","confidence","applied_at"],
};

function title(section: string) {
  if (section === "ocr-queue") return "OCR Queue";
  if (section === "station-reports") return "Station Reports";
  return humanizeField(section);
}

function endpoint(section: string) {
  if (section === "ocr-queue") return "/ocr-jobs?kind=PRICE_BOARD&limit=50";
  return `/admin/${section}`;
}

export default function AdminRoutePageClient({ section }: { section: string }) {
  const { token, api } = useAdminAuth();
  const router = useRouter();
  const [data, setData] = useState<AdminRow[] | AdminRow>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!supportedSections.has(section)) return;
    let active = true;
    setLoading(true);
    setError("");
    void fetch(`${api}${endpoint(section)}`, { headers: { authorization: `Bearer ${token}` } })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Request failed (HTTP ${response.status}).`);
        return response.json();
      })
      .then((payload) => { if (active) setData(payload); })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Request failed."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api, section, token]);

  const rows = useMemo(() => Array.isArray(data) ? filterAdminRows(data, filter) : [], [data, filter]);
  const fields = useMemo(() => {
    const configured = fieldOverrides[section];
    if (configured) return configured.filter((field) => field in (rows[0] ?? {}));
    return listFields(rows[0] ?? {});
  }, [rows, section]);

  if (!supportedSections.has(section)) return <div><h1>Admin page not found</h1><p>The requested admin section does not exist.</p></div>;

  if (section === "dashboard") {
    return <><header className="admin-page-header"><div><p className="admin-kicker">Operations</p><h1>Dashboard</h1><p>{descriptions.dashboard}</p></div></header>{error && <p className="admin-alert" role="alert">{error}</p>}{loading ? <p className="admin-empty">Loading…</p> : data && !Array.isArray(data) ? <div className="admin-stats">{Object.entries(data).map(([label,value]) => <article key={label}><span>{humanizeField(label)}</span><strong>{String(value)}</strong></article>)}</div> : null}</>;
  }

  return <><header className="admin-page-header"><div><p className="admin-kicker">Operations</p><h1>{title(section)}</h1><p>{descriptions[section]}</p></div><div className="admin-page-actions">{Array.isArray(data) && <span className="admin-count">{rows.length} records</span>}</div></header>{error && <p className="admin-alert" role="alert">{error}</p>}<div className="admin-list-card"><div className="admin-list-toolbar"><input aria-label="Filter records" placeholder="Search all fields…" type="search" value={filter} onChange={(event) => setFilter(event.target.value)} /></div>{loading ? <p className="admin-empty">Loading…</p> : rows.length === 0 ? <p className="admin-empty">No records found.</p> : <div className="admin-table-wrap"><table className="admin-table"><thead><tr>{fields.map((field) => <th key={field}>{humanizeField(field)}</th>)}<th><span className="sr-only">Open</span></th></tr></thead><tbody>{rows.map((row,index) => {
    const id = String(row.id ?? index);
    const href = `/admin/${section}/${encodeURIComponent(id)}`;
    return <tr key={id} role="link" tabIndex={0} onClick={() => router.push(href)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") router.push(href); }}>{fields.map((field) => <td key={field}>{formatAdminValue(field,row[field])}</td>)}<td className="admin-row-arrow"><Link aria-label={`Open ${id}`} href={href} onClick={(event) => event.stopPropagation()}>→</Link></td></tr>;
  })}</tbody></table></div>}</div></>;
}
