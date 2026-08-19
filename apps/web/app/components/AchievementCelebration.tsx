"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { supabaseBrowser } from "../../lib/supabase";

const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

type Tier={name:string}|null;
type Award={award_id:string;name:string;description:string;category:string;icon:string|null;tier:Tier;period_key:string|null;scope_key:string|null};

export default function AchievementCelebration(){
  const [queue,setQueue]=useState<Award[]>([]); const [current,setCurrent]=useState<Award|null>(null);
  const load=useCallback(async()=>{try{const {data}=await supabaseBrowser().auth.getSession();const session=data.session;if(!session)return;const response=await fetch(`${api}/me/achievement-feed`,{headers:{Authorization:`Bearer ${session.access_token}`}});if(!response.ok)return;const body=await response.json();if(Array.isArray(body)&&body.length){setQueue(body);setCurrent(body[0])}}catch{}},[]);
  useEffect(()=>{void load(); const timer=window.setInterval(()=>void load(),45000); return()=>window.clearInterval(timer)},[load]);
  const dismiss=async()=>{if(!current)return;try{const {data}=await supabaseBrowser().auth.getSession();const session=data.session;if(session)await fetch(`${api}/me/achievement-feed/seen`,{method:"POST",headers:{Authorization:`Bearer ${session.access_token}`,"Content-Type":"application/json"},body:JSON.stringify({award_ids:[current.award_id]})})}catch{}finally{const rest=queue.filter(item=>item.award_id!==current.award_id);setQueue(rest);setCurrent(rest[0]||null)}};
  if(!current)return null;
  const regional=current.category==="REGIONAL";
  return <div className="achievement-celebration" role="status" aria-live="polite"><div className="celebration-burst">{regional?"🏆":"🎉"}</div><div className="celebration-copy"><small>{current.tier?"Achievement upgraded":"Achievement unlocked"}</small><strong>{current.name}{current.tier?` · ${current.tier.name}`:""}</strong><p>{regional&&current.scope_key?`${current.scope_key==="nz"?"New Zealand":current.scope_key}${current.period_key?` · ${current.period_key}`:""}`:current.description}</p><Link href="/profile" onClick={()=>void dismiss()}>View achievements</Link></div><button type="button" className="celebration-close" aria-label="Dismiss achievement notification" onClick={()=>void dismiss()}>×</button></div>;
}
