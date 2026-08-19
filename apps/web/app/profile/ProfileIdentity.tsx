"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { supabaseBrowser } from "../../lib/supabase";
import styles from "./ProfileIdentity.module.css";

const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

type ProfilePayload={id:string;member_id:string;display_name:string;member_since:string};

export default function ProfileIdentity(){
  const [profile,setProfile]=useState<ProfilePayload|null>(null);
  const [loading,setLoading]=useState(true);
  const [editing,setEditing]=useState(false);
  const [name,setName]=useState("");
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState("");

  useEffect(()=>{let active=true;void(async()=>{try{const {data}=await supabaseBrowser().auth.getSession();const session=data.session;if(!session)return;const response=await fetch(`${api}/me/profile`,{headers:{Authorization:`Bearer ${session.access_token}`}});const body=await response.json().catch(()=>null);if(!response.ok)throw new Error(body?.detail||body?.error?.message||"Could not load your profile.");if(active){setProfile(body);setName(body.display_name||"")}}catch(e){if(active)setError(e instanceof Error?e.message:"Could not load your profile.")}finally{if(active)setLoading(false)}})();return()=>{active=false}},[]);

  const initials=useMemo(()=>{const value=profile?.display_name?.trim()||"A";return value.split(/\s+/).slice(0,2).map(part=>part[0]?.toUpperCase()).join("")||"A"},[profile]);
  const memberSince=useMemo(()=>profile?new Intl.DateTimeFormat("en-NZ",{month:"short",year:"numeric"}).format(new Date(profile.member_since)):"",[profile]);

  const save=async(event:FormEvent)=>{event.preventDefault();setSaving(true);setError("");try{const {data}=await supabaseBrowser().auth.getSession();const session=data.session;if(!session)throw new Error("Please sign in again.");const response=await fetch(`${api}/me/profile`,{method:"PATCH",headers:{Authorization:`Bearer ${session.access_token}`,"Content-Type":"application/json"},body:JSON.stringify({display_name:name})});const body=await response.json().catch(()=>null);if(!response.ok)throw new Error(typeof body?.detail==="string"?body.detail:body?.error?.message||"Could not update your display name.");setProfile(body);setName(body.display_name);setEditing(false);window.dispatchEvent(new CustomEvent("autoroa:profile-updated",{detail:{display_name:body.display_name}}))}catch(e){setError(e instanceof Error?e.message:"Could not update your display name.")}finally{setSaving(false)}};

  if(loading)return <section className={styles.card}><p className="location-message">Loading profile details…</p></section>;
  if(!profile)return error?<p className="location-message" role="alert">{error}</p>:null;

  return <section className={styles.card} aria-label="Your Autoroa identity">
    <div className={styles.avatar} aria-hidden>{initials}</div>
    <div className={styles.main}>
      <p className="eyebrow">Your Autoroa identity</p>
      {!editing?<>
        <div className={styles.titleRow}><h2>{profile.display_name}</h2><button className={styles.editButton} type="button" onClick={()=>{setName(profile.display_name);setEditing(true);setError("")}}>Edit display name</button></div>
        <p className={styles.helper}>This is the name other drivers see on Autoroa leaderboards.</p>
      </>:<form className={styles.form} onSubmit={save}>
        <label><span>Display name</span><input autoFocus maxLength={30} value={name} onChange={event=>setName(event.target.value)} /></label>
        <div className={styles.formActions}><button className="button" type="submit" disabled={saving}>{saving?"Saving…":"Save"}</button><button className="button secondary" type="button" disabled={saving} onClick={()=>{setEditing(false);setName(profile.display_name);setError("")}}>Cancel</button></div>
        <small>2–30 characters. Display names do not need to be unique.</small>
      </form>}
      {error&&<p className={styles.error} role="alert">{error}</p>}
      <div className={styles.meta}>
        <div><span>Member ID</span><strong>{profile.member_id}</strong></div>
        <div><span>Member since</span><strong>{memberSince}</strong></div>
      </div>
    </div>
    <div className={styles.action}><Link className="button secondary" href="/leaderboard?focus=me">View on leaderboard</Link></div>
  </section>;
}
