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
  if (status === 401) return "Sign in again.";
  if (status === 403) return "Administrator role required.";
  if (status === 409) return "The upload was rejected because its upload token is expired, already used, or conflicts with an existing record.";
  if (status === 413) return "The image is larger than the server upload limit.";
  if (status === 415) return "The image format is not supported. Use JPEG, PNG, or WebP.";
  if (status === 422) return "Image validation failed. The file may be an unsupported iPhone/HEIC image, too large, corrupted, or its uploaded bytes/metadata may not match the declared image type.";
  if (status === 429) return "Too many OCR requests were submitted. Wait briefly and retry.";
  if (status === 503) return "Image storage or the OCR service is not configured or temporarily unavailable.";
  if (status >= 500) return `The operation failed on the server (HTTP ${status}).`;
  return `The operation was rejected (HTTP ${status}).`;
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
