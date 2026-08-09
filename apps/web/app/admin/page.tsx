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
type Section = (typeof sections)[number];

const sectionDescriptions: Record<Section, string> = {
  dashboard: "A current overview of activity and items needing attention.",
  stations: "Fuel stations available throughout the product.",
  observations: "Submitted fuel prices and their moderation status.",
  "receipt-failures": "Receipts that could not be processed successfully.",
  "unmatched-stations": "Receipts whose station still needs to be matched.",
  users: "Customer profiles registered with Carfolio.",
  vehicles: "Vehicles added by customers.",
  "fill-ups": "Recent fuel purchases recorded by customers.",
};

export default function Admin() {
  const [authReady, setAuthReady] = useState(false);
  const [adminAuthorized, setAdminAuthorized] = useState(false);
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [section, setSection] = useState<Section>("dashboard");
  const [data, setData] = useState<AdminRow[] | AdminRow>();
  const [selected, setSelected] = useState<AdminRow>();
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const requestSequence = useRef(0);
  const [authClient] = useState(() =>
    createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost",
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ??
        "development-placeholder",
    ),
  );

  useEffect(() => {
    authClient.auth.getSession().then(({ data: sessionData }) => {
      setToken(sessionData.session?.access_token ?? "");
      setAuthReady(true);
    });
    const { data: listener } = authClient.auth.onAuthStateChange(
      (_, session) => {
        setToken(session?.access_token ?? "");
        setAdminAuthorized(false);
        setAuthReady(true);
        if (!session) setData(undefined);
      },
    );
    return () => listener.subscription.unsubscribe();
  }, [authClient]);

  const load = useCallback(
    async (next: Section) => {
      if (!token) return;
      const requestId = ++requestSequence.current;
      setSection(next);
      setSelected(undefined);
      setFilter("");
      setError("");
      setData(undefined);
      setLoading(true);
      try {
        const response = await fetch(`${api}/admin/${next}`, {
          headers: { authorization: `Bearer ${token}` },
        });
        if (response.status === 401 || response.status === 403) {
          const authMessage = adminMutationError(response.status);
          setAdminAuthorized(false);
          setError(authMessage);
          await authClient.auth.signOut();
          return;
        }
        if (!response.ok) throw new Error(adminMutationError(response.status));
        const responseData = await response.json();
        if (requestId !== requestSequence.current) return;
        setAdminAuthorized(true);
        setData(responseData);
      } catch (caught) {
        if (requestId !== requestSequence.current) return;
        setError(caught instanceof Error ? caught.message : "Request failed");
      } finally {
        if (requestId === requestSequence.current) setLoading(false);
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
    const { data: session, error: authError } =
      await authClient.auth.signInWithPassword({
        email,
        password,
      });
    if (authError || !session.session) {
      setError("Administrator sign-in failed. Check your email and password.");
      setLoading(false);
      return;
    }
    setToken(session.session.access_token);
    setPassword("");
  }

  async function handleMutationFailure(response: Response) {
    setError(adminMutationError(response.status));
    if (response.status === 401 || response.status === 403) {
      setAdminAuthorized(false);
      await authClient.auth.signOut();
    }
  }

  async function moderate(id: string, isActive: boolean) {
    const response = await fetch(
      `${api}/admin/observations/${id}?is_active=${isActive}`,
      {
        method: "PATCH",
        headers: { authorization: `Bearer ${token}` },
      },
    );
    if (!response.ok) return void (await handleMutationFailure(response));
    await load("observations");
  }

  async function merge(id: string) {
    const duplicateId = prompt(
      "Duplicate station UUID to merge into this station",
    );
    if (!duplicateId) return;
    const response = await fetch(
      `${api}/admin/stations/${id}/merge?duplicate_id=${duplicateId}`,
      { method: "POST", headers: { authorization: `Bearer ${token}` } },
    );
    if (!response.ok) return void (await handleMutationFailure(response));
    await load("stations");
  }

  async function editStation(id: string) {
    const name = prompt("Station name", String(selected?.name ?? ""));
    if (!name) return;
    const response = await fetch(
      `${api}/admin/stations/${id}?name=${encodeURIComponent(name)}`,
      { method: "PATCH", headers: { authorization: `Bearer ${token}` } },
    );
    if (!response.ok) return void (await handleMutationFailure(response));
    await load("stations");
  }

  if (!authReady) return null;
  if (!token) {
    return (
      <main className="admin-login-shell">
        <form className="admin-login-card" onSubmit={signIn}>
          <div className="admin-brand">carfolio</div>
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

  if (!adminAuthorized) return null;

  const rows = Array.isArray(data) ? filterAdminRows(data, filter) : [];
  return (
    <main className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand admin-brand-light">carfolio</div>
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
              onEditStation={editStation}
              onMerge={merge}
              onModerate={moderate}
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
              {Array.isArray(data) && (
                <span className="admin-count">{rows.length} records</span>
              )}
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
              <AdminList
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
  onEditStation,
  onMerge,
  onModerate,
}: {
  section: Section;
  row: AdminRow;
  onBack: () => void;
  onEditStation: (id: string) => void;
  onMerge: (id: string) => void;
  onModerate: (id: string, active: boolean) => void;
}) {
  const id = String(row.id ?? "");
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
              <button onClick={() => onEditStation(id)}>Edit station</button>
              <button onClick={() => onMerge(id)}>Merge duplicate</button>
            </>
          )}
          {section === "observations" && (
            <button onClick={() => onModerate(id, !Boolean(row.is_active))}>
              {row.is_active ? "Disable" : "Enable"} observation
            </button>
          )}
        </div>
      </header>
      <dl className="admin-detail-grid">
        {Object.entries(row).map(([field, value]) => (
          <div
            className={
              typeof value === "object" && value !== null
                ? "admin-detail-wide"
                : ""
            }
            key={field}
          >
            <dt>{humanizeField(field)}</dt>
            <dd
              className={
                field === "id" || field.endsWith("_id") ? "admin-mono" : ""
              }
            >
              {formatAdminValue(field, value)}
            </dd>
          </div>
        ))}
      </dl>
    </>
  );
}
