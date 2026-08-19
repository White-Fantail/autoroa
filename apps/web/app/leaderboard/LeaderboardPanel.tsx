"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { supabaseBrowser } from "../../lib/supabase";

const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

type Entry={rank:number;display_name:string;points:number;is_current_user:boolean};
type Payload={period:string;scope:string;value:string|null;entries:Entry[];current_user:Entry|null};

export default function LeaderboardPanel(){
  const [period,setPeriod]=useState("month"); const [scope,setScope]=useState("national"); const [value,setValue]=useState(""); const [data,setData]=useState<Payload|null>(null); const [loading,setLoading]=useState(true); const [signedIn,setSignedIn]=useState<boolean|null>(null); const [error,setError]=useState("");
  const needsValue=scope!=="national";
  const canLoad=!needsValue||value.trim().length>0;
  useEffect(()=>{let active=true; void (async()=>{try{const {data:auth}=await supabaseBrowser().auth.getSession(); if(!active)return; const session=auth.session; setSignedIn(!!session); if(!session){setLoading(false);return} if(!canLoad){setData(null);setLoading(false);return} setLoading(true);setError(""); const params=new URLSearchParams({period,scope}); if(needsValue)params.set("value",value.trim()); const response=await fetch(`${api}/leaderboard?${params.toString()}`,{headers:{Authorization:`Bearer ${session.access_token}`}}); const body=await response.json().catch(()=>null); if(!response.ok)throw new Error(body?.error?.message||"Could not load the leaderboard."); if(active)setData(body)}catch(e){if(active)setError(e instanceof Error?e.message:"Could not load leaderboard.")}finally{if(active)setLoading(false)}})(); return()=>{active=false}},[period,scope,value,canLoad,needsValue]);
  useEffect(()=>{if(!data||typeof window==="undefined"||new URLSearchParams(window.location.search).get("focus")!=="me")return;window.setTimeout(()=>document.getElementById("leaderboard-current-user")?.scrollIntoView({behavior:"smooth",block:"center"}),50)},[data]);
  const helper=useMemo(()=>scope==="region"?"Enter a station region, e.g. Canterbury":scope==="city"?"Enter a city, e.g. Christchurch":scope==="station"?"Enter a station ID":"",[scope]);
  if(signedIn===false)return <div className="location-message"><strong>Sign in to view contribution rankings.</strong><p>Your own rank will be shown even when you are outside the visible top list.</p><Link className="button" href="/login?next=/leaderboard">Sign in</Link></div>;
  return <div style={{display:"grid",gap:18}}>
    <section className="location-message" style={{padding:16,display:"grid",gap:12}}>
      <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>{[["month","This Month"],["all_time","All Time"]].map(([v,l])=><button className="locate-button" type="button" key={v} onClick={()=>setPeriod(v)} aria-pressed={period===v}>{l}</button>)}</div>
      <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>{[["national","New Zealand"],["region","Region"],["city","City"],["station","Station"]].map(([v,l])=><button className="locate-button" type="button" key={v} onClick={()=>{setScope(v);setValue("")}} aria-pressed={scope===v}>{l}</button>)}</div>
      {needsValue&&<label style={{display:"grid",gap:6}}><span>{helper}</span><input value={value} onChange={event=>setValue(event.target.value)} placeholder={scope==="region"?"Canterbury":scope==="city"?"Christchurch":"Station UUID"} style={{padding:"10px 12px",borderRadius:8,border:"1px solid #ccc"}} /></label>}
    </section>
    {loading?<p className="location-message">Loading leaderboard…</p>:error?<p className="location-message" role="alert">{error}</p>:!canLoad?<p className="location-message">Choose the area you want to rank.</p>:data&&data.entries.length===0?<p className="location-message">No points have been earned in this leaderboard yet.</p>:data&&<>
      <div style={{display:"grid",gap:8}}>{data.entries.map(entry=><div id={entry.is_current_user?"leaderboard-current-user":undefined} key={`${entry.rank}-${entry.display_name}`} className="location-message" style={{padding:14,display:"grid",gridTemplateColumns:"48px 1fr auto",alignItems:"center",gap:10,fontWeight:entry.is_current_user?800:500,outline:entry.is_current_user?"2px solid rgba(19,167,139,.35)":"none"}}><span>#{entry.rank}</span><span>{entry.display_name}{entry.is_current_user?" (You)":""}</span><strong>{entry.points} pts</strong></div>)}</div>
      {data.current_user&&!data.entries.some(item=>item.is_current_user)&&<div id="leaderboard-current-user" className="location-message" style={{padding:14,display:"grid",gridTemplateColumns:"48px 1fr auto",gap:10,outline:"2px solid rgba(19,167,139,.35)"}}><strong>#{data.current_user.rank}</strong><strong>{data.current_user.display_name} (You)</strong><strong>{data.current_user.points} pts</strong></div>}
      <small>Leaderboard names come from each contributor’s Autoroa display name. Contributors without one keep a privacy-safe alias.</small>
    </>}
  </div>
}
