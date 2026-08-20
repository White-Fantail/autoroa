"use client";

import { useEffect, useState } from "react";
import { useAdminAuth } from "./AdminAuthShell";

type ModerationStatus="ACTIVE"|"SUSPENDED"|"BANNED";
type ModerationEvent={id:string;previous_status:ModerationStatus;new_status:ModerationStatus;reason?:string|null;created_at:string};
type ModeratedUser={id:string;moderation_status:ModerationStatus;moderation_reason?:string|null;moderated_at?:string|null;moderation_history?:ModerationEvent[]};

function label(status:ModerationStatus){return status==="SUSPENDED"?"Suspended":status==="BANNED"?"Banned":"Active"}
function formatDate(value?:string|null){if(!value)return "—";const date=new Date(value);return Number.isNaN(date.getTime())?"—":new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(date)}

export default function AdminUserModerationPanel({id}:{id:string}){
  const {token,api}=useAdminAuth();
  const [user,setUser]=useState<ModeratedUser|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");

  async function load(){
    try{const response=await fetch(`${api}/admin/users/${encodeURIComponent(id)}`,{headers:{authorization:`Bearer ${token}`}});if(!response.ok)throw new Error("User moderation details could not be loaded.");setUser(await response.json());setError("")}catch(caught){setError(caught instanceof Error?caught.message:"User moderation details could not be loaded.")}
  }
  useEffect(()=>{void load()},[api,id,token]);

  async function updateStatus(status:ModerationStatus){
    if(!user||busy)return;
    let reason:string|null=null;
    if(status==="SUSPENDED"||status==="BANNED"){
      const entered=window.prompt(status==="SUSPENDED"?"Why is this user being suspended?":"Why is this user being permanently banned?");
      if(entered===null)return;
      reason=entered.trim();
      if(!reason){setError("A moderation reason is required.");return}
    }else{
      if(!window.confirm("Reactivate this user and restore contribution access?"))return;
      reason="Restriction lifted by administrator";
    }
    setBusy(true);setMessage("");setError("");
    try{const response=await fetch(`${api}/admin/users/${encodeURIComponent(id)}/moderation`,{method:"PATCH",headers:{authorization:`Bearer ${token}`,"content-type":"application/json"},body:JSON.stringify({status,reason})});const payload=await response.json().catch(()=>null);if(!response.ok)throw new Error(payload?.error?.message??payload?.detail??"The moderation change was rejected.");setUser(payload);setMessage(status==="ACTIVE"?"User reactivated.":status==="SUSPENDED"?"User suspended.":"User banned.")}catch(caught){setError(caught instanceof Error?caught.message:"The moderation change failed.")}finally{setBusy(false)}
  }

  if(!user&&!error)return <section className="admin-detail-section"><header><h2>Moderation</h2></header><p className="admin-empty">Loading moderation…</p></section>;
  return <section className="admin-detail-section" aria-label="User moderation"><header><div><h2>Moderation</h2><p>Contribution restrictions and administrator action history.</p></div><div className="admin-detail-actions">{user&&<><span className={`admin-status-badge admin-status-${user.moderation_status.toLowerCase()}`}>{label(user.moderation_status)}</span>{user.moderation_status!=="ACTIVE"&&<button type="button" disabled={busy} onClick={()=>void updateStatus("ACTIVE")}>{busy?"Updating…":"Reactivate"}</button>}{user.moderation_status!=="SUSPENDED"&&<button type="button" disabled={busy} onClick={()=>void updateStatus("SUSPENDED")}>Suspend user</button>}{user.moderation_status!=="BANNED"&&<button type="button" disabled={busy} onClick={()=>void updateStatus("BANNED")} style={{borderColor:"#b42318",color:"#b42318"}}>Ban user</button>}</>}</div></header>{message&&<p className="admin-success" role="status">{message}</p>}{error&&<p className="admin-alert" role="alert">{error}</p>}{user&&<><dl className="admin-detail-grid"><div><dt>Status</dt><dd>{label(user.moderation_status)}</dd></div><div><dt>Reason</dt><dd>{user.moderation_reason||"—"}</dd></div><div><dt>Last moderated</dt><dd>{formatDate(user.moderated_at)}</dd></div></dl><div style={{marginTop:18}}><h3>History</h3>{(user.moderation_history??[]).length===0?<p className="admin-empty">No moderation actions recorded.</p>:<div style={{display:"grid",gap:10}}>{(user.moderation_history??[]).map(event=><div key={event.id} style={{borderTop:"1px solid var(--border)",paddingTop:10}}><strong>{label(event.previous_status)} → {label(event.new_status)}</strong><div className="admin-muted">{formatDate(event.created_at)}{event.reason?` · ${event.reason}`:""}</div></div>)}</div>}</div></>}</section>;
}
