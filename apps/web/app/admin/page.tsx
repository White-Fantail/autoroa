"use client";
import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import {filterAdminRows} from './admin-utils';
const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const sections = [
  "dashboard",
  "stations",
  "observations",
  "receipt-failures",
  "unmatched-stations",
  "users",
  "vehicles",
  "fill-ups",
] as const;
export default function Admin() {
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [section, setSection] =
    useState<(typeof sections)[number]>("dashboard");
  const [data, setData] = useState<any>();
  const [error, setError] = useState("");
  const [filter,setFilter]=useState("");
  const [authClient]=useState(()=>createClient(process.env.NEXT_PUBLIC_SUPABASE_URL??'http://localhost',process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY??'development-placeholder'));
  useEffect(()=>{authClient.auth.getSession().then(({data})=>setToken(data.session?.access_token??''));const {data}=authClient.auth.onAuthStateChange((_,session)=>setToken(session?.access_token??''));return()=>data.subscription.unsubscribe()},[authClient]);
  async function signIn() {
    try {
      const { data: session, error: authError } =
        await authClient.auth.signInWithPassword({ email, password });
      if (authError || !session.session) throw authError;
      setToken(session.session.access_token);
      setError("");
    } catch {
      setError("Administrator sign-in failed");
    }
  }
  async function load(next = section) {
    setSection(next);
    setError("");
    try {
      const response = await fetch(`${api}/admin/${next}`, {
        headers: { authorization: `Bearer ${token}` },
      });
      if (!response.ok)
        throw new Error(
          response.status === 403
            ? "Administrator role required"
            : "Request failed",
        );
      setData(await response.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    }
  }
  async function moderate(id: string, is_active: boolean) {
    const response = await fetch(`${api}/admin/observations/${id}?is_active=${is_active}`, {
      method: "PATCH",
      headers: { authorization: `Bearer ${token}` },
    });
    if (!response.ok) return setError("Moderation failed");await load("observations");
  }
  async function merge(id: string) {
    const duplicate_id = prompt(
      "Duplicate station UUID to merge into this station",
    );
    if (!duplicate_id) return;
    const response = await fetch(
      `${api}/admin/stations/${id}/merge?duplicate_id=${duplicate_id}`,
      { method: "POST", headers: { authorization: `Bearer ${token}` } },
    );
    if (!response.ok) return setError("Station merge failed");await load("stations");
  }
  async function editStation(id:string){const name=prompt('Station name');if(!name)return;const response=await fetch(`${api}/admin/stations/${id}?name=${encodeURIComponent(name)}`,{method:'PATCH',headers:{authorization:`Bearer ${token}`}});if(!response.ok)return setError('Station update failed');await load('stations')}
  return (
    <main className="admin">
      <aside className="sidebar">
        <div className="logo">carfolio</div>
        <h3>Operations</h3>
        {sections.map((x) => (
          <button
            style={{
              display: "block",
              background: "none",
              border: 0,
              color: "white",
              padding: "10px 0",
              cursor: "pointer",
            }}
            onClick={() => load(x)}
            key={x}
          >
            {x.replaceAll("-", " ")}
          </button>
        ))}
      </aside>
      <section className="content">
        <h1>{section.replaceAll("-", " ")}</h1>
        <label>
          Admin email{" "}
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>{" "}
        <input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Password" /> <button onClick={signIn}>Sign in</button> <button disabled={!token} onClick={() => load()}>Load</button> <button disabled={!token} onClick={()=>authClient.auth.signOut()}>Sign out</button>
        {error && <p role="alert">{error}</p>}
        {section==='stations'&&<input aria-label="Filter stations" placeholder="Filter stations" value={filter} onChange={event=>setFilter(event.target.value)}/>} 
        {section === "dashboard" && data && (
          <div className="stats">
            {Object.entries(data).map(([label, value]) => (
              <div className="stat" key={label}>
                <span>{label.replaceAll("_", " ")}</span>
                <strong>{String(value)}</strong>
              </div>
            ))}
          </div>
        )}
        {Array.isArray(data) && (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  {Object.keys(data[0] ?? {}).map((k) => (
                    <th key={k}>{k}</th>
                  ))}
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
              {filterAdminRows(data,filter).map((row: any) => (
                  <tr key={row.id}>
                    {Object.values(row).map((v: any, i) => (
                      <td key={i}>
                        {typeof v === "object"
                          ? JSON.stringify(v)
                          : String(v ?? "")}
                      </td>
                    ))}
                    <td>
                      {section === "observations" && (
                        <button
                          onClick={() => moderate(row.id, !row.is_active)}
                        >
                          {row.is_active ? "Disable" : "Enable"}
                        </button>
                      )}
                      {section === "stations" && (
                        <><button onClick={() => editStation(row.id)}>Edit</button><button onClick={() => merge(row.id)}>Merge duplicate</button></>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
