export type AdminRow = Record<string, unknown>;

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

export function adminMutationError(status: number) {
  return status === 401
    ? "Sign in again."
    : status === 403
      ? "Administrator role required."
      : status >= 500
        ? "The operation failed on the server."
        : "The operation was rejected.";
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
