"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { supabaseBrowser } from "../../lib/supabase";

const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
type FuelResult={fuel_type:string;previous_price:number|null;submitted_price:number;final_price:number|null;result:string;points:number};
type Contribution={id:string;created_at:string;status:string;station:{name:string;address:string;city:string;region:string|null}|null;points:number;fuel_results:FuelResult[];review_reason:string|null};
type Badge={id:string;name:string;description:string;earned:boolean;progress:number;target:number};
type Summary={total_points:number;month_points:number;submission_count:number;applied_price_count:number;contributed_station_count:number;badges:Badge[]};
type Props={embedded?:boolean};
const labels:Record<string,string>={REVIEWING:"Reviewing",APPLIED:"Applied",NO_POINTS:"No points",FAILED:"Failed"};
const fuels:Record<string,string>={PETROL_91:"91",PETROL_95:"95",PETROL_98:"98",DIESEL:"Diesel",OTHER:"Other"};
const resultText:Record<string,string>={APPLIED:"Updated",NO_CHANGE:"No change",STALE:"Older data",NOT_APPLIED:"Not applied"};
function price(value:number|null){return value===null?"—":value.toFixed(3)}

export default function ContributionsPanel({embedded=false}:Props){
  const [rows,setRows]=useState<Contribution[]>([]),[summary,setSummary]=useState<Summary|null>(null),[filter,setFilter]=useState("ALL"),[loading,setLoading]=useState(true),[signedIn,setSignedIn]=useState<boolean|null>(null),[error,setError]=useState("");
  useEffect(()=>{let active=true;void(async()=>{try{const {data}=await supabaseBrowser().auth.getSession();if(!active)return;const session=data.session;setSignedIn(!!session);if(!session){setLoading(false);return}const headers={Authorization:`Bearer ${session.access_token}`};const[a,b]=await Promise.all([fetch(`${api}/me/contributions`,{headers}),fetch(`${api}/me/contribution-summary`,{headers})]);if(!a.ok||!b.ok)throw new Error("Could not load your contribution history.");const[items,total]=await Promise.all([a.json(),b.json()]);if(active){setRows(items);setSummary(total)}}catch(e){if(active)setError(e instanceof Error?e.message:"Could not load contributions.")}finally{if(active)setLoading(false)}})();return()=>{active=false}},[]);
  if(loading)return <p className="location-message">Loading your contributions…</p>;
  if(signedIn===false)return <div className="location-message"><strong>Sign in to see your contributions.</strong><p>Your verified price updates and earned points will appear here.</p><Link className="button" href={`/login?next=${embedded?"/profile":"/contributions"}`}>Sign in</Link></div>;
  if(error)return <p className="location-message" role="alert">{error}</p>;
  const filtered=filter==="ALL"?rows:rows.filter(row=>row.status===filter);
  const visible=embedded?rows.slice(0,5):filtered;
  return <div style={{display:"grid",gap:22}}>
    {summary&&<>
      <section style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(150px,1fr))",gap:12}}>{[['All-time points',summary.total_points],['This month',summary.month_points],['Submissions',summary.submission_count],['Prices updated',summary.applied_price_count],['Stations helped',summary.contributed_station_count]].map(([label,value])=><div key={String(label)} className="location-message" style={{padding:16}}><div style={{fontSize:26,fontWeight:800}}>{value}</div><small>{label}</small></div>)}</section>
      {!embedded&&<section className="location-message" style={{padding:18}}><h2 style={{marginTop:0}}>Badges</h2><div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:10}}>{summary.badges.map(badge=><div key={badge.id} style={{padding:12,border:"1px solid rgba(127,127,127,.25)",borderRadius:12,opacity:badge.earned?1:.68}}><strong>{badge.earned?"✓ ":"○ "}{badge.name}</strong><p style={{margin:"6px 0",fontSize:13}}>{badge.description}</p><small>{badge.earned?"Earned":`${badge.progress}/${badge.target}`}</small></div>)}</div></section>}
    </>}
    {embedded?<div style={{display:"flex",justifyContent:"space-between",gap:12,alignItems:"baseline"}}><div><p className="eyebrow" style={{marginBottom:4}}>Activity</p><h2 style={{margin:0}}>Recent contributions</h2></div><Link href="/contributions">View all</Link></div>:<div style={{display:"flex",gap:8,flexWrap:"wrap"}}>{[['ALL','All'],['REVIEWING','Reviewing'],['APPLIED','Applied'],['NO_POINTS','No points']].map(([value,label])=><button key={value} className="locate-button" type="button" onClick={()=>setFilter(value)} aria-pressed={filter===value}>{label}</button>)}</div>}
    {visible.length===0?<p className="location-message">No contributions in this view yet.</p>:visible.map(row=><article key={row.id} className="location-message" style={{padding:18,display:"grid",gap:12}}><div style={{display:"flex",justifyContent:"space-between",gap:12,alignItems:"flex-start"}}><div><strong>{row.station?.name||"Station under review"}</strong><div><small>{row.station?.address||"We’re verifying the station."}</small></div></div><div style={{textAlign:"right"}}><strong>{row.points>0?`+${row.points} pts`:labels[row.status]||row.status}</strong><div><small>{new Date(row.created_at).toLocaleString('en-NZ')}</small></div></div></div>{row.fuel_results.length>0&&<div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",textAlign:"left"}}><thead><tr><th>Fuel</th><th>Before</th><th>Your photo</th><th>Result</th></tr></thead><tbody>{row.fuel_results.map(item=><tr key={item.fuel_type}><td>{fuels[item.fuel_type]||item.fuel_type}</td><td>{price(item.previous_price)}</td><td>{price(item.submitted_price)}</td><td>{resultText[item.result]||item.result}{item.points?` +${item.points}`:""}</td></tr>)}</tbody></table></div>}{row.status==="REVIEWING"&&<small>Your photo is still being verified. Points are awarded only after a price is actually applied.</small>}{row.review_reason&&row.status==="REVIEWING"&&<small>{row.review_reason}</small>}</article>)}
  </div>
}
