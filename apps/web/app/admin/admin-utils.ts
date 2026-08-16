export type AdminRow = Record<string, unknown>;

type HttpDiagnostic = { status: number; message: string; requestId?: string; at: number };
const diagnosticKey = "__autoroaLastHttpDiagnostic";

const dateFieldPattern = /(?:_at|_date|datetime|timestamp)$/i;
const hiddenListFields = new Set([
  "id",
  "user_id",
  "vehicle_id",
  "station_id",
  "receipt_id",
  "media_asset_id",
  "brand_id",
  "google_place_id",
  "raw_result_json",
]);

export function filterAdminRows<T>(rows: T[], query: string) {
  const normalized = query.trim().toLowerCase();
  return normalized
    ? rows.filter((row) =>
        JSON.stringify(row).toLowerCase().includes(normalized),
      )
    : rows;
}

function latestDiagnostic(status: number) {
  const diagnostic = (globalThis as typeof globalThis & Record<string, unknown>)[diagnosticKey] as HttpDiagnostic | undefined;
  if (!diagnostic || diagnostic.status !== status || Date.now() - diagnostic.at > 10_000) return undefined;
  return diagnostic;
}

export function adminMutationError(status: number) {
  const diagnostic = latestDiagnostic(status);
  if (diagnostic) return `${diagnostic.message}${diagnostic.requestId ? ` [request ${diagnostic.requestId}]` : ""}`;
  return status === 401
    ? "Sign in again."
    : status === 403
      ? "Administrator role required."
      : status >= 500
        ? "The operation failed on the server."
        : "The operation was rejected.";
}

function errorMessageFromPayload(payload: unknown): string | undefined {
  if (!payload || typeof payload !== "object") return undefined;
  const record = payload as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  if (record.error && typeof record.error === "object") {
    const message = (record.error as Record<string, unknown>).message;
    if (typeof message === "string") return message;
  }
  return undefined;
}

export async function adminResponseError(response: Response, stage?: string) {
  const requestId = response.headers.get("x-request-id");
  let detail: string | undefined;
  try {
    const text = await response.clone().text();
    if (text) {
      try {
        detail = errorMessageFromPayload(JSON.parse(text));
      } catch {
        detail = text.length <= 300 ? text : `${text.slice(0, 300)}…`;
      }
    }
  } catch {
    // Fall back to the status-based message below.
  }
  const prefix = stage ? `${stage} failed` : "Operation failed";
  const reason = detail || adminMutationError(response.status);
  return `${prefix} (${response.status}): ${reason}${requestId ? ` [request ${requestId}]` : ""}`;
}

export function humanizeField(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function isDateField(field: string) {
  return dateFieldPattern.test(field);
}

export function formatAdminValue(field: string, value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (
    isDateField(field) &&
    (typeof value === "string" || typeof value === "number")
  ) {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) {
      return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
    }
  }
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

export function listFields(row: AdminRow, maximum = 6) {
  const fields = Object.keys(row).filter(
    (field) => !hiddenListFields.has(field),
  );
  return fields
    .sort((left, right) => Number(right === "name") - Number(left === "name"))
    .slice(0, maximum);
}

export function shortId(value: unknown) {
  const id = String(value ?? "");
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}
