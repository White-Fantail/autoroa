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
  const requestSequence = useRef(0);
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

  async function openRelated(target: Section, related: AdminRow) {
    const requestId = ++requestSequence.current;
    setSection(target);
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
  onEditStation,
  onMerge,
  onModerate,
  token,
  onOpenRelated,
}: {
  section: Section;
  row: AdminRow;
  onBack: () => void;
  onEditStation: (id: string) => void;
  onMerge: (id: string) => void;
  onModerate: (id: string, active: boolean) => void;
  token: string;
  onOpenRelated: (section: Section, row: AdminRow) => void;
}) {
  const [showPriceBoard, setShowPriceBoard] = useState(false);
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
                {showPriceBoard ? "Cancel price entry" : "Add prices from photo"}
              </button>
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
      {section === "stations" && showPriceBoard && (
        <PriceBoardForm
          stationId={id}
          token={token}
          onSaved={() => setShowPriceBoard(false)}
        />
      )}
      <div className="admin-detail-sections">
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

function PriceBoardForm({ stationId, token, onSaved }: {
  stationId: string;
  token: string;
  onSaved: () => void;
}) {
  const [photo, setPhoto] = useState<File>();
  const [observedAt, setObservedAt] = useState(() => {
    const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000);
    return now.toISOString().slice(0, 16);
  });
  const [prices, setPrices] = useState<Record<string, string>>({});
  const [mediaId, setMediaId] = useState<string>();
  const [confidences, setConfidences] = useState<Record<string, number>>({});
  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function analyze(selected: File) {
    setAnalyzing(true);
    setMessage("");
    setMediaId(undefined);
    setPrices({});
    setConfidences({});
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
      const analyzeResponse = await fetch(`${api}/admin/stations/${stationId}/price-board/analyze`, {
        method: "POST", headers, body: JSON.stringify({ media_asset_id: media.id }),
      });
      if (!analyzeResponse.ok) throw new Error(adminMutationError(analyzeResponse.status));
      const analysis = await analyzeResponse.json();
      const extractedPrices: Record<string, string> = {};
      const extractedConfidences: Record<string, number> = {};
      for (const entry of analysis.prices ?? []) {
        extractedPrices[entry.fuel_type] = String(entry.price_per_litre);
        extractedConfidences[entry.fuel_type] = Number(entry.confidence);
      }
      setMediaId(media.id);
      setPrices(extractedPrices);
      setConfidences(extractedConfidences);
      setMessage(Object.keys(extractedPrices).length ? "Prices extracted. Review them before saving." : "No prices were confidently detected. Enter visible prices before saving.");
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Photo analysis failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const entries = fuelTypes.filter((fuelType) => prices[fuelType]?.trim()).map((fuelType) => ({ fuel_type: fuelType, price: prices[fuelType] }));
    if (!mediaId || entries.length === 0) return;
    setSaving(true);setMessage("");
    try {
      const headers = { authorization: `Bearer ${token}`, "content-type": "application/json" };
      const saveResponse = await fetch(`${api}/admin/stations/${stationId}/price-board`, {
        method: "POST",
        headers,
        body: JSON.stringify({ media_asset_id: mediaId, observed_at: new Date(observedAt).toISOString(), prices: entries }),
      });
      if (!saveResponse.ok) throw new Error(adminMutationError(saveResponse.status));
      setMessage("Initial prices saved from the price-board photo.");
      onSaved();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Price entry failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="admin-price-board" onSubmit={submit}>
      <header>
        <div><p className="admin-kicker">Initial price collection</p><h2>Price-board photo</h2></div>
        <p>Upload a photo to extract its prices automatically, then review or correct them before saving.</p>
      </header>
      <div className="admin-price-board-grid">
        <label>Photo<input type="file" accept="image/jpeg,image/png,image/webp" required disabled={analyzing || saving} onChange={(event) => { const selected=event.target.files?.[0];setPhoto(selected);if(selected)void analyze(selected); }} /></label>
        <label>Observed at<input type="datetime-local" required value={observedAt} onChange={(event) => setObservedAt(event.target.value)} /></label>
        {fuelTypes.map((fuelType) => (
          <label key={fuelType}>{humanizeField(fuelType)}{confidences[fuelType] !== undefined && <small> {Math.round(confidences[fuelType] * 100)}% confidence</small>}<input type="number" inputMode="decimal" min="0.001" max="20" step="0.001" placeholder="Not shown" disabled={analyzing} value={prices[fuelType] ?? ""} onChange={(event) => setPrices((current) => ({ ...current, [fuelType]: event.target.value }))} /></label>
        ))}
      </div>
      {message && <p className={message.includes("saved") || message.includes("extracted") || message.includes("detected") ? "admin-success" : "admin-alert"} role="status">{message}</p>}
      <button className="admin-primary" disabled={saving || analyzing || !photo || !mediaId || !Object.values(prices).some(Boolean)} type="submit">{analyzing ? "Analyzing photo…" : saving ? "Saving confirmed prices…" : "Confirm and save prices"}</button>
    </form>
  );
}
