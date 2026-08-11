// @vitest-environment jsdom

import {
  cleanup,
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({
  token: "" as string,
  getSession: vi.fn(),
  listener: undefined as
    ((event: string, session: unknown) => void) | undefined,
  signOut: vi.fn(),
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      getSession: auth.getSession,
      onAuthStateChange: vi.fn((callback) => {
        auth.listener = callback;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      }),
      signInWithPassword: vi.fn(async () => ({
        data: { session: { access_token: "signed-in-token" } },
        error: null,
      })),
      signOut: auth.signOut,
    },
  }),
}));

import Admin from "./page";
import { RelatedEntity, Relation } from "./admin-related";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn(async () => body),
  } as unknown as Response;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

describe("admin page", () => {
  beforeEach(() => {
    auth.token = "";
    auth.getSession.mockReset();
    auth.getSession.mockImplementation(async () => ({
      data: { session: auth.token ? { access_token: auth.token } : null },
      error: null,
    }));
    auth.listener = undefined;
    auth.signOut.mockReset();
    auth.signOut.mockImplementation(async () => {
      auth.token = "";
      auth.listener?.("SIGNED_OUT", null);
    });
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows only the sign-in screen without a session", async () => {
    render(<Admin />);
    expect(
      await screen.findByRole("heading", { name: "Welcome back" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("navigation", { name: "Admin sections" }),
    ).toBeNull();
  });

  it("renders the admin shell after the dashboard authorizes the session", async () => {
    auth.token = "admin-token";
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ users: 12 }));
    render(<Admin />);
    expect(
      await screen.findByRole("navigation", { name: "Admin sections" }),
    ).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Welcome back" })).toBeNull();
  });

  it("keeps access authorized when the auth client repeats the current session", async () => {
    auth.token = "admin-token";
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ users: 12 }));
    render(<Admin />);
    expect(
      await screen.findByRole("navigation", { name: "Admin sections" }),
    ).toBeTruthy();

    await act(async () => {
      auth.listener?.("TOKEN_REFRESHED", { access_token: "admin-token" });
    });

    expect(
      screen.getByRole("navigation", { name: "Admin sections" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "Checking access" }),
    ).toBeNull();
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("returns an expired session to sign-in", async () => {
    auth.token = "invalid-token";
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}, 401));
    render(<Admin />);
    expect(
      await screen.findByRole("heading", { name: "Welcome back" }),
    ).toBeTruthy();
    expect(auth.signOut).toHaveBeenCalledOnce();
    expect(screen.getByRole("alert").textContent).toMatch(/Sign in again/);
  });

  it("shows access denied without signing out a non-admin user", async () => {
    auth.token = "member-token";
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}, 403));
    render(<Admin />);
    expect(
      await screen.findByRole("heading", { name: "Access denied" }),
    ).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toMatch(
      /does not have permission/,
    );
    expect(
      screen.getByRole("button", { name: "Sign in with another account" }),
    ).toBeTruthy();
    expect(auth.signOut).not.toHaveBeenCalled();
  });

  it("renders an accessible loading state while the session is checked", () => {
    auth.getSession.mockReturnValue(new Promise(() => {}));
    render(<Admin />);
    expect(screen.getByRole("heading", { name: "Checking access" })).toBeTruthy();
    expect(screen.getByText(/verifying your administrator permissions/)).toBeTruthy();
  });

  it("offers a retry when the admin service fails", async () => {
    auth.token = "admin-token";
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}, 500));
    render(<Admin />);
    expect(
      await screen.findByRole("heading", { name: "Unable to verify access" }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("recovers from a session lookup error without a blank screen", async () => {
    auth.getSession.mockRejectedValue(new Error("network failure"));
    render(<Admin />);
    expect(
      await screen.findByRole("heading", { name: "Unable to verify access" }),
    ).toBeTruthy();
    expect(screen.getByRole("alert").textContent).not.toContain("network failure");
  });

  it("ignores an initial session lookup that resolves after an auth event", async () => {
    const sessionLookup = deferred<{
      data: { session: { access_token: string } | null };
      error: null;
    }>();
    auth.getSession.mockReturnValue(sessionLookup.promise);
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ users: 4 }));
    render(<Admin />);

    await act(async () => {
      auth.listener?.("SIGNED_IN", { access_token: "new-admin-token" });
    });
    expect(
      await screen.findByRole("navigation", { name: "Admin sections" }),
    ).toBeTruthy();

    await act(async () => {
      sessionLookup.resolve({ data: { session: null }, error: null });
    });
    expect(
      screen.getByRole("navigation", { name: "Admin sections" }),
    ).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Welcome back" })).toBeNull();
  });

  it("ignores a stale forbidden response after a newer session is authorized", async () => {
    auth.token = "old-token";
    const oldRequest = deferred<Response>();
    vi.mocked(fetch)
      .mockReturnValueOnce(oldRequest.promise)
      .mockResolvedValueOnce(jsonResponse({ users: 8 }));
    render(<Admin />);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));

    await act(async () => {
      auth.listener?.("SIGNED_IN", { access_token: "new-admin-token" });
    });
    expect(
      await screen.findByRole("navigation", { name: "Admin sections" }),
    ).toBeTruthy();

    await act(async () => {
      oldRequest.resolve(jsonResponse({}, 403));
    });
    expect(
      screen.getByRole("navigation", { name: "Admin sections" }),
    ).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Access denied" })).toBeNull();
    expect(auth.signOut).not.toHaveBeenCalled();
  });

  it("ignores a pending authorization response after unmount", async () => {
    auth.token = "admin-token";
    const pendingRequest = deferred<Response>();
    vi.mocked(fetch).mockReturnValue(pendingRequest.promise);
    const view = render(<Admin />);
    await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    view.unmount();

    await act(async () => {
      pendingRequest.resolve(jsonResponse({}, 401));
    });
    expect(auth.signOut).not.toHaveBeenCalled();
  });

  it.each([401, 403])(
    "ignores a stale mutation response with status %s after the account changes",
    async (status) => {
      auth.token = "old-admin-token";
      const pendingMutation = deferred<Response>();
      vi.spyOn(window, "prompt").mockReturnValue("Renamed Station");
      vi.mocked(fetch).mockImplementation(async (input, init) => {
        if (init?.method === "PATCH") return pendingMutation.promise;
        return String(input).endsWith("/admin/stations")
          ? jsonResponse([{ id: "station-id", name: "Central Station" }])
          : jsonResponse({ users: 2 });
      });
      render(<Admin />);
      fireEvent.click(await screen.findByRole("button", { name: "Stations" }));
      fireEvent.click(await screen.findByText("Central Station"));
      fireEvent.click(screen.getByRole("button", { name: "Edit station" }));

      await act(async () => {
        auth.listener?.("SIGNED_IN", { access_token: "new-admin-token" });
      });
      expect(
        await screen.findByRole("navigation", { name: "Admin sections" }),
      ).toBeTruthy();

      await act(async () => {
        pendingMutation.resolve(jsonResponse({}, status));
      });
      expect(
        screen.getByRole("navigation", { name: "Admin sections" }),
      ).toBeTruthy();
      expect(screen.queryByRole("heading", { name: "Access denied" })).toBeNull();
      expect(auth.signOut).not.toHaveBeenCalled();
    },
  );

  it("opens a complete detail view from a list row", async () => {
    auth.token = "admin-token";
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      return url.endsWith("/admin/dashboard")
        ? jsonResponse({ users: 1 })
        : jsonResponse([
            {
              id: "12345678-abcd-efgh",
              name: "Central Station",
              city: "Auckland",
              created_at: "2026-08-09T12:00:00Z",
            },
          ]);
    });
    render(<Admin />);
    fireEvent.click(await screen.findByRole("button", { name: "Stations" }));
    fireEvent.click(await screen.findByText("Central Station"));
    expect(
      screen.getByRole("heading", { name: "Central Station" }),
    ).toBeTruthy();
    expect(screen.getByText("12345678-abcd-efgh")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /Back to Stations/ }),
    ).toBeTruthy();
  });

  it("shows a station name instead of its Google Place ID in the stations list", async () => {
    auth.token = "admin-token";
    vi.mocked(fetch).mockImplementation(async (input) =>
      String(input).endsWith("/admin/dashboard")
        ? jsonResponse({ users: 1 })
        : jsonResponse([
            {
              id: "station-id",
              google_place_id: "ChIJ-place-id",
              suburb: "Mount Eden",
              city: "Auckland",
              postal_code: "1024",
              latitude: "-36.878",
              timezone: "Pacific/Auckland",
              name: "Central Station",
            },
          ]),
    );
    render(<Admin />);
    fireEvent.click(await screen.findByRole("button", { name: "Stations" }));

    expect(await screen.findByText("Central Station")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeTruthy();
    expect(
      screen.queryByRole("columnheader", { name: "Google Place Id" }),
    ).toBeNull();
    expect(screen.queryByText("ChIJ-place-id")).toBeNull();

    fireEvent.click(screen.getByText("Central Station"));
    expect(screen.getByText("ChIJ-place-id")).toBeTruthy();
  });

  it("groups vehicle details and links to a summarized user", async () => {
    auth.token = "admin-token";
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/admin/dashboard")) return jsonResponse({ users: 1 });
      if (url.endsWith("/admin/users/user-id")) {
        return jsonResponse({
          id: "user-id",
          display_name: "Jamie Driver",
          country_code: "NZ",
          preferred_currency: "NZD",
        });
      }
      return jsonResponse([
        {
          id: "vehicle-id",
          user_id: "user-id",
          nickname: "Roadie",
          make: "Toyota",
          model: "Corolla",
          fuel_type: "PETROL_91",
          is_primary: true,
        },
      ]);
    });
    render(<Admin />);
    fireEvent.click(await screen.findByRole("button", { name: "Vehicles" }));
    fireEvent.click(await screen.findByText("Roadie"));

    expect(screen.getByRole("heading", { name: "Vehicle" })).toBeTruthy();
    expect(await screen.findByText("Jamie Driver")).toBeTruthy();
    expect(screen.queryByText("user-id")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "View user →" }));
    expect(screen.getByRole("heading", { name: "Jamie Driver" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Back to Users/ })).toBeTruthy();
  });

  it("links a station brand summary to the brand detail", async () => {
    auth.token = "admin-token";
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/admin/dashboard")) return jsonResponse({ users: 1 });
      if (url.endsWith("/admin/brands/brand-id")) {
        return jsonResponse({ id: "brand-id", name: "North Fuel", slug: "north-fuel" });
      }
      if (url.endsWith("/admin/brands")) {
        return jsonResponse([{ id: "brand-id", name: "North Fuel", slug: "north-fuel" }]);
      }
      return jsonResponse([{ id: "station-id", brand_id: "brand-id", name: "Harbour Station", city: "Auckland" }]);
    });
    render(<Admin />);
    fireEvent.click(await screen.findByRole("button", { name: "Stations" }));
    fireEvent.click(await screen.findByText("Harbour Station"));

    expect(await screen.findByText("North Fuel")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View brand →" }));
    expect(screen.getByRole("heading", { name: "North Fuel" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Brand" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Back to Brands/ })).toBeTruthy();
  });

  it("does not let a delayed related list replace a newer section load", async () => {
    auth.token = "admin-token";
    const relatedList = deferred<Response>();
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/admin/dashboard")) return jsonResponse({ users: 1 });
      if (url.endsWith("/admin/vehicles")) {
        return jsonResponse([{ id: "vehicle-id", user_id: "user-id", nickname: "Roadie", make: "Toyota", model: "Corolla" }]);
      }
      if (url.endsWith("/admin/users/user-id")) {
        return jsonResponse({ id: "user-id", display_name: "Jamie Driver" });
      }
      if (url.endsWith("/admin/users")) return relatedList.promise;
      if (url.endsWith("/admin/stations")) {
        return jsonResponse([{ id: "station-id", name: "Current Station", city: "Auckland" }]);
      }
      return jsonResponse([]);
    });
    render(<Admin />);
    fireEvent.click(await screen.findByRole("button", { name: "Vehicles" }));
    fireEvent.click(await screen.findByText("Roadie"));
    fireEvent.click(await screen.findByRole("button", { name: "View user →" }));
    fireEvent.click(screen.getByRole("button", { name: "Stations" }));
    expect(await screen.findByText("Current Station")).toBeTruthy();

    await act(async () => {
      relatedList.resolve(jsonResponse([{ id: "user-id", display_name: "Stale User" }]));
    });
    expect(screen.getByText("Current Station")).toBeTruthy();
    expect(screen.queryByText("Stale User")).toBeNull();
  });

  it("clears an old relation summary when the changed relationship fails", async () => {
    const relation: Relation = {
      field: "user_id",
      title: "User",
      target: "users",
      summaryFields: ["display_name"],
    };
    vi.mocked(fetch).mockImplementation(async (input) =>
      String(input).endsWith("/user-one")
        ? jsonResponse({ id: "user-one", display_name: "First User" })
        : jsonResponse({}, 404),
    );
    const view = render(
      <RelatedEntity apiBase="http://localhost:8000/api/v1" relation={relation} relatedId="user-one" token="admin-token" onOpenRelated={vi.fn()} />,
    );
    expect(await screen.findByText("First User")).toBeTruthy();

    view.rerender(
      <RelatedEntity apiBase="http://localhost:8000/api/v1" relation={relation} relatedId="user-two" token="admin-token" onOpenRelated={vi.fn()} />,
    );
    expect(screen.queryByText("First User")).toBeNull();
    await waitFor(() => expect(screen.getByText(/Related information is unavailable/)).toBeTruthy());
    expect(screen.queryByRole("button", { name: "View user →" })).toBeNull();
  });

  it("shows mutation failures while the detail view remains selected", async () => {
    auth.token = "admin-token";
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      if (init?.method === "PATCH") return jsonResponse({}, 500);
      return String(input).endsWith("/admin/dashboard")
        ? jsonResponse({ users: 1 })
        : jsonResponse([
            { id: "station-id", name: "Central Station", address_line: "1 Road", city: "Auckland", country_code: "NZ", latitude: "-36.8", longitude: "174.7", timezone: "Pacific/Auckland" },
          ]);
    });
    render(<Admin />);
    fireEvent.click(await screen.findByRole("button", { name: "Stations" }));
    fireEvent.click(await screen.findByText("Central Station"));
    fireEvent.click(screen.getByRole("button", { name: "Edit station" }));
    fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!);
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "failed on the server",
      ),
    );
    expect(
      screen.getByRole("heading", { name: "Central Station" }),
    ).toBeTruthy();
  });

  it("searches and imports all Google Places candidates at once", async () => {
    auth.token = "admin-token";
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/admin/dashboard")) return jsonResponse({ users: 1 });
      if (url.includes("/admin/stations/import?") && init?.method === "POST") return jsonResponse({ added: 2, updated: 1, already_existing: 3, invalid_results: 1, duplicate_provider_results: 1 });
      if (url.endsWith("/admin/brands")) return jsonResponse([{ id: "brand-1", name: "North Fuel", slug: "north-fuel" }]);
      if (url.endsWith("/admin/stations")) return jsonResponse([]);
      return jsonResponse([]);
    });
    render(<Admin />);
    fireEvent.click(await screen.findByRole("button", { name: "Stations" }));
    fireEvent.click(await screen.findByRole("button", { name: "Add station" }));
    fireEvent.change(screen.getByLabelText("Search Google Places"), { target: { value: "Harbour" } });
    fireEvent.click(screen.getByRole("button", { name: "Search and add all" }));
    expect((await screen.findByRole("status")).textContent).toContain("2 added, 1 updated, 3 already existed, 1 invalid skipped, 1 duplicate provider result skipped.");
    expect(vi.mocked(fetch).mock.calls.some(([input,init]) => String(input).includes("/admin/stations/import?q=Harbour") && init?.method === "POST")).toBe(true);
  });

  it("keeps the newest Google Places search results when responses arrive out of order", async () => {
    auth.token = "admin-token";const first=deferred<Response>();const second=deferred<Response>();
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url=String(input);
      if(url.endsWith("/admin/dashboard"))return jsonResponse({users:1});
      if(url.endsWith("/admin/stations")||url.endsWith("/admin/brands"))return jsonResponse([]);
      if(url.includes("q=First"))return first.promise;
      if(url.includes("q=Second"))return second.promise;
      return jsonResponse([]);
    });
    render(<Admin />);fireEvent.click(await screen.findByRole("button",{name:"Stations"}));fireEvent.click(await screen.findByRole("button",{name:"Add station"}));
    let searchInput=screen.getByLabelText("Search Google Places");let searchForm=searchInput.closest("form")!;
    fireEvent.change(searchInput,{target:{value:"First"}});fireEvent.submit(searchForm);
    fireEvent.click(screen.getByRole("button",{name:"Cancel"}));fireEvent.click(screen.getByRole("button",{name:"Add station"}));
    searchInput=screen.getByLabelText("Search Google Places");searchForm=searchInput.closest("form")!;fireEvent.change(searchInput,{target:{value:"Second"}});fireEvent.submit(searchForm);
    await act(async()=>second.resolve(jsonResponse({added:2,updated:0,already_existing:0,skipped_invalid:0})));
    expect((await screen.findByRole("status")).textContent).toContain("2 added");
    await act(async()=>first.resolve(jsonResponse({added:9,updated:0,already_existing:0,skipped_invalid:0})));
    expect(screen.getByRole("status").textContent).toContain("2 added");expect(screen.getByRole("status").textContent).not.toContain("9 added");
  });

  it("ignores a rapid repeated bulk import submission while one is in flight", async () => {
    auth.token = "admin-token";const pending=deferred<Response>();
    vi.mocked(fetch).mockImplementation(async (input,init) => {
      const url=String(input);
      if(url.endsWith("/admin/dashboard"))return jsonResponse({users:1});
      if(url.endsWith("/admin/stations")||url.endsWith("/admin/brands"))return jsonResponse([]);
      if(url.includes("/admin/stations/import?")&&init?.method==="POST")return pending.promise;
      return jsonResponse([]);
    });
    render(<Admin />);fireEvent.click(await screen.findByRole("button",{name:"Stations"}));fireEvent.click(await screen.findByRole("button",{name:"Add station"}));
    const searchInput=screen.getByLabelText("Search Google Places");const searchForm=searchInput.closest("form")!;
    fireEvent.change(searchInput,{target:{value:"Harbour"}});fireEvent.submit(searchForm);fireEvent.submit(searchForm);
    expect(vi.mocked(fetch).mock.calls.filter(([input,init])=>String(input).includes("/admin/stations/import?")&&init?.method==="POST")).toHaveLength(1);
    await act(async()=>pending.resolve(jsonResponse({added:1,updated:0,already_existing:0,invalid_results:0,duplicate_provider_results:0})));
    expect((await screen.findByRole("status")).textContent).toContain("1 added");
  });

  it("creates and edits brands with structured forms", async () => {
    auth.token = "admin-token";
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url=String(input);
      if (url.endsWith("/admin/dashboard")) return jsonResponse({ users: 1 });
      if (url.endsWith("/admin/brands") && init?.method === "POST") return jsonResponse({ id: "brand-1", ...JSON.parse(String(init.body)) },201);
      if (url.endsWith("/admin/brands/brand-1") && init?.method === "PATCH") return jsonResponse({ id: "brand-1", ...JSON.parse(String(init.body)) });
      if (url.endsWith("/admin/brands")) return jsonResponse([]);
      return jsonResponse([]);
    });
    render(<Admin />);fireEvent.click(await screen.findByRole("button", { name: "Brands" }));fireEvent.click(await screen.findByRole("button", { name: "Add brand" }));
    fireEvent.change(screen.getByLabelText("Name"),{target:{value:"North Fuel"}});fireEvent.change(screen.getByLabelText("Slug"),{target:{value:"north-fuel"}});fireEvent.click(screen.getByRole("button",{name:"Save"}));
    expect(await screen.findByRole("heading",{name:"North Fuel"})).toBeTruthy();fireEvent.click(screen.getByRole("button",{name:"Edit brand"}));
    fireEvent.change(screen.getByLabelText("Name"),{target:{value:"Northern Fuel"}});fireEvent.click(screen.getByRole("button",{name:"Save"}));
    expect(await screen.findByRole("heading",{name:"Northern Fuel"})).toBeTruthy();
  });

  it("shows and downloads an authenticated image for a failed receipt", async () => {
    auth.token = "admin-token";
    const createObjectURL = vi.fn(() => "blob:receipt-image");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/admin/dashboard")) return jsonResponse({ users: 1 });
      if (url.endsWith("/admin/receipt-failures")) return jsonResponse([{ id: "receipt-id", media_asset_id: "media-id", processing_status: "FAILED" }]);
      if (url.endsWith("/admin/media/media-id/content")) return { ok: true, blob: async () => new Blob(["image"], { type: "image/jpeg" }) } as Response;
      return jsonResponse({}, 404);
    });
    const view = render(<Admin />);
    fireEvent.click(await screen.findByRole("button", { name: "Receipt-Failures" }));
    fireEvent.click(await screen.findByText("FAILED"));
    expect((await screen.findByRole("img", { name: "Uploaded receipt" })).getAttribute("src")).toBe("blob:receipt-image");
    expect(screen.getByRole("link", { name: "Download image" }).getAttribute("download")).toBe("receipt-media-id");
    expect(vi.mocked(fetch).mock.calls.some(([input, init]) => String(input).endsWith("/admin/media/media-id/content") && new Headers(init?.headers).get("authorization") === "Bearer admin-token")).toBe(true);
    view.unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:receipt-image");
  });
});
