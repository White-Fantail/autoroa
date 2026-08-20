const adminPathRoutingScript = String.raw`(() => {
  if (window.__autoroaAdminPathRoutingInstalled) return;
  window.__autoroaAdminPathRoutingInstalled = true;

  const NativeURLSearchParams = window.URLSearchParams;
  const nativePushState = window.history.pushState.bind(window.history);
  const nativeReplaceState = window.history.replaceState.bind(window.history);

  const currentPathSection = () => {
    const match = window.location.pathname.match(/^\/admin\/([^/]+)\/?$/);
    return match ? decodeURIComponent(match[1]) : null;
  };

  class AdminAwareURLSearchParams extends NativeURLSearchParams {
    constructor(init) {
      const section = currentPathSection();
      const raw = init == null ? "" : String(init);
      const shouldInjectSection =
        Boolean(section) &&
        raw === window.location.search &&
        !new NativeURLSearchParams(raw).has("section");
      super(shouldInjectSection ? `section=${encodeURIComponent(section)}` : init);
    }
  }

  Object.defineProperty(window, "URLSearchParams", {
    configurable: true,
    writable: true,
    value: AdminAwareURLSearchParams,
  });

  const normalizeAdminUrl = (url) => {
    if (url == null) return url;
    const resolved = new URL(String(url), window.location.href);
    if (resolved.origin !== window.location.origin) return url;
    if (resolved.pathname !== "/admin" && !resolved.pathname.startsWith("/admin/")) {
      return url;
    }

    const params = new NativeURLSearchParams(resolved.search);
    const section = params.get("section");
    if (!section) return url;

    params.delete("section");
    resolved.pathname = `/admin/${encodeURIComponent(section)}`;
    const query = params.toString();
    return `${resolved.pathname}${query ? `?${query}` : ""}${resolved.hash}`;
  };

  window.history.pushState = function pushState(state, unused, url) {
    return nativePushState(state, unused, normalizeAdminUrl(url));
  };

  window.history.replaceState = function replaceState(state, unused, url) {
    return nativeReplaceState(state, unused, normalizeAdminUrl(url));
  };

  if (window.location.pathname === "/admin") {
    const params = new NativeURLSearchParams(window.location.search);
    const section = params.get("section") || "dashboard";
    params.delete("section");
    const query = params.toString();
    nativeReplaceState(
      window.history.state,
      "",
      `/admin/${encodeURIComponent(section)}${query ? `?${query}` : ""}${window.location.hash}`,
    );
  }
})();`;

export default function AdminPathRoutingCompatibility() {
  return <script dangerouslySetInnerHTML={{ __html: adminPathRoutingScript }} />;
}

declare global {
  interface Window {
    __autoroaAdminPathRoutingInstalled?: boolean;
  }
}
