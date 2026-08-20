export function adminSectionFromLocation(fallback = "dashboard") {
  if (typeof window === "undefined") return fallback;
  const match = window.location.pathname.match(/^\/admin\/([^/]+)(?:\/[^/]+)?\/?$/);
  if (match) return decodeURIComponent(match[1]);
  return new URLSearchParams(window.location.search).get("section") ?? fallback;
}

export function adminDetailIdFromLocation(section?: string) {
  if (typeof window === "undefined") return null;
  const match = window.location.pathname.match(/^\/admin\/([^/]+)\/([^/]+)\/?$/);
  if (!match) return null;
  const currentSection = decodeURIComponent(match[1]);
  if (section && currentSection !== section) return null;
  return decodeURIComponent(match[2]);
}

function adminUrl(section: string, id?: string) {
  const base = `/admin/${encodeURIComponent(section)}`;
  return `${base}${id ? `/${encodeURIComponent(id)}` : ""}${window.location.hash}`;
}

export function pushAdminSection(section: string) {
  window.history.pushState({ section }, "", adminUrl(section));
}

export function replaceAdminSection(section: string) {
  window.history.replaceState({ section }, "", adminUrl(section));
}

export function pushAdminDetail(section: string, id: string) {
  window.history.pushState(
    { section, id, autoroaAdminDetail: true },
    "",
    adminUrl(section, id),
  );
}

export function leaveAdminDetail(section: string) {
  if (window.history.state?.autoroaAdminDetail) {
    window.history.back();
    return;
  }
  replaceAdminSection(section);
}
