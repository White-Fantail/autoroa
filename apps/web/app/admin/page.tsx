"use client";

import {
  default as React,
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createClient } from "@supabase/supabase-js";
import {
  AdminRow,
  adminMutationError,
  filterAdminRows,
  formatAdminValue,
  humanizeField,
  listFields,
  shortId,
} from "./admin-utils";
import { RelatedEntity, Relation } from "./admin-related";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const sections = [
  "dashboard",
  "stations",
  "brands",
  "observations",
  "receipt-failures",
  "unmatched-stations",
  "users",
  "vehicles",
  "fill-ups",
] as const;
type Section = (typeof sections)[number];
type DetailSection = { title: string; description?: string; fields: string[] };
type AccessState =
  | "checking-session"
  | "signed-out"
  | "checking-role"
  | "authorized"
  | "forbidden"
  | "error";
const fuelTypes = ["PETROL_91", "PETROL_95", "PETROL_98", "DIESEL", "OTHER"] as const;

const sectionDescriptions: Record<Section, string> = {
  dashboard: "A current overview of activity and items needing attention.",
  stations: "Fuel stations available throughout the product.",
  brands: "Fuel station brands used to identify station networks.",
  observations: "Submitted fuel prices and their moderation status.",
  "receipt-failures": "Receipts that could not be processed successfully.",
  "unmatched-stations": "Receipts whose station still needs to be matched.",
  users: "Customer profiles registered with Autoroa.",
  vehicles: "Vehicles added by customers.",
  "fill-ups": "Recent fuel purchases recorded by customers.",
};

const detailSections: Partial<Record<Section, DetailSection[]>> = {
  stations: [
    { title: "Station", fields: ["name", "address_line", "is_active"] },
    { title: "Address", fields: ["suburb", "city", "region", "postal_code", "country_code"] },
    { title: "Location", fields: ["latitude", "longitude", "timezone", "google_place_id"] },
    { title: "Record", fields: ["id", "created_at", "updated_at"] },
  ],
  brands: [
    { title: "Brand", fields: ["name", "slug", "logo_url"] },
    { title: "Record", fields: ["id", "created_at", "updated_at"] },
  ],
  users: [
    { title: "Profile", fields: ["display_name", "country_code", "deleted_at"] },
    { title: "Preferences", fields: ["preferred_currency", "preferred_distance_unit", "preferred_efficiency_unit"] },
    { title: "Account", fields: ["id", "auth_user_id", "created_at", "updated_at"] },
  ],
  vehicles: [
    { title: "Vehicle", fields: ["nickname", "make", "model", "year", "variant"] },
    { title: "Fuel and registration", fields: ["fuel_type", "registration_plate", "tank_capacity_litres"] },
    { title: "Status", fields: ["is_primary", "is_archived"] },
    { title: "Record", fields: ["id", "created_at", "updated_at"] },
  ],
  "fill-ups": [
    { title: "Purchase", fields: ["occurred_at", "fuel_type", "litres", "total_amount", "currency"] },
    { title: "Pricing", fields: ["pump_price_per_litre", "paid_price_per_litre", "subtotal", "discount_amount"] },
    { title: "Odometer and tank", fields: ["odometer_km", "full_tank", "missed_previous_fill", "distance_since_previous_km", "notes"] },
    { title: "Fuel economy", fields: ["fuel_economy_l_per_100km", "cost_per_100km", "economy_fuel_litres", "economy_cost_amount", "economy_started_at", "economy_is_valid", "economy_warning"] },
    { title: "Record", fields: ["id", "odometer_image_id", "created_at", "updated_at"] },
  ],
  observations: [
    { title: "Observation", fields: ["fuel_type", "observed_at", "submitted_at", "source", "verification_level"] },
    { title: "Pricing", fields: ["pump_price_per_litre", "paid_price_per_litre", "discount_per_litre"] },
    { title: "Quality and moderation", fields: ["confidence_score", "is_anomaly", "is_active"] },
    { title: "Record", fields: ["id", "created_at", "updated_at"] },
  ],
  "receipt-failures": [
    { title: "Processing", fields: ["processing_status", "error_code", "error_message", "ocr_provider", "overall_confidence"] },
    { title: "Detected station", fields: ["station_text", "station_confidence"] },
    { title: "Detected purchase", fields: ["transaction_datetime", "datetime_confidence", "fuel_type", "fuel_type_confidence", "litres", "litres_confidence", "pump_price_per_litre", "price_confidence", "discount_amount", "discount_confidence", "total_amount", "total_confidence"] },
    { title: "Processing data", fields: ["raw_result_json", "processed_at"] },
    { title: "Record", fields: ["id", "media_asset_id", "created_at"] },
  ],
  "unmatched-stations": [
    { title: "Station match", fields: ["station_text", "station_confidence", "processing_status"] },
    { title: "Detected purchase", fields: ["transaction_datetime", "datetime_confidence", "fuel_type", "fuel_type_confidence", "litres", "litres_confidence", "pump_price_per_litre", "price_confidence", "discount_amount", "discount_confidence", "total_amount", "total_confidence"] },
    { title: "Processing", fields: ["ocr_provider", "overall_confidence", "error_code", "error_message", "raw_result_json", "processed_at"] },
    { title: "Record", fields: ["id", "media_asset_id", "created_at"] },
  ],
};

