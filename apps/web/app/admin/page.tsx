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
type AccessState =
  | "checking-session"
  | "signed-out"
  | "checking-role"
  | "authorized"
  | "forbidden"
  | "error";

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
  const requestSequence = useRef(0);
  const authGeneration = useRef(0);
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
        authGeneration.current += 1;
        requestSequence.current += 1;
        const accessToken = session?.access_token ?? "";
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
      setSection(next);
      setSelected(undefined);
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

  async function editStation(id: string) {
    const name = prompt("Station name", String(selected?.name ?? ""));
    if (!name) return;
    const mutationAuthGeneration = authGeneration.current;
    const response = await fetch(
      `${api}/admin/stations/${id}?name=${encodeURIComponent(name)}`,
      { method: "PATCH", headers: { authorization: `Bearer ${token}` } },
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
        copy="Your account does not have permission to access Carfolio administration."
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
        <div className="admin-brand">carfolio</div>
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
