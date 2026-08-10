import { describe, expect, it } from "vitest";
import {
  adminMutationError,
  filterAdminRows,
  formatAdminValue,
  listFields,
  shortId,
} from "./admin-utils";

describe("admin operations", () => {
  it("filters record metadata case-insensitively", () => {
    expect(
      filterAdminRows([{ name: "NPD Moorhouse" }, { name: "BP" }], "moor"),
    ).toEqual([{ name: "NPD Moorhouse" }]);
  });

  it("surfaces authorization failures", () => {
    expect(adminMutationError(403)).toContain("Administrator");
  });

  it("shows station names first and keeps identifiers out of list columns", () => {
    expect(
      listFields({
        id: "full-id",
        station_id: "station-id",
        google_place_id: "google-place-id",
        suburb: "Mount Eden",
        name: "Central",
        city: "Auckland",
      }),
    ).toEqual(["name", "suburb", "city"]);
  });

  it("uses the browser locale for date fields", () => {
    const expected = new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date("2026-08-09T12:00:00Z"));
    expect(formatAdminValue("created_at", "2026-08-09T12:00:00Z")).toBe(
      expected,
    );
  });

  it("shortens identifiers used in summaries", () => {
    expect(shortId("12345678-abcd-efgh")).toBe("12345678…");
  });
});