const relations: Partial<Record<Section, Relation[]>> = {
  stations: [{ field: "brand_id", title: "Brand", target: "brands", summaryFields: ["name", "slug", "logo_url"] }],
  vehicles: [{ field: "user_id", title: "User", target: "users", summaryFields: ["display_name", "country_code", "preferred_currency"] }],
  "fill-ups": [
    { field: "user_id", title: "User", target: "users", summaryFields: ["display_name", "country_code", "preferred_currency"] },
    { field: "vehicle_id", title: "Vehicle", target: "vehicles", summaryFields: ["nickname", "make", "model", "registration_plate"] },
    { field: "station_id", title: "Station", target: "stations", summaryFields: ["name", "address_line", "city"] },
    { field: "receipt_id", title: "Receipt", target: "receipt-failures", endpoint: "receipts", summaryFields: ["processing_status", "station_text", "transaction_datetime"] },
  ],
  observations: [
    { field: "station_id", title: "Station", target: "stations", summaryFields: ["name", "address_line", "city"] },
    { field: "fill_up_id", title: "Fill-up", target: "fill-ups", summaryFields: ["occurred_at", "litres", "total_amount", "currency"] },
    { field: "receipt_id", title: "Receipt", target: "receipt-failures", endpoint: "receipts", summaryFields: ["processing_status", "station_text", "transaction_datetime"] },
  ],
  "receipt-failures": [
    { field: "user_id", title: "User", target: "users", summaryFields: ["display_name", "country_code", "preferred_currency"] },
    { field: "station_id", title: "Station", target: "stations", summaryFields: ["name", "address_line", "city"] },
  ],
  "unmatched-stations": [
    { field: "user_id", title: "User", target: "users", summaryFields: ["display_name", "country_code", "preferred_currency"] },
    { field: "station_id", title: "Station", target: "stations", summaryFields: ["name", "address_line", "city"] },
  ],
};

