export type QuickCaptureMode = "receipt" | "full";

/** Stable entry URLs for iOS Shortcuts, Home Screen shortcuts, and future widgets. */
export const quickCaptureUrls: Record<QuickCaptureMode, string> = {
  receipt: "autoroa://quick-capture?mode=receipt",
  full: "autoroa://quick-capture?mode=full",
};

export function captureModeFromUrl(url: string | null): QuickCaptureMode | null {
  if (!url || !/^autoroa:\/\/\/?quick-capture\/?(?:[?#]|$)/i.test(url)) return null;
  return /[?&]mode=full(?:[&#]|$)/i.test(url) ? "full" : "receipt";
}
