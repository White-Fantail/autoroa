"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { createClient } from "@supabase/supabase-js";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

type Mode = "list" | "detail" | "station";
type Report = {
  id: string;
  station_id: string;
  station_name: string;
  station_address?: string | null;
  reporter_name?: string | null;
  reporter_id: string;
  reason: string;
  details?: string | null;
  status: "OPEN" | "CLOSED";
  created_at: string;
  updated_at: string;
  station?: Record<string, unknown> | null;
};

const reasonLabels: Record<string, string> = {
  CLOSED: "Permanently closed",
  NOT_A_STATION: "Not a fuel station",
  DUPLICATE: "Duplicate station listing",
  WRONG_NAME_OR_BRAND: "Wrong name or brand",
  WRONG_LOCATION: "Wrong address or map location",
  OTHER: "Other issue",
};

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function humanize(value: string) {
  return value.replaceAll("_", " ").toLowerCase().replace(/(^|\s)\S/g, (letter) => letter.toUpperCase());
}

export default function StationReportsClient({ mode }: { mode: Mode }) {
  const params = useParams<{ id?: string }>();
  const router = useRouter();
  const reportId = typeof params?.id === "string" ? params.id : "";
  const [token, setToken] = useState("");
  const [access, setAccess] = useState<"checking" | "ready" | "signed-out" | "forbidden" | "error">("checking");
  const [reports, setReports] = useState<Report[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [statusFilter, setStatusFilter] = useState<"OPEN" | "CLOSED" | "ALL">("OPEN");
  const [loading, setLoading] = useState(true);
  const [closing, setClosing] = useState(false);
  const [error, setError] = useState("");
  const [authClient] = useState(() => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost",
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "development-placeholder",
  ));

  useEffect(() => {
    let active = true;
    void authClient.auth.getSession().then(({ data, error: sessionError }) => {
      if (!active) return;
      if (sessionError) {
        setAccess("error");
        setError("We could not verify your administrator session.");
        return;
      }
      const accessToken = data.session?.access_token ?? "";
      if (!accessToken) {
        setAccess("signed-out");
        setLoading(false);
        return;
      }
      setToken(accessToken);
    });
    return () => { active = false; };
  }, [authClient]);

  useEffect(() => {
    if (!token) return;
    let active = true;
    setLoading(true);
    setError("");
    const endpoint = mode === "list"
      ? `${api}/admin/station-reports`
      : `${api}/admin/station-reports/${encodeURIComponent(reportId)}`;
    void fetch(endpoint, { headers: { authorization: `Bearer ${token}` } })
      .then(async (response) => {
        if (response.status === 401) {
          await authClient.auth.signOut();
          throw new Error("SIGNED_OUT");
        }
        if (response.status === 403) throw new Error("FORBIDDEN");
        if (!response.ok) throw new Error("The station report data could not be loaded.");
        return response.json();
      })
      .then((payload) => {
        if (!active) return;
        setAccess("ready");
        if (mode === "list") setReports(Array.isArray(payload) ? payload : []);
        else setReport(payload as Report);
      })
      .catch((caught) => {
        if (!active) return;
        if (caught instanceof Error && caught.message === "SIGNED_OUT") setAccess("signed-out");
        else if (caught instanceof Error && caught.message === "FORBIDDEN") setAccess("forbidden");
        else {
          setAccess("error");
          setError(caught instanceof Error ? caught.message : "The station report data could not be loaded.");
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [authClient, mode, reportId, token]);

  const filteredReports = useMemo(() => {
    if (statusFilter === "ALL") return reports;
    return reports.filter((item) => item.status === statusFilter);
  }, [reports, statusFilter]);

  async function closeIssue() {
    if (!report || report.status === "CLOSED" || closing) return;
    if (!window.confirm("Close this station report? The report will remain available in Closed reports.")) return;
    setClosing(true);
    setError("");
    try {
      const response = await fetch(`${api}/admin/station-reports/${encodeURIComponent(report.id)}/close`, {
        method: "PATCH",
        headers: { authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("The report could not be closed.");
      setReport(await response.json());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The report could not be closed.");
    } finally {
      setClosing(false);
    }
  }

  if (access === "checking" || loading) {
    return <main className="admin-login-shell"><section className="admin-login-card"><p className="admin-kicker">Administration</p><h1>Loading station reports…</h1></section></main>;
  }
  if (access === "signed-out") {
    return <main className="admin-login-shell"><section className="admin-login-card"><p className="admin-kicker">Administration</p><h1>Sign in required</h1><p>Use the Admin sign-in before reviewing station reports.</p><Link className="admin-primary" href="/admin">Go to Admin sign in</Link></section></main>;
  }
  if (access === "forbidden") {
    return <main className="admin-login-shell"><section className="admin-login-card"><p className="admin-kicker">Administration</p><h1>Access denied</h1><p>Your account does not have administrator permission.</p><Link href="/admin">Back to Admin</Link></section></main>;
  }
  if (access === "error") {
    return <main className="admin-login-shell"><section className="admin-login-card"><p className="admin-kicker">Administration</p><h1>Unable to load reports</h1><p className="admin-alert" role="alert">{error}</p><button onClick={() => window.location.reload()}>Try again</button></section></main>;
  }

  if (mode === "list") {
    return <main className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand admin-brand-light">autoroa</div>
        <nav aria-label="Admin sections">
          <button onClick={() => router.push("/admin")}>Dashboard</button>
          <button className="active">Station reports</button>
          <button onClick={() => router.push("/admin?section=stations")}>Stations</button>
          <button onClick={() => router.push("/admin/stations/map")}>Map & duplicates</button>
        </nav>
        <button className="admin-signout" onClick={() => void authClient.auth.signOut().then(() => router.push("/admin"))}>Sign out</button>
      </aside>
      <section className="admin-content">
        <header className="admin-page-header">
          <div><p className="admin-kicker">Operations</p><h1>Station reports</h1><p>Review community reports about incorrect, duplicate, closed, or misplaced fuel stations.</p></div>
          <span className="admin-count">{filteredReports.length} records</span>
        </header>
        <div style={{display:"flex",gap:8,marginBottom:18,flexWrap:"wrap"}}>
          {(["OPEN","CLOSED","ALL"] as const).map((value) => <button key={value} className={statusFilter===value?"admin-primary":""} onClick={() => setStatusFilter(value)}>{value === "ALL" ? "All" : humanize(value)}</button>)}
        </div>
        {filteredReports.length === 0 ? <p className="admin-empty">No {statusFilter === "ALL" ? "station" : statusFilter.toLowerCase()} reports.</p> : <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Reported</th><th>Station</th><th>Reason</th><th>Status</th><th>Reporter</th><th><span className="sr-only">Open</span></th></tr></thead><tbody>{filteredReports.map((item) => <tr key={item.id} tabIndex={0} role="link" onClick={() => router.push(`/admin/station-reports/${item.id}`)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") router.push(`/admin/station-reports/${item.id}`); }}><td>{formatDate(item.created_at)}</td><td><strong>{item.station_name}</strong>{item.station_address && <><br/><small>{item.station_address}</small></>}</td><td>{reasonLabels[item.reason] ?? humanize(item.reason)}</td><td><span className={`admin-status-badge admin-status-${item.status.toLowerCase()}`}>{humanize(item.status)}</span></td><td>{item.reporter_name || "Member"}</td><td className="admin-row-arrow">→</td></tr>)}</tbody></table></div>}
      </section>
    </main>;
  }

  if (!report) return null;

  if (mode === "station") {
    const station = report.station;
    return <main className="admin-shell">
      <aside className="admin-sidebar"><div className="admin-brand admin-brand-light">autoroa</div><nav><button onClick={() => router.push("/admin")}>Dashboard</button><button onClick={() => router.push("/admin/station-reports")}>Station reports</button><button className="active">Station detail</button></nav></aside>
      <section className="admin-content">
        <Link className="admin-back" href={`/admin/station-reports/${report.id}`}>← Back to report</Link>
        <header className="admin-detail-header"><div><p className="admin-kicker">Station detail</p><h1>{report.station_name}</h1><p>{report.station_address}</p></div></header>
        {!station ? <p className="admin-alert">This station record no longer exists.</p> : <div className="admin-detail-sections"><section className="admin-detail-section"><header><h2>Station information</h2><p>Current station record linked to this report.</p></header><dl className="admin-detail-grid">{Object.entries(station).filter(([key]) => !["created_at","updated_at"].includes(key)).map(([key,value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{value == null || value === "" ? "—" : String(value)}</dd></div>)}</dl></section></div>}
      </section>
    </main>;
  }

  return <main className="admin-shell">
    <aside className="admin-sidebar">
      <div className="admin-brand admin-brand-light">autoroa</div>
      <nav><button onClick={() => router.push("/admin")}>Dashboard</button><button className="active" onClick={() => router.push("/admin/station-reports")}>Station reports</button><button onClick={() => router.push("/admin?section=stations")}>Stations</button></nav>
    </aside>
    <section className="admin-content">
      <Link className="admin-back" href="/admin/station-reports">← Back to station reports</Link>
      <header className="admin-detail-header">
        <div><p className="admin-kicker">Station report detail</p><h1>{reasonLabels[report.reason] ?? humanize(report.reason)}</h1><p>{report.station_name}</p></div>
        <div className="admin-detail-actions"><span className={`admin-status-badge admin-status-${report.status.toLowerCase()}`}>{humanize(report.status)}</span><Link href={`/admin/station-reports/${report.id}/station`}>Open station</Link>{report.status === "OPEN" && <button className="admin-primary" disabled={closing} onClick={() => void closeIssue()}>{closing ? "Closing…" : "Close issue"}</button>}</div>
      </header>
      {error && <p className="admin-alert" role="alert">{error}</p>}
      <div className="admin-detail-sections">
        <section className="admin-detail-section"><header><h2>Report</h2></header><dl className="admin-detail-grid"><div><dt>Reason</dt><dd>{reasonLabels[report.reason] ?? humanize(report.reason)}</dd></div><div><dt>Status</dt><dd>{humanize(report.status)}</dd></div><div><dt>Reported</dt><dd>{formatDate(report.created_at)}</dd></div><div><dt>Last updated</dt><dd>{formatDate(report.updated_at)}</dd></div><div><dt>Reporter</dt><dd>{report.reporter_name || "Member"}</dd></div><div><dt>Report ID</dt><dd className="admin-mono">{report.id}</dd></div></dl></section>
        <section className="admin-detail-section"><header><h2>Additional information</h2></header><p style={{whiteSpace:"pre-wrap"}}>{report.details || "No additional information was provided."}</p></section>
        <section className="admin-detail-section"><header><h2>Station</h2></header><dl className="admin-detail-grid"><div><dt>Name</dt><dd>{report.station_name}</dd></div><div><dt>Address</dt><dd>{report.station_address || "—"}</dd></div><div><dt>Station ID</dt><dd className="admin-mono">{report.station_id}</dd></div></dl><div className="admin-form-actions"><Link href={`/admin/station-reports/${report.id}/station`}>Open station</Link></div></section>
      </div>
    </section>
  </main>;
}