export default function Admin() {
  const [accessState, setAccessState] =
    useState<AccessState>("checking-session");
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [section, setSection] = useState<Section>("dashboard");
  const [data, setData] = useState<AdminRow[] | AdminRow>();
  const [selected, setSelected] = useState<AdminRow>();
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [importNotice, setImportNotice] = useState("");
  const requestSequence = useRef(0);
  const currentSection = useRef<Section>("dashboard");
  const authGeneration = useRef(0);
  const currentToken = useRef("");
  const mounted = useRef(true);
  const [authClient] = useState(() =>
    createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost",
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ??
        "development-placeholder",
    ),
  );

  useEffect(() => {
    let active = true;
    mounted.current = true;
    const initialAuthGeneration = authGeneration.current;
    void authClient.auth
      .getSession()
      .then(({ data: sessionData, error: sessionError }) => {
        if (
          !active ||
          initialAuthGeneration !== authGeneration.current
        )
          return;
        if (sessionError) {
          setError("We could not verify your session. Please try again.");
          setAccessState("error");
          return;
        }
        const accessToken = sessionData.session?.access_token ?? "";
        currentToken.current = accessToken;
        setToken(accessToken);
        setAccessState(accessToken ? "checking-role" : "signed-out");
      })
      .catch(() => {
        if (
          !active ||
          initialAuthGeneration !== authGeneration.current
        )
          return;
        setError("We could not verify your session. Please try again.");
        setAccessState("error");
      });
    const { data: listener } = authClient.auth.onAuthStateChange(
      (_, session) => {
        const accessToken = session?.access_token ?? "";
        if (accessToken && accessToken === currentToken.current) return;
        authGeneration.current += 1;
        requestSequence.current += 1;
        currentToken.current = accessToken;
        setToken(accessToken);
        setAccessState(accessToken ? "checking-role" : "signed-out");
        if (!session) {
          setData(undefined);
          setSelected(undefined);
        }
      },
    );
    return () => {
      active = false;
      mounted.current = false;
      authGeneration.current += 1;
      requestSequence.current += 1;
      listener.subscription.unsubscribe();
    };
  }, [authClient]);

  const load = useCallback(
    async (next: Section) => {
      if (!token) return;
      const requestId = ++requestSequence.current;
      currentSection.current=next;
      setSection(next);
      setSelected(undefined);
      setShowCreate(false);
      setImportNotice("");
      setFilter("");
      setError("");
      setData(undefined);
      setLoading(true);
      setAccessState((current) =>
        current === "authorized" ? current : "checking-role",
      );
      try {
        const response = await fetch(`${api}/admin/${next}`, {
          headers: { authorization: `Bearer ${token}` },
        });
        if (!mounted.current || requestId !== requestSequence.current) return;
        if (response.status === 401) {
          const authMessage = adminMutationError(response.status);
          setError(authMessage);
          await authClient.auth.signOut();
          return;
        }
        if (response.status === 403) {
          setError(adminMutationError(response.status));
          setAccessState("forbidden");
          return;
        }
        if (!response.ok) throw new Error(adminMutationError(response.status));
        const responseData = await response.json();
        if (!mounted.current || requestId !== requestSequence.current) return;
        setAccessState("authorized");
        setData(responseData);
      } catch (caught) {
        if (!mounted.current || requestId !== requestSequence.current) return;
        setError(caught instanceof Error ? caught.message : "Request failed");
        setAccessState((current) =>
          current === "authorized" ? current : "error",
        );
      } finally {
        if (mounted.current && requestId === requestSequence.current)
          setLoading(false);
      }
    },
    [authClient, token],
  );

  useEffect(() => {
    if (token) void load("dashboard");
  }, [token, load]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading(true);
    setAccessState("checking-role");
    const { data: session, error: authError } =
      await authClient.auth.signInWithPassword({
        email,
        password,
      });
    if (authError || !session.session) {
      setError("Administrator sign-in failed. Check your email and password.");
      setAccessState("signed-out");
      setLoading(false);
      return;
    }
    currentToken.current = session.session.access_token;
    setToken(session.session.access_token);
    setPassword("");
  }

  async function handleMutationFailure(
    response: Response,
    mutationAuthGeneration: number,
  ) {
    if (
      !mounted.current ||
      mutationAuthGeneration !== authGeneration.current
    )
      return;
    setError(adminMutationError(response.status));
    if (response.status === 401 || response.status === 403) {
      if (response.status === 403) {
        setAccessState("forbidden");
      } else {
        await authClient.auth.signOut();
      }
    }
  }

  async function moderate(id: string, isActive: boolean) {
    const mutationAuthGeneration = authGeneration.current;
    const response = await fetch(
      `${api}/admin/observations/${id}?is_active=${isActive}`,
      {
        method: "PATCH",
        headers: { authorization: `Bearer ${token}` },
      },
    );
    if (
      !mounted.current ||
      mutationAuthGeneration !== authGeneration.current
    )
      return;
    if (!response.ok)
      return void (await handleMutationFailure(
        response,
        mutationAuthGeneration,
      ));
    await load("observations");
  }

  async function merge(id: string) {
    const duplicateId = prompt(
      "Duplicate station UUID to merge into this station",
    );
    if (!duplicateId) return;
    const mutationAuthGeneration = authGeneration.current;
    const response = await fetch(
      `${api}/admin/stations/${id}/merge?duplicate_id=${duplicateId}`,
      { method: "POST", headers: { authorization: `Bearer ${token}` } },
    );
    if (
      !mounted.current ||
      mutationAuthGeneration !== authGeneration.current
    )
      return;
    if (!response.ok)
      return void (await handleMutationFailure(
        response,
        mutationAuthGeneration,
      ));
    await load("stations");
  }

  async function saveManagedRecord(target: "stations" | "brands", id: string | undefined, values: AdminRow) {
    const mutationAuthGeneration = authGeneration.current;
    const response = await fetch(
      `${api}/admin/${target}${id ? `/${id}` : ""}`,
      { method: id ? "PATCH" : "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" }, body: JSON.stringify(values) },
    );
    if (
      !mounted.current ||
      mutationAuthGeneration !== authGeneration.current
    )
      return;
    if (!response.ok) {
      await handleMutationFailure(response, mutationAuthGeneration);
      throw new Error(adminMutationError(response.status));
    }
    const saved = await response.json();
    if (!mounted.current || mutationAuthGeneration !== authGeneration.current) return;
    setData((current) => Array.isArray(current) ? (id ? current.map((row) => row.id === id ? saved : row) : [...current, saved]) : current);
    setSelected(saved);setShowCreate(false);setError("");
  }

  async function openRelated(target: Section, related: AdminRow) {
    const requestId = ++requestSequence.current;
    currentSection.current=target;setSection(target);
    setData([related]);
    setSelected(related);
    setFilter("");
    setError("");
    const navigationAuthGeneration = authGeneration.current;
    try {
      const response = await fetch(`${api}/admin/${target}`, {
        headers: { authorization: `Bearer ${token}` },
      });
      if (!response.ok) return;
      const rows = await response.json();
      if (
        mounted.current &&
        requestId === requestSequence.current &&
        navigationAuthGeneration === authGeneration.current &&
        Array.isArray(rows)
      ) {
        setData(rows);
      }
    } catch {
      // Keep the selected related record available if refreshing its list fails.
    }
  }

  const refreshOCRData=useCallback(()=>{const expectedSection=section;const expectedAuthGeneration=authGeneration.current;void (async()=>{try{const response=await fetch(`${api}/admin/${expectedSection}`,{headers:{authorization:`Bearer ${token}`}});if(!response.ok)return;const refreshed=await response.json();if(!mounted.current||currentSection.current!==expectedSection||authGeneration.current!==expectedAuthGeneration)return;setData(refreshed)}catch{}})()},[section,token]);
  if (accessState === "checking-session" || accessState === "checking-role") {
    return (
      <AdminStatusCard
        title="Checking access"
        copy="We are verifying your administrator permissions."
        busy
      />
    );
  }

  if (accessState === "forbidden") {
    return (
      <AdminStatusCard
        title="Access denied"
        copy="Your account does not have permission to access Autoroa administration."
        action="Sign in with another account"
        onAction={() => void authClient.auth.signOut()}
        alert
      />
    );
  }

  if (accessState === "error") {
    return (
      <AdminStatusCard
        title="Unable to verify access"
        copy={error || "The administrator service is temporarily unavailable."}
        action={token ? "Try again" : "Return to sign in"}
        onAction={() =>
          token ? void load("dashboard") : setAccessState("signed-out")
        }
        alert
      />
    );
  }

  if (accessState === "signed-out" || !token) {
    return (
      <main className="admin-login-shell">
        <form className="admin-login-card" onSubmit={signIn}>
          <div className="admin-brand">autoroa</div>
          <p className="admin-kicker">Administration</p>
          <h1>Welcome back</h1>
          <p className="admin-login-copy">
            Sign in with your administrator account to continue.
          </p>
          <label>
            Email
            <input
              autoComplete="email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            Password
            <input
              autoComplete="current-password"
              type="password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {error && (
            <p className="admin-alert" role="alert">
              {error}
            </p>
          )}
          <button className="admin-primary" disabled={loading} type="submit">
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </main>
    );
  }

  const rows = Array.isArray(data) ? filterAdminRows(data, filter) : [];
  return (
    <main className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand admin-brand-light">autoroa</div>
        <nav aria-label="Admin sections">
          {sections.map((item) => (
            <button
              className={section === item ? "active" : ""}
              onClick={() => void load(item)}
              key={item}
            >
              {humanizeField(item)}
            </button>
          ))}
        </nav>
        <button
          className="admin-signout"
          onClick={() => void authClient.auth.signOut()}
        >
          Sign out
        </button>
      </aside>
      <section className="admin-content">
        <AdminOCRQueue token={token} onAutoApplied={refreshOCRData} />
        {importNotice && section === "stations" && <p className="admin-success" role="status">{importNotice}</p>}
        {selected ? (
          <>
            {error && (
              <p className="admin-alert" role="alert">
                {error}
              </p>
            )}
            <AdminDetail
              section={section}
              row={selected}
              onBack={() => setSelected(undefined)}
              onSaveManaged={saveManagedRecord}
              onMerge={merge}
              onModerate={moderate}
              token={token}
              onOpenRelated={openRelated}
            />
          </>
        ) : (
          <>
            <header className="admin-page-header">
              <div>
                <p className="admin-kicker">Operations</p>
                <h1>{humanizeField(section)}</h1>
                <p>{sectionDescriptions[section]}</p>
              </div>
              <div className="admin-page-actions">
                {(section === "stations" || section === "brands") && <button className="admin-primary" onClick={() => setShowCreate(true)}>Add {section === "stations" ? "station" : "brand"}</button>}
                {Array.isArray(data) && <span className="admin-count">{rows.length} records</span>}
              </div>
            </header>
            {error && (
              <p className="admin-alert" role="alert">
                {error}
              </p>
            )}
            {section === "dashboard" && data && !Array.isArray(data) && (
              <AdminDashboard data={data} />
            )}
            {section !== "dashboard" && (
              showCreate && (section === "stations" || section === "brands") ? <ManagedEntityForm kind={section} token={token} onCancel={() => setShowCreate(false)} onSave={(values) => saveManagedRecord(section, undefined, values)} onStationsImported={async (message) => { await load("stations");setImportNotice(message); }} /> : <AdminList
                rows={rows}
                loading={loading}
                filter={filter}
                onFilter={setFilter}
                onSelect={setSelected}
              />
            )}
          </>
        )}
      </section>
    </main>
  );
}

