// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  pathname: "/admin/users",
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  redirect: vi.fn(),
  getSession: vi.fn(),
  signOut: vi.fn(),
  listener: undefined as ((event: string, session: unknown) => void) | undefined,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname,
  useRouter: () => ({ push: mocks.push, replace: mocks.replace, refresh: mocks.refresh }),
  redirect: mocks.redirect,
  notFound: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      getSession: mocks.getSession,
      onAuthStateChange: vi.fn((callback) => {
        mocks.listener = callback;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      }),
      signInWithPassword: vi.fn(async () => ({
        data: { session: { access_token: "signed-in-token" } },
        error: null,
      })),
      signOut: mocks.signOut,
    },
  }),
}));

import AdminIndexPage from "./page";
import AdminAuthShell from "./AdminAuthShell";
import AdminRoutePageClient from "./AdminRoutePageClient";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn(async () => body),
  } as unknown as Response;
}

describe("admin App Router", () => {
  beforeEach(() => {
    mocks.pathname = "/admin/users";
    mocks.push.mockReset();
    mocks.replace.mockReset();
    mocks.refresh.mockReset();
    mocks.redirect.mockReset();
    mocks.getSession.mockReset();
    mocks.getSession.mockResolvedValue({
      data: { session: { access_token: "admin-token" } },
      error: null,
    });
    mocks.signOut.mockReset();
    mocks.listener = undefined;
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("redirects /admin to the dashboard route", () => {
    AdminIndexPage();
    expect(mocks.redirect).toHaveBeenCalledWith("/admin/dashboard");
  });

  it("keeps authorization in the shared layout and renders route children", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ users: 3 }));
    render(<AdminAuthShell><div>Route content</div></AdminAuthShell>);

    expect(screen.getByText("Checking access")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("Route content")).toBeTruthy());
    expect(screen.getByRole("link", { name: "Users" }).className).toContain("active");
  });

  it("navigates table rows with the Next router", async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/admin/dashboard")) return jsonResponse({ users: 1 });
      if (url.includes("/admin/users")) {
        return jsonResponse([{ id: "user-1", display_name: "Alice", country_code: "NZ" }]);
      }
      return jsonResponse({}, 404);
    });

    render(
      <AdminAuthShell>
        <AdminRoutePageClient section="users" />
      </AdminAuthShell>,
    );

    await waitFor(() => expect(screen.getByText("Alice")).toBeTruthy());
    fireEvent.click(screen.getByText("Alice").closest("tr")!);
    expect(mocks.push).toHaveBeenCalledWith("/admin/users/user-1");
  });
});
