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

  it("shows mutation failures while the detail view remains selected", async () => {
    auth.token = "admin-token";
    vi.spyOn(window, "prompt").mockReturnValue("Renamed Station");
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      if (init?.method === "PATCH") return jsonResponse({}, 500);
      return String(input).endsWith("/admin/dashboard")
        ? jsonResponse({ users: 1 })
        : jsonResponse([
            { id: "station-id", name: "Central Station", city: "Auckland" },
          ]);
    });
    render(<Admin />);
    fireEvent.click(await screen.findByRole("button", { name: "Stations" }));
    fireEvent.click(await screen.findByText("Central Station"));
    fireEvent.click(screen.getByRole("button", { name: "Edit station" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "failed on the server",
      ),
    );
    expect(
      screen.getByRole("heading", { name: "Central Station" }),
    ).toBeTruthy();
  });
});
