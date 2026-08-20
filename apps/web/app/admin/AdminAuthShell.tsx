"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createClient } from "@supabase/supabase-js";
import { FormEvent, ReactNode, createContext, useContext, useEffect, useMemo, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

const adminSections = [
  ["dashboard", "Dashboard"],
  ["ocr-queue", "OCR Queue"],
  ["station-reports", "Station Reports"],
  ["stations", "Stations"],
  ["brands", "Brands"],
  ["observations", "Observations"],
  ["receipt-failures", "Receipt-Failures"],
  ["unmatched-stations", "Unmatched-Stations"],
  ["users", "Users"],
  ["vehicles", "Vehicles"],
  ["fill-ups", "Fill-Ups"],
  ["achievements", "Achievements"],
] as const;

type AdminAuthValue = { token: string; api: string };
const AdminAuthContext = createContext<AdminAuthValue | null>(null);

export function useAdminAuth() {
  const value = useContext(AdminAuthContext);
  if (!value) throw new Error("useAdminAuth must be used inside AdminAuthShell");
  return value;
}

export default function AdminAuthShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [token, setToken] = useState("");
  const [status, setStatus] = useState<"checking" | "signed-out" | "checking-role" | "authorized" | "forbidden" | "error">("checking");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [authClient] = useState(() => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost",
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "development-placeholder",
  ));

  useEffect(() => {
    let active = true;
    void authClient.auth.getSession().then(({ data, error: sessionError }) => {
      if (!active) return;
      if (sessionError) {
        setError("We could not verify your session. Please try again.");
        setStatus("error");
        return;
      }
      const next = data.session?.access_token ?? "";
      setToken(next);
      setStatus(next ? "checking-role" : "signed-out");
    });
    const { data } = authClient.auth.onAuthStateChange((_, session) => {
      if (!active) return;
      const next = session?.access_token ?? "";
      setToken(next);
      setStatus(next ? "checking-role" : "signed-out");
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, [authClient]);

  useEffect(() => {
    if (!token || status !== "checking-role") return;
    let active = true;
    void fetch(`${api}/admin/dashboard`, { headers: { authorization: `Bearer ${token}` } })
      .then((response) => {
        if (!active) return;
        if (response.status === 401) {
          void authClient.auth.signOut();
          return;
        }
        if (response.status === 403) {
          setStatus("forbidden");
          return;
        }
        if (!response.ok) throw new Error();
        setStatus("authorized");
        setError("");
      })
      .catch(() => {
        if (!active) return;
        setError("The administrator service is temporarily unavailable.");
        setStatus("error");
      });
    return () => { active = false; };
  }, [authClient, status, token]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setError("");
    setStatus("checking-role");
    const { data, error: signInError } = await authClient.auth.signInWithPassword({ email, password });
    if (signInError || !data.session) {
      setError("Administrator sign-in failed. Check your email and password.");
      setStatus("signed-out");
      return;
    }
    setToken(data.session.access_token);
    setPassword("");
  }

  const contextValue = useMemo(() => ({ token, api }), [token]);

  if (status === "checking" || status === "checking-role") {
    return <main className="admin-login-shell"><section className="admin-login-card admin-status-card"><div className="admin-brand">autoroa</div><p className="admin-kicker">Administration</p><h1>Checking access</h1><p className="admin-login-copy">We are verifying your administrator permissions.</p><div className="admin-status-progress" aria-hidden="true" /></section></main>;
  }

  if (status === "signed-out") {
    return <main className="admin-login-shell"><form className="admin-login-card" onSubmit={signIn}><div className="admin-brand">autoroa</div><p className="admin-kicker">Administration</p><h1>Welcome back</h1><p className="admin-login-copy">Sign in with your administrator account to continue.</p><label>Email<input autoComplete="email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label><label>Password<input autoComplete="current-password" type="password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>{error && <p className="admin-alert" role="alert">{error}</p>}<button className="admin-primary" type="submit">Sign in</button></form></main>;
  }

  if (status === "forbidden" || status === "error") {
    return <main className="admin-login-shell"><section className="admin-login-card admin-status-card"><div className="admin-brand">autoroa</div><p className="admin-kicker">Administration</p><h1>{status === "forbidden" ? "Access denied" : "Unable to verify access"}</h1><p className="admin-login-copy" role="alert">{status === "forbidden" ? "Your account does not have permission to access Autoroa administration." : error}</p><button className="admin-primary" type="button" onClick={() => void authClient.auth.signOut()}>Sign in with another account</button></section></main>;
  }

  return <AdminAuthContext.Provider value={contextValue}><main className="admin-shell"><aside className="admin-sidebar"><div className="admin-brand admin-brand-light">autoroa</div><nav aria-label="Admin sections">{adminSections.map(([slug, label]) => {
    const href = `/admin/${slug}`;
    const active = pathname === href || pathname.startsWith(`${href}/`);
    return <Link className={active ? "active" : ""} href={href} key={slug}>{label}</Link>;
  })}</nav><button className="admin-signout" type="button" onClick={() => void authClient.auth.signOut()}>Sign out</button></aside><section className="admin-content">{children}</section></main></AdminAuthContext.Provider>;
}
