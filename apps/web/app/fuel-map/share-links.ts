export type ShareFuel = "91" | "95" | "98" | "Diesel";

export function buildStationSharePath(stationId: string, fuel: ShareFuel) {
  const params = new URLSearchParams({ station: stationId, fuel });
  return `/fuel-map?${params.toString()}`;
}

export function buildRegionSharePath(region: string, fuel: ShareFuel) {
  const params = new URLSearchParams({ region, fuel, view: "cheapest" });
  return `/fuel-map?${params.toString()}`;
}

export function parseFuel(value: string | null): ShareFuel | null {
  return value === "91" || value === "95" || value === "98" || value === "Diesel" ? value : null;
}

export function absoluteShareUrl(path: string) {
  if (typeof window === "undefined") return path;
  return new URL(path, window.location.origin).toString();
}
