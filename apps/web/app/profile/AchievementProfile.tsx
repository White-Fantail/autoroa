"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { supabaseBrowser } from "../../lib/supabase";

const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

type Tier={id:string;key:string;name:string;threshold:number|null;sort_order:number;icon:string|null};
type Achievement={id:string;key:string|null;name:string;description:string;category:string;icon:string|null;visibility:string;achievement_type:string;earned:boolean;earned_count:number;first_earned_at:string|null;last_earned_at:string|null;progress:Record<string,unknown>;current_tier:Tier|null;next_tier:Tier|null;tiers:Tier[];revoked_at:string|null};
type Title={scope_type:string;scope_key:string;scope_label:string;rank:number;points:number;is_number_one:boolean};
type TrophySummary={achievement_key:string;name:string;scope_type:string;scope_key:string;count:number;periods:string[]};
type Payload={achievements:Achievement[];featured_achievement_ids:string[];current_titles:Title[];trophy_summary:TrophySummary[];trophies:unknown[]};

const categoryNames:Record<string,string>={STARTER:"Starter",CONTRIBUTION:"Contribution",EXPLORATION:"Exploration",QUALITY:"Quality",SPECIAL:"Special",REGIONAL:"Regional"};
const iconFor=(achievement:Achievement)=>achievement.current_tier?.icon||achievement.icon||"badge";
const emoji=(icon:string|null)=>({spot:"📍",camera:"📷",spark:"✨",road:"🛣️",ten:"🔟",price:"⛽",station:"⛽",compass:"🧭",map:"🗺️",car:"🚗",regions:"🌏",nz:"🇳🇿",sunrise:"🌅",moon:"🌙",route:"🛣️",fire:"🔥",return:"↩️",secret:"❓",fresh:"🌱",rescue:"🛟",board:"🧾",trusted:"⭐",trophy:"🏆",bronze:"🥉",silver:"🥈",gold:"🥇",platinum:"🏅",diamond:"💎"}[icon||""]||"🏅");

function progressValues(a:Achievement){
  const p=a.progress||{}; const current=Number(p.current??0); const target=Number(p.target??0); const percent=Number(p.percent??0);
  return {current:Number.isFinite(current)?current:0,target:Number.isFinite(target)?target:0,percent:Number.isFinite(percent)?Math.max(0,Math.min(100,percent)):0};
}