function AdminOCRQueue({token,onAutoApplied}:{token:string;onAutoApplied:()=>void}){
  const [jobs,setJobs]=useState<any[]>([]);const [stations,setStations]=useState<any[]>([]);const [review,setReview]=useState<any>();const [uploading,setUploading]=useState(false);const [message,setMessage]=useState("");const seenApplied=useRef(new Set<string>());const initialized=useRef(false);
  async function refresh(){const headers={authorization:`Bearer ${token}`};const [jobResponse,stationResponse]=await Promise.all([fetch(`${api}/ocr-jobs?kind=PRICE_BOARD&limit=20`,{headers}),fetch(`${api}/admin/stations`,{headers})]);if(jobResponse.ok)setJobs(await jobResponse.json());if(stationResponse.ok)setStations(await stationResponse.json())}
  useEffect(()=>{let active=true;async function poll(){try{const response=await fetch(`${api}/ocr-jobs?kind=PRICE_BOARD&limit=20`,{headers:{authorization:`Bearer ${token}`}});if(!response.ok)return;const next=await response.json();if(!active)return;setJobs(next);let changed=false;for(const job of next){if(job.applied_at&&!seenApplied.current.has(job.id)){seenApplied.current.add(job.id);if(initialized.current)changed=true}}initialized.current=true;if(changed)onAutoApplied()}catch{}}void refresh();const timer=setInterval(poll,5000);return()=>{active=false;clearInterval(timer)}},[token,onAutoApplied]);
  async function uploadUnassigned(file:File){setUploading(true);setMessage("");try{const headers={authorization:`Bearer ${token}`,"content-type":"application/json"};const preparedResponse=await fetch(`${api}/media/upload-url`,{method:"POST",headers,body:JSON.stringify({type:"OTHER",mime_type:file.type,file_size:file.size})});if(!preparedResponse.ok)throw new Error(adminMutationError(preparedResponse.status));const prepared=await preparedResponse.json();const local=String(prepared.upload_url).startsWith("/");const uploaded=await fetch(local?`${api}${String(prepared.upload_url).replace("/api/v1","")}`:prepared.upload_url,{method:"PUT",headers:{"content-type":file.type,...(local?{authorization:`Bearer ${token}`}:{})},body:file});if(!uploaded.ok)throw new Error("The photo could not be uploaded.");const completed=await fetch(`${api}/media/complete`,{method:"POST",headers,body:JSON.stringify({storage_token:prepared.storage_token,type:"OTHER",mime_type:file.type,file_size:file.size})});if(!completed.ok)throw new Error(adminMutationError(completed.status));const media=await completed.json();const queued=await fetch(`${api}/ocr-jobs`,{method:"POST",headers,body:JSON.stringify({kind:"PRICE_BOARD",resource_id:media.id})});if(!queued.ok)throw new Error(adminMutationError(queued.status));setMessage("Unassigned photo added to the OCR queue.");await refresh()}catch(error){setMessage(error instanceof Error?error.message:"Photo upload failed.")}finally{setUploading(false)}}
  const stationNames=Object.fromEntries(stations.map(station=>[station.id,station.name]));
  return <section aria-label="Price-board OCR queue"><header><div><h2>Price-board OCR queue</h2><p>Upload a board without choosing a station, or review jobs that need attention.</p></div><label className="admin-primary">{uploading?"Uploading…":"Upload unassigned photo"}<input hidden type="file" accept="image/jpeg,image/png,image/webp" disabled={uploading} onChange={event=>{const file=event.target.files?.[0];if(file)void uploadUnassigned(file);event.target.value=""}} /></label></header>{message&&<p role="status">{message}</p>}{jobs.length===0?<p>No recent price-board jobs.</p>:jobs.slice(0,8).map(job=><p key={job.id}>{job.station_id?stationNames[job.station_id]||job.station_id:"Station not assigned"} · {job.status}{job.confidence!=null?` · ${Math.round(Number(job.confidence)*100)}%`:''}{job.status==='REVIEW_REQUIRED'&&<button type="button" onClick={()=>setReview(job)}>Review and apply</button>}</p>)}{review&&<PriceBoardQueueReview key={review.id} job={review} stations={stations} token={token} onCancel={()=>setReview(undefined)} onSaved={async()=>{setReview(undefined);await refresh();onAutoApplied()}} />}</section>
}

