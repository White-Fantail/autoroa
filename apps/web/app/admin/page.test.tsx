// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({
  token: "" as string,
  listener: undefined as
    ((event: string, session: unknown) => void) | undefined,
  signOut: vi.fn(),
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      getSession: vi.fn(async () => ({
        data: { session: auth.token ? { access_token: auth.token } : null },
      })),
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

describe("admin page", () => {
  beforeEach(() => {
    auth.token = "";
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

  it.each([401, 403])(
    "returns unauthorized sessions to sign-in on %s",
    async (status) => {
      auth.token = "invalid-token";
      vi.mocked(fetch).mockResolvedValue(jsonResponse({}, status));
      render(<Admin />);
      expect(
        await screen.findByRole("heading", { name: "Welcome back" }),
      ).toBeTruthy();
      expect(auth.signOut).toHaveBeenCalledOnce();
      expect(screen.getByRole("alert").textContent).toMatch(
        status === 401 ? /Sign in again/ : /Administrator role required/,
      );
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
