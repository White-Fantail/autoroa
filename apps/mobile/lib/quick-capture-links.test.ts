import { describe, expect, it } from "vitest";
import { captureModeFromUrl, quickCaptureUrls } from "./quick-capture-links";

describe("Quick Capture Shortcut entry", () => {
  it("opens a receipt capture by default", () => {
    expect(captureModeFromUrl(quickCaptureUrls.receipt)).toBe("receipt");
    expect(captureModeFromUrl("autoroa://quick-capture")).toBe("receipt");
  });
  it("routes the two-photo mode without entering the main dashboard", () => {
    expect(captureModeFromUrl(quickCaptureUrls.full)).toBe("full");
    expect(captureModeFromUrl("autoroa:///quick-capture?source=shortcut&mode=full")).toBe("full");
  });
  it("rejects unrelated and lookalike URLs", () => {
    expect(captureModeFromUrl(null)).toBeNull();
    expect(captureModeFromUrl("https://some.site/quick-capture")).toBeNull();
    expect(captureModeFromUrl("autoroa://quick-capture-malicious")).toBeNull();
    expect(captureModeFromUrl("autoroa://fill-up?mode=full")).toBeNull();
  });
});