function PriceBoardQueueReview({job,stations,token,onCancel,onSaved}:{job:any;stations:any[];token:string;onCancel:()=>void;onSaved:()=>void}){
  const [stationId,setStationId]=useState(job.station_id??"");const [prices,setPrices]=useState<Record<string,string>>(()=>Object.fromEntries((job.result_json?.prices??[]).map((entry:any)=>[entry.fuel_type,String(entry.price_per_litre)])));const [saving,setSaving]=useState(false);const [error,setError]=useState("");
  async function apply(event:FormEvent){event.preventDefault();const entries=fuelTypes.filter(type=>prices[type]?.trim()).map(type=>({fuel_type:type,price:prices[type]}));if(!stationId||!entries.length)return;setSaving(true);setError("");try{const response=await fetch(`${api}/admin/stations/${stationId}/price-board`,{method:"POST",headers:{authorization:`Bearer ${token}`,"content-type":"application/json"},body:JSON.stringify({job_id:job.id,media_asset_id:job.media_asset_id,observed_at:new Date(job.created_at).toISOString(),prices:entries})});if(!response.ok)throw new Error(adminMutationError(response.status));onSaved()}catch(caught){setError(caught instanceof Error?caught.message:"Could not apply prices.")}finally{setSaving(false)}}
  return <form className="admin-price-board" onSubmit={apply}><h3>Review extracted prices</h3><label>Station<select required value={stationId} onChange={event=>setStationId(event.target.value)}><option value="">Select station</option>{stations.filter(station=>station.is_active!==false).map(station=><option key={station.id} value={station.id}>{station.name} — {station.address_line}</option>)}</select></label><div className="admin-price-board-grid">{fuelTypes.map(type=><label key={type}>{humanizeField(type)}<input type="number" min="0.001" max="20" step="0.001" value={prices[type]??""} onChange={event=>setPrices(current=>({...current,[type]:event.target.value}))} /></label>)}</div>{error&&<p className="admin-alert" role="alert">{error}</p>}<div className="admin-form-actions"><button type="button" onClick={onCancel}>Cancel</button><button className="admin-primary" disabled={saving||!stationId||!Object.values(prices).some(Boolean)} type="submit">{saving?"Applying…":"Confirm and apply"}</button></div></form>
}

function AdminStatusCard({
  title,
  copy,
  action,
  onAction,
  busy = false,
  alert = false,
}: {
  title: string;
  copy: string;
  action?: string;
  onAction?: () => void;
  busy?: boolean;
  alert?: boolean;
}) {
  return (
    <main className="admin-login-shell">
      <section
        className="admin-login-card admin-status-card"
        aria-busy={busy || undefined}
        aria-live="polite"
      >
        <div className="admin-brand">autoroa</div>
        <p className="admin-kicker">Administration</p>
        <h1>{title}</h1>
        <p className="admin-login-copy" role={alert ? "alert" : undefined}>
          {copy}
        </p>
        {busy && <div className="admin-status-progress" aria-hidden="true" />}
        {action && onAction && (
          <button className="admin-primary" type="button" onClick={onAction}>
            {action}
          </button>
        )}
      </section>
    </main>
  );
}

function AdminDashboard({ data }: { data: AdminRow }) {
  return (
    <div className="admin-stats">
      {Object.entries(data).map(([label, value]) => (
        <article key={label}>
          <span>{humanizeField(label)}</span>
          <strong>{String(value)}</strong>
        </article>
      ))}
    </div>
  );
}