export default function AchievementProfile(){
  const [data,setData]=useState<Payload|null>(null); const [signedIn,setSignedIn]=useState<boolean|null>(null); const [loading,setLoading]=useState(true); const [error,setError]=useState(""); const [saving,setSaving]=useState(false); const [signingOut,setSigningOut]=useState(false); const [featured,setFeatured]=useState<string[]>([]); const [category,setCategory]=useState("ALL");
  const load=async()=>{setLoading(true);setError("");try{const {data:auth}=await supabaseBrowser().auth.getSession();const session=auth.session;setSignedIn(!!session);if(!session)return;const response=await fetch(`${api}/me/achievement-profile`,{headers:{Authorization:`Bearer ${session.access_token}`}});const body=await response.json().catch(()=>null);if(!response.ok)throw new Error(body?.error?.message||"Could not load achievements.");setData(body);setFeatured(body.featured_achievement_ids||[])}catch(e){setError(e instanceof Error?e.message:"Could not load achievements.")}finally{setLoading(false)}};
  useEffect(()=>{void load()},[]);
  const earnedById=useMemo(()=>new Map((data?.achievements||[]).filter(item=>item.earned).map(item=>[item.id,item])),[data]);
  const displayed=useMemo(()=>{const all=data?.achievements||[];return category==="ALL"?all:all.filter(item=>item.category===category)},[data,category]);
  const toggleFeatured=(id:string)=>{setFeatured(current=>current.includes(id)?current.filter(item=>item!==id):current.length<3?[...current,id]:current)};
  const saveFeatured=async()=>{setSaving(true);setError("");try{const {data:auth}=await supabaseBrowser().auth.getSession();const session=auth.session;if(!session)return;const response=await fetch(`${api}/me/featured-achievements`,{method:"PUT",headers:{Authorization:`Bearer ${session.access_token}`,"Content-Type":"application/json"},body:JSON.stringify({achievement_ids:featured})});const body=await response.json().catch(()=>null);if(!response.ok)throw new Error(body?.error?.message||"Could not save featured achievements.");setData(current=>current?{...current,featured_achievement_ids:body.featured_achievement_ids}:current)}catch(e){setError(e instanceof Error?e.message:"Could not save featured achievements.")}finally{setSaving(false)}};
  const signOut=async()=>{setSigningOut(true);setError("");try{const {error:signOutError}=await supabaseBrowser().auth.signOut();if(signOutError)throw signOutError;window.location.assign("/")}catch(e){setError(e instanceof Error?e.message:"Could not sign out.");setSigningOut(false)}};
  if(loading)return <p className="location-message">Loading achievements…</p>;
  if(signedIn===false)return <div className="location-message"><strong>Sign in to view your achievement profile.</strong><p>Your badges, trophies and progress are attached to your Autoroa account.</p><Link className="button" href="/login?next=/profile">Sign in</Link></div>;
  if(error&&!data)return <p className="location-message" role="alert">{error}</p>;
  if(!data)return null;
  const earnedCount=data.achievements.filter(item=>item.earned).length;
  return <div className="achievement-profile-grid">
    {error&&<p className="location-message" role="alert">{error}</p>}
    <section className="achievement-hero-card">
      <div><p className="eyebrow">Achievement collection</p><h2>{earnedCount} unlocked</h2><p>Choose up to three earned achievements to represent you across your profile.</p></div>
      <div className="featured-achievements">
        {featured.length===0?<span className="featured-empty">No featured achievements yet</span>:featured.map(id=>{const a=earnedById.get(id);return a?<div className="featured-badge" key={id}><span>{emoji(iconFor(a))}</span><div><strong>{a.name}</strong>{a.current_tier&&<small>{a.current_tier.name}</small>}</div></div>:null})}
      </div>
      <button className="button secondary" type="button" disabled={saving||featured.join(",")===data.featured_achievement_ids.join(",")} onClick={()=>void saveFeatured()}>{saving?"Saving…":"Save featured"}</button>
    </section>

    {data.current_titles.length>0&&<section className="achievement-section"><div className="achievement-section-heading"><div><p className="eyebrow">Current standings</p><h2>Current titles</h2></div><Link href="/leaderboard">View leaderboard</Link></div><div className="current-title-grid">{data.current_titles.map(title=><div className={`current-title-card${title.is_number_one?" number-one":""}`} key={`${title.scope_type}-${title.scope_key}`}><span className="title-crown">{title.is_number_one?"👑":"🏁"}</span><div><strong>{title.scope_label} #{title.rank}</strong><small>{title.points} pts this month · {title.scope_type.toLowerCase()}</small></div></div>)}</div></section>}

    {data.trophy_summary.length>0&&<section className="achievement-section"><div className="achievement-section-heading"><div><p className="eyebrow">Permanent record</p><h2>Regional trophies</h2></div></div><div className="trophy-grid">{data.trophy_summary.map(trophy=><div className="trophy-card" key={`${trophy.achievement_key}-${trophy.scope_type}-${trophy.scope_key}`}><span>🏆</span><div><strong>{trophy.scope_key==="nz"?"New Zealand":trophy.scope_key} {trophy.name}</strong><small>{trophy.count}× earned</small><p>{trophy.periods.slice(0,4).join(" · ")}{trophy.periods.length>4?` · +${trophy.periods.length-4} more`:""}</p></div></div>)}</div></section>}

    <section className="achievement-section"><div className="achievement-section-heading"><div><p className="eyebrow">Collection</p><h2>All achievements</h2></div><span>{featured.length}/3 featured</span></div><div className="achievement-tabs">{["ALL","STARTER","CONTRIBUTION","EXPLORATION","QUALITY","SPECIAL","REGIONAL"].map(key=><button type="button" className="achievement-tab" aria-pressed={category===key} onClick={()=>setCategory(key)} key={key}>{key==="ALL"?"All":categoryNames[key]}</button>)}</div><div className="achievement-card-grid">{displayed.map(a=>{const p=progressValues(a);const selected=featured.includes(a.id);return <article className={`achievement-card${a.earned?" earned":" locked"}${selected?" featured-selected":""}`} key={a.id}><div className="achievement-icon" aria-hidden>{emoji(iconFor(a))}</div><div className="achievement-card-body"><div className="achievement-card-title"><div><strong>{a.name}</strong>{a.current_tier&&<span className="achievement-tier">{a.current_tier.name}</span>}</div>{a.earned&&<span className="earned-mark">Unlocked</span>}</div><p>{a.description}</p>{a.achievement_type==="TIERED"&&a.next_tier&&p.target>0&&<div className="achievement-progress"><div><span>{p.current.toLocaleString()}</span><span>{p.target.toLocaleString()}</span></div><div className="achievement-progress-track"><span style={{width:`${p.percent}%`}} /></div><small>Next: {a.next_tier.name}</small></div>}{!a.earned&&a.achievement_type!=="TIERED"&&Object.keys(a.progress||{}).length>0&&p.target>0&&<div className="achievement-progress"><div><span>{p.current.toLocaleString()}</span><span>{p.target.toLocaleString()}</span></div><div className="achievement-progress-track"><span style={{width:`${p.percent}%`}} /></div></div>}{a.earned&&<button type="button" className="feature-toggle" aria-pressed={selected} disabled={!selected&&featured.length>=3} onClick={()=>toggleFeatured(a.id)}>{selected?"Featured":"Feature"}</button>}</div></article>})}</div></section>

    <section className="achievement-section">
      <div className="achievement-section-heading"><div><p className="eyebrow">Account</p><h2>Account</h2></div></div>
      <p>Sign out of Autoroa on this device.</p>
      <button className="button secondary" type="button" disabled={signingOut} onClick={()=>void signOut()}>{signingOut?"Signing out…":"Sign out"}</button>
    </section>
  </div>;
}
