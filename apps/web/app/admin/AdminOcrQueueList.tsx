"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useAdminAuth } from "./AdminAuthShell";
import { adminMutationError, humanizeField, shortId } from "./admin-utils";

type Job = Record<string,any> & { id:string; status:string; created_at:string; station_id?:string|null; user_id?:string|null; confidence?:number|null };

function formatDate(value?:string|null){if(!value)return "—";const date=new Date(value);return Number.isNaN(date.getTime())?"—":new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(date)}
function formatUploader(job:Job,names:Record<string,string>){const source=String(job.submission_source??job.result_json?.submission_source??"").toUpperCase();const role=source==="FUEL_MAP_USER"?"User":source==="ADMIN"?"Admin":job.user_id?"Account":"User";const id=job.user_id?String(job.user_id):"";const name=id?names[id]||shortId(id):"";return name?`${role} · ${name}`:source==="FUEL_MAP_USER"&&!id?"User · Anonymous/legacy":role}

export default function AdminOcrQueueList(){
  const {token,api}=useAdminAuth();
  const router=useRouter();
  const [jobs,setJobs]=useState<Job[]>([]);
  const [stations,setStations]=useState<any[]>([]);
  const [users,setUsers]=useState<any[]>([]);
  const [loading,setLoading]=useState(true);
  const [uploading,setUploading]=useState(false);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");

  async function load(){
    setLoading(true);setError("");
    try{
      const headers={authorization:`Bearer ${token}`};
      const [jobsResponse,stationsResponse,usersResponse]=await Promise.all([
        fetch(`${api}/ocr-jobs?kind=PRICE_BOARD&limit=50`,{headers}),
        fetch(`${api}/admin/stations`,{headers}),
        fetch(`${api}/admin/users`,{headers}),
      ]);
      if(!jobsResponse.ok)throw new Error("The OCR queue could not be loaded.");
      setJobs(await jobsResponse.json());
      if(stationsResponse.ok)setStations(await stationsResponse.json());
      if(usersResponse.ok)setUsers(await usersResponse.json());
    }catch(caught){setError(caught instanceof Error?caught.message:"The OCR queue could not be loaded.")}finally{setLoading(false)}
  }
  useEffect(()=>{void load();const timer=window.setInterval(()=>void load(),5000);return()=>window.clearInterval(timer)},[api,token]);

  async function upload(file:File){
    setUploading(true);setMessage("");setError("");
    try{
      const headers={authorization:`Bearer ${token}`,"content-type":"application/json"};
      const preparedResponse=await fetch(`${api}/media/upload-url`,{method:"POST",headers,body:JSON.stringify({type:"OTHER",mime_type:file.type,file_size:file.size})});
      if(!preparedResponse.ok)throw new Error(adminMutationError(preparedResponse.status));
      const prepared=await preparedResponse.json();
      const local=String(prepared.upload_url).startsWith("/");
      const uploaded=await fetch(local?`${api}${String(prepared.upload_url).replace("/api/v1","")}`:prepared.upload_url,{method:"PUT",headers:{"content-type":file.type,...(local?{authorization:`Bearer ${token}`}:{})},body:file});
      if(!uploaded.ok)throw new Error("The photo could not be uploaded.");
      const completed=await fetch(`${api}/media/complete`,{method:"POST",headers,body:JSON.stringify({storage_token:prepared.storage_token,type:"OTHER",mime_type:file.type,file_size:file.size})});
      if(!completed.ok)throw new Error(adminMutationError(completed.status));
      const media=await completed.json();
      const queued=await fetch(`${api}/ocr-jobs`,{method:"POST",headers,body:JSON.stringify({kind:"PRICE_BOARD",resource_id:media.id})});
      if(!queued.ok)throw new Error(adminMutationError(queued.status));
      setMessage("Unassigned photo added to the OCR queue.");
      await load();
    }catch(caught){setError(caught instanceof Error?caught.message:"Photo upload failed.")}finally{setUploading(false)}
  }

  const stationNames=useMemo(()=>Object.fromEntries(stations.map(station=>[station.id,station.name])),[stations]);
  const uploaderNames=useMemo(()=>Object.fromEntries(users.map(user=>[String(user.id),String(user.display_name||shortId(String(user.id)))])),[users]);

  return <><header className="admin-page-header"><div><p className="admin-kicker">Operations</p><h1>OCR Queue</h1><p>Upload price-board photos and review extracted prices before applying them.</p></div><label className="admin-primary" style={{width:"auto",marginTop:0}}>{uploading?"Uploading…":"Upload unassigned photo"}<input hidden type="file" accept="image/jpeg,image/png,image/webp" disabled={uploading} onChange={event=>{const file=event.target.files?.[0];if(file)void upload(file);event.target.value=""}}/></label></header>{message&&<p className="admin-success" role="status">{message}</p>}{error&&<p className="admin-alert" role="alert">{error}</p>}{loading&&jobs.length===0?<p className="admin-empty">Loading OCR jobs…</p>:jobs.length===0?<p className="admin-empty">No recent price-board jobs.</p>:<div className="admin-table-wrap"><table className="admin-table admin-ocr-table"><thead><tr><th>Uploaded</th><th>Uploaded by</th><th>Station</th><th>Status</th><th>Confidence</th><th>Result</th><th><span className="sr-only">Open</span></th></tr></thead><tbody>{jobs.map(job=>{const href=`/admin/ocr-queue/${encodeURIComponent(job.id)}`;return <tr key={job.id} role="link" tabIndex={0} onClick={()=>router.push(href)} onKeyDown={event=>{if(event.key==="Enter"||event.key===" ")router.push(href)}}><td>{formatDate(job.created_at)}</td><td>{formatUploader(job,uploaderNames)}</td><td>{job.station_id?stationNames[job.station_id]||job.station_id:<span className="admin-muted">Unassigned</span>}</td><td><span className={`admin-status-badge admin-status-${String(job.status).toLowerCase().replaceAll("_","-")}`}>{humanizeField(job.status)}</span></td><td>{job.confidence!=null?`${Math.round(Number(job.confidence)*100)}%`:"—"}</td><td>{job.status==="READY"||job.status==="CONFIRMED"?"Applied":job.status==="REVIEW_REQUIRED"?"Needs review":job.status==="FAILED"?job.error_message||"Failed":"Processing"}</td><td className="admin-row-arrow">→</td></tr>})}</tbody></table></div>}</>;
}