function AdminList({
  rows,
  loading,
  filter,
  onFilter,
  onSelect,
}: {
  rows: AdminRow[];
  loading: boolean;
  filter: string;
  onFilter: (value: string) => void;
  onSelect: (row: AdminRow) => void;
}) {
  const fields = useMemo(() => listFields(rows[0] ?? {}), [rows]);
  return (
    <div className="admin-list-card">
      <div className="admin-list-toolbar">
        <input
          aria-label="Filter records"
          placeholder="Search all fields…"
          type="search"
          value={filter}
          onChange={(event) => onFilter(event.target.value)}
        />
      </div>
      {loading ? (
        <p className="admin-empty">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="admin-empty">No records found.</p>
      ) : (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                {fields.map((field) => (
                  <th key={field}>{humanizeField(field)}</th>
                ))}
                <th>
                  <span className="sr-only">Open</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr
                  tabIndex={0}
                  role="link"
                  key={String(row.id ?? index)}
                  onClick={() => onSelect(row)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ")
                      onSelect(row);
                  }}
                >
                  {fields.map((field) => (
                    <td key={field}>{formatAdminValue(field, row[field])}</td>
                  ))}
                  <td className="admin-row-arrow" aria-hidden="true">
                    →
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AdminDetail({
  section,
  row,
  onBack,
  onSaveManaged,
  onMerge,
  onModerate,
  token,
  onOpenRelated,
}: {
  section: Section;
  row: AdminRow;
  onBack: () => void;
  onSaveManaged: (target: "stations" | "brands", id: string | undefined, values: AdminRow) => Promise<void>;
  onMerge: (id: string) => void;
  onModerate: (id: string, active: boolean) => void;
  token: string;
  onOpenRelated: (section: Section, row: AdminRow) => void;
}) {
  const [showPriceBoard, setShowPriceBoard] = useState(false);
  const [editing, setEditing] = useState(false);
  const id = String(row.id ?? "");
  const configuredRelations = relations[section] ?? [];
  const relationFields = new Set(configuredRelations.map(({ field }) => field));
  const configured = detailSections[section] ?? [];
  const includedFields = new Set(configured.flatMap(({ fields }) => fields));
  const renderedSections = configured
    .map((group) => ({ ...group, fields: group.fields.filter((field) => field in row) }))
    .filter(({ fields }) => fields.length > 0);
  const additionalFields = Object.keys(row).filter(
    (field) => !includedFields.has(field) && !relationFields.has(field),
  );
  if (additionalFields.length > 0) {
    renderedSections.push({ title: "Additional information", fields: additionalFields });
  }
  return (
    <>
      <button className="admin-back" onClick={onBack}>
        ← Back to {humanizeField(section)}
      </button>
      <header className="admin-detail-header">
        <div>
          <p className="admin-kicker">{humanizeField(section)} detail</p>
          <h1>
            {String(
              row.name ??
                row.display_name ??
                row.nickname ??
                row.station_text ??
                "Record",
            )}
          </h1>
          {id && <p className="admin-detail-id">ID {shortId(id)}</p>}
        </div>
        <div className="admin-detail-actions">
          {section === "stations" && (
            <>
              <button onClick={() => setShowPriceBoard((current) => !current)}>
                {showPriceBoard ? "Cancel price entry" : "Add station prices"}
              </button>
              <button onClick={() => setEditing(true)}>Edit station</button>
              <button onClick={() => onMerge(id)}>Merge duplicate</button>
            </>
          )}
          {section === "brands" && <button onClick={() => setEditing(true)}>Edit brand</button>}
          {section === "observations" && (
            <button onClick={() => onModerate(id, !Boolean(row.is_active))}>
              {row.is_active ? "Disable" : "Enable"} observation
            </button>
          )}
        </div>
      </header>
      {editing && (section === "stations" || section === "brands") && <ManagedEntityForm kind={section} initial={row} token={token} onCancel={() => setEditing(false)} onSave={async (values) => {await onSaveManaged(section,id,values);setEditing(false);}} />}
      {section === "stations" && showPriceBoard && (
        <PriceBoardForm
          stationId={id}
          token={token}
          onSaved={() => setShowPriceBoard(false)}
        />
      )}
      <div className="admin-detail-sections">
        {section === "receipt-failures" && Boolean(row.media_asset_id) && (
          <ReceiptImage mediaAssetId={String(row.media_asset_id)} token={token} />
        )}
        {configuredRelations.map((relation) => (
          <RelatedEntity
            apiBase={api}
            key={relation.field}
            relation={relation}
            relatedId={row[relation.field]}
            token={token}
            onOpenRelated={(target, related) => onOpenRelated(target as Section, related)}
          />
        ))}
        {renderedSections.map((group) => (
          <section className="admin-detail-section" key={group.title}>
            <header>
              <h2>{group.title}</h2>
              {group.description && <p>{group.description}</p>}
            </header>
            <dl className="admin-detail-grid">
              {group.fields.map((field) => {
                const value = row[field];
                return (
                  <div className={typeof value === "object" && value !== null ? "admin-detail-wide" : ""} key={field}>
                    <dt>{humanizeField(field)}</dt>
                    <dd className={field === "id" || field.endsWith("_id") ? "admin-mono" : ""}>
                      {formatAdminValue(field, value)}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </section>
        ))}
      </div>
    </>
  );
}

function ReceiptImage({ mediaAssetId, token }: { mediaAssetId: string; token: string }) {
  const [imageUrl, setImageUrl] = useState("");
  const [loadError, setLoadError] = useState("");
  useEffect(() => {
    let active = true;
    let objectUrl = "";
    setImageUrl("");
    setLoadError("");
    void fetch(`${api}/admin/media/${encodeURIComponent(mediaAssetId)}/content`, {
      headers: { authorization: `Bearer ${token}` },
    }).then(async (response) => {
      if (!response.ok) throw new Error("Receipt image could not be loaded.");
      const blob = await response.blob();
      if (!blob.type.startsWith("image/")) throw new Error("The uploaded file is not a supported image.");
      objectUrl = URL.createObjectURL(blob);
      if (active) setImageUrl(objectUrl);
      else URL.revokeObjectURL(objectUrl);
    }).catch((caught) => {
      if (active) setLoadError(caught instanceof Error ? caught.message : "Receipt image could not be loaded.");
    });
    return () => { active = false;if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [mediaAssetId, token]);
  return <section className="admin-detail-section admin-receipt-image">
    <header><h2>Uploaded receipt</h2></header>
    <div className="admin-receipt-image-body">
      {!imageUrl && !loadError && <p role="status">Loading receipt image…</p>}
      {loadError && <p className="admin-alert" role="alert">{loadError}</p>}
      {imageUrl && <>
        <img src={imageUrl} alt="Uploaded receipt" onError={() => setLoadError("Receipt image could not be displayed.")} />
        <a className="admin-download" href={imageUrl} download={`receipt-${mediaAssetId}`}>Download image</a>
      </>}
    </div>
  </section>;
}

const stationTextFields = [
  ["name", "Name"], ["address_line", "Address"], ["suburb", "Suburb"], ["city", "City"],
  ["region", "Region"], ["postal_code", "Postal code"], ["country_code", "Country code"],
  ["latitude", "Latitude"], ["longitude", "Longitude"], ["timezone", "Timezone"],
  ["google_place_id", "Google Place ID"],
] as const;

function ManagedEntityForm({ kind, initial, token, onCancel, onSave, onStationsImported }: {
  kind: "stations" | "brands";
  initial?: AdminRow;
  token: string;
  onCancel: () => void;
  onSave: (values: AdminRow) => Promise<void>;
  onStationsImported?: (message: string) => Promise<void>;
}) {
  const [values, setValues] = useState<Record<string, string | boolean>>(() => (kind === "brands" ? {
    name: String(initial?.name ?? ""), slug: String(initial?.slug ?? ""), logo_url: String(initial?.logo_url ?? ""),
  } : {
    brand_id: String(initial?.brand_id ?? ""), name: String(initial?.name ?? ""), google_place_id: String(initial?.google_place_id ?? ""),
    address_line: String(initial?.address_line ?? ""), suburb: String(initial?.suburb ?? ""), city: String(initial?.city ?? ""),
    region: String(initial?.region ?? ""), postal_code: String(initial?.postal_code ?? ""), country_code: String(initial?.country_code ?? "NZ"),
    latitude: String(initial?.latitude ?? ""), longitude: String(initial?.longitude ?? ""), timezone: String(initial?.timezone ?? "Pacific/Auckland"),
    is_active: Boolean(initial?.is_active ?? true),
  }) as Record<string, string | boolean>);
  const [brands, setBrands] = useState<AdminRow[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const [importResult, setImportResult] = useState("");
  const searchSequence = useRef(0);
  const importInFlight = useRef(false);
  useEffect(() => {
    if (kind !== "stations") return;
    let active = true;
    void fetch(`${api}/admin/brands`, { headers: { authorization: `Bearer ${token}` } })
      .then((response) => response.ok ? response.json() : [])
      .then((rows) => { if (active && Array.isArray(rows)) setBrands(rows); })
      .catch(() => undefined);
    return () => { active = false;searchSequence.current += 1;importInFlight.current=false; };
  }, [kind, token]);
  function update(field: string, value: string | boolean) { setValues((current) => ({ ...current, [field]: value })); }
  async function searchStations(event: FormEvent) {
    event.preventDefault();if(importInFlight.current)return;importInFlight.current=true;const searchId=++searchSequence.current;setBusy(true);setFormError("");setImportResult("");
    try {
      const response = await fetch(`${api}/admin/stations/import?q=${encodeURIComponent(query)}`, { method: "POST", headers: { authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error(response.status === 503 ? "Station search is temporarily unavailable." : response.status === 429 ? "Too many searches. Please wait and try again." : "Station import failed.");
      const result = await response.json();
      if(searchId===searchSequence.current) {
        const message=`${Number(result.added) || 0} added, ${Number(result.updated) || 0} updated, ${Number(result.already_existing) || 0} already existed${result.invalid_results ? `, ${result.invalid_results} invalid skipped` : ""}${result.duplicate_provider_results ? `, ${result.duplicate_provider_results} duplicate provider result skipped` : ""}.`;
        setImportResult(message);await onStationsImported?.(message);
      }
    } catch (caught) { if(searchId===searchSequence.current)setFormError(caught instanceof Error ? caught.message : "Station import failed."); }
    finally { importInFlight.current=false;if(searchId===searchSequence.current)setBusy(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();setBusy(true);setFormError("");
    const payload: AdminRow = kind === "brands" ? { name: values.name, slug: values.slug, logo_url: values.logo_url || null } : {
      ...values, brand_id: values.brand_id || null, google_place_id: values.google_place_id || null,
      suburb: values.suburb || null, region: values.region || null, postal_code: values.postal_code || null,
    };
    try { await onSave(payload); } catch { /* The parent keeps authorization and mutation errors in one live region. */ }
    finally { setBusy(false); }
  }
  return <section className="admin-management-form" aria-label={`${initial ? "Edit" : "Add"} ${kind === "stations" ? "station" : "brand"}`}>
    <header><div><p className="admin-kicker">{initial ? "Edit record" : "New record"}</p><h2>{initial ? `Edit ${kind === "stations" ? "station" : "brand"}` : `Add ${kind === "stations" ? "station" : "brand"}`}</h2></div></header>
    {kind === "stations" && !initial && <form className="admin-station-search" onSubmit={searchStations}>
      <label>Search Google Places<input required minLength={2} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Station name or address" /></label>
      <button type="submit" disabled={busy}>{busy ? "Searching and adding…" : "Search and add all"}</button>
    </form>}
    {importResult && <p className="admin-success" role="status">{importResult}</p>}
    {formError && <p className="admin-alert" role="alert">{formError}</p>}
    {(kind === "brands" || initial) && <form onSubmit={submit}>
      <div className="admin-management-grid">
        {kind === "brands" ? <>
          <label>Name<input required maxLength={120} value={String(values.name)} onChange={(event) => update("name",event.target.value)} /></label>
          <label>Slug<input required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" maxLength={120} value={String(values.slug)} onChange={(event) => update("slug",event.target.value)} /></label>
          <label className="admin-form-wide">Logo URL<input type="url" maxLength={2048} value={String(values.logo_url)} onChange={(event) => update("logo_url",event.target.value)} /></label>
        </> : <>
          <label>Brand<select value={String(values.brand_id)} onChange={(event) => update("brand_id",event.target.value)}><option value="">No brand</option>{brands.map((brand) => <option value={String(brand.id)} key={String(brand.id)}>{String(brand.name)}</option>)}</select></label>
          {stationTextFields.map(([field,label]) => <label key={field}>{label}<input required={["name","address_line","city","country_code","latitude","longitude","timezone"].includes(field)} type={["latitude","longitude"].includes(field) ? "number" : "text"} step="any" value={String(values[field])} onChange={(event) => update(field,event.target.value)} /></label>)}
          <label className="admin-checkbox"><input type="checkbox" checked={Boolean(values.is_active)} onChange={(event) => update("is_active",event.target.checked)} />Active</label>
        </>}
      </div>
      <div className="admin-form-actions"><button type="button" onClick={onCancel}>Cancel</button><button className="admin-primary" disabled={busy} type="submit">{busy ? "Saving…" : "Save"}</button></div>
    </form>}
    {kind === "stations" && !initial && !values.google_place_id && <button className="admin-form-cancel" type="button" onClick={onCancel}>Cancel</button>}
  </section>;
}

function PriceBoardForm({ stationId, token, onSaved }: {
  stationId: string;
  token: string;
  onSaved: () => void;
}) {
  const [observedAt, setObservedAt] = useState(() => {
    const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000);
    return now.toISOString().slice(0, 16);
  });
  const [prices, setPrices] = useState<Record<string, string>>({});
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function analyze(selected: File) {
    setAnalyzing(true);
    setMessage("");
    try {
      const headers = { authorization: `Bearer ${token}`, "content-type": "application/json" };
      const preparedResponse = await fetch(`${api}/media/upload-url`, {
        method: "POST",
        headers,
        body: JSON.stringify({ type: "OTHER", mime_type: selected.type, file_size: selected.size }),
      });
      if (!preparedResponse.ok) throw new Error(adminMutationError(preparedResponse.status));
      const prepared = await preparedResponse.json();
      const localUpload = String(prepared.upload_url).startsWith("/");
      const uploadUrl = localUpload
        ? `${api}${String(prepared.upload_url).replace("/api/v1", "")}`
        : prepared.upload_url;
      const uploadResponse = await fetch(uploadUrl, {
        method: "PUT",
        headers: {
          "content-type": selected.type,
          ...(localUpload ? { authorization: `Bearer ${token}` } : {}),
        },
        body: selected,
      });
      if (!uploadResponse.ok) throw new Error("The photo could not be uploaded.");
      const completeResponse = await fetch(`${api}/media/complete`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          storage_token: prepared.storage_token,
          type: "OTHER",
          mime_type: selected.type,
          file_size: selected.size,
        }),
      });
      if (!completeResponse.ok) throw new Error(adminMutationError(completeResponse.status));
      const media = await completeResponse.json();
      const analyzeResponse = await fetch(`${api}/ocr-jobs`, {
        method: "POST", headers, body: JSON.stringify({ kind: "PRICE_BOARD", resource_id: media.id, station_id: stationId }),
      });
      if (!analyzeResponse.ok) throw new Error(adminMutationError(analyzeResponse.status));
      await analyzeResponse.json();
      setMessage("Photo added to the OCR queue. High-confidence results will apply automatically; otherwise review them in the queue.");
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Photo analysis failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const entries = fuelTypes.filter((fuelType) => prices[fuelType]?.trim()).map((fuelType) => ({ fuel_type: fuelType, price: prices[fuelType] }));
    if (entries.length === 0) return;
    setSaving(true);setMessage("");
    try {
      const headers = { authorization: `Bearer ${token}`, "content-type": "application/json" };
      const saveResponse = await fetch(`${api}/admin/stations/${stationId}/price-board`, {
        method: "POST",
        headers,
        body: JSON.stringify({ media_asset_id: null, observed_at: new Date(observedAt).toISOString(), prices: entries }),
      });
      if (!saveResponse.ok) throw new Error(adminMutationError(saveResponse.status));
      setMessage("Initial prices saved.");
      onSaved();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Price entry failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="admin-price-board">
      <header>
        <div><p className="admin-kicker">Initial price collection</p><h2>Station prices</h2></div>
        <p>Choose one independent action: queue a photo for background OCR, or enter values for immediate application.</p>
      </header>
      <section><h3>Upload photo to queue</h3><p>The photo is queued immediately. Accurate results apply to this station automatically; uncertain results wait in the OCR queue.</p><label>Price-board photo<input type="file" accept="image/jpeg,image/png,image/webp" disabled={analyzing || saving} onChange={(event) => { const selected=event.target.files?.[0];if(selected)void analyze(selected);event.target.value=""; }} /></label></section>
      <form onSubmit={submit}><h3>Enter prices manually</h3><p>No photo is required. These values are applied immediately when you save.</p><div className="admin-price-board-grid">
        <label>Observed at<input type="datetime-local" required value={observedAt} onChange={(event) => setObservedAt(event.target.value)} /></label>
        {fuelTypes.map((fuelType) => (
          <label key={fuelType}>{humanizeField(fuelType)}<input type="number" inputMode="decimal" min="0.001" max="20" step="0.001" placeholder="Not shown" value={prices[fuelType] ?? ""} onChange={(event) => setPrices((current) => ({ ...current, [fuelType]: event.target.value }))} /></label>
        ))}
      </div>
      {message && <p className={message.includes("saved") || message.includes("extracted") || message.includes("detected") ? "admin-success" : "admin-alert"} role="status">{message}</p>}
      <button className="admin-primary" disabled={saving || !Object.values(prices).some((price) => price.trim())} type="submit">{saving ? "Saving prices…" : "Apply manual prices now"}</button></form>
    </div>
  );
}
