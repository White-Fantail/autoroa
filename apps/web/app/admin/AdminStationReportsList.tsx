"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useAdminAuth } from "./AdminAuthShell";

const reasonLabels: Record<string,string> = {
  CLOSED:"Permanently closed",
  NOT_A_STATION:"Not a fuel station",
  DUPLICATE:"Duplicate station listing",
  WRONG_NAME_OR_BRAND:"Wrong name or brand",
  WRONG_LOCATION:"Wrong address or map location",
  OTHER:"Other issue",
};

type Report = { id:string; station_name:string; station_address?:string|null; reporter_name?:string|null; reason:string; status:"OPEN"|"CLOSED"; created_at:string };
type Filter = "OPEN"|"CLOSED"|"ALL";

function humanize(value:string){return value.replaceAll("_"," ").toLowerCase().replace(/(^|\s)\S/g,(letter)=>letter.toUpperCase())}
function formatDate(value:string){const date=new Date(value);return Number.isNaN(date.getTime())?"—":new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(date)}

export default function AdminStationReportsList(){
  const {token,api}=useAdminAuth();
  const router=useRouter();
  const [reports,setReports]=useState<Report[]>([]);
  const [filter,setFilter]=useState<Filter>("OPEN");
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");

  useEffect(()=>{let active=true;setLoading(true);setError("");void fetch(`${api}/admin/station-reports`,{headers:{authorization:`Bearer ${token}`}}).then(async response=>{if(!response.ok)throw new Error("Station reports could not be loaded.");return response.json()}).then(payload=>{if(active)setReports(Array.isArray(payload)?payload:[])}).catch(caught=>{if(active)setError(caught instanceof Error?caught.message:"Station reports could not be loaded.")}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[api,token]);

  const filtered=useMemo(()=>filter==="ALL"?reports:reports.filter(report=>report.status===filter),[filter,reports]);
  return <><header className="admin-page-header"><div><p className="admin-kicker">Operations</p><h1>Station Reports</h1><p>Review community reports about incorrect, duplicate, closed, or misplaced fuel stations.</p></div><div className="admin-page-actions"><span className="admin-count">{filtered.length} records</span></div></header>{error&&<p className="admin-alert" role="alert">{error}</p>}<div style={{display:"flex",gap:8,marginBottom:18}}>{(["OPEN","CLOSED","ALL"] as const).map(value=><button key={value} type="button" className={filter===value?"admin-primary":""} style={{width:"auto",marginTop:0}} onClick={()=>setFilter(value)}>{value==="ALL"?"All":humanize(value)}</button>)}</div>{loading?<p className="admin-empty">Loading station reports…</p>:filtered.length===0?<p className="admin-empty">No station reports.</p>:<div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Reported</th><th>Station</th><th>Reason</th><th>Status</th><th>Reporter</th><th><span className="sr-only">Open</span></th></tr></thead><tbody>{filtered.map(report=>{const href=`/admin/station-reports/${encodeURIComponent(report.id)}`;return <tr key={report.id} role="link" tabIndex={0} onClick={()=>router.push(href)} onKeyDown={event=>{if(event.key==="Enter"||event.key===" ")router.push(href)}}><td>{formatDate(report.created_at)}</td><td><strong>{report.station_name}</strong>{report.station_address&&<><br/><small>{report.station_address}</small></>}</td><td>{reasonLabels[report.reason]??humanize(report.reason)}</td><td><span className={`admin-status-badge admin-status-${report.status.toLowerCase()}`}>{humanize(report.status)}</span></td><td>{report.reporter_name||"Member"}</td><td className="admin-row-arrow">→</td></tr>})}</tbody></table></div>}</>;
}
