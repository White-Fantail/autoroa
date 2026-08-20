"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createClient } from "@supabase/supabase-js";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { FormEvent } from "react";

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

let sharedAdminToken = "";
const tokenListeners = new Set<() => void>();
function publishAdminToken(token: string) {
  if (sharedAdminToken === token) return;
  sharedAdminToken = token;
  tokenListeners.forEach((listener) => listener());
}

export function useAdminAuth() {
  const token = useSyncExternalStore(
    (listener) => {
      tokenListeners.add(listener);
      return () => tokenListeners.delete(listener);
    },
    () => sharedAdminToken,
    () => "",
  );
  return { token, api };
}

export default function AdminAuthShell({ children }: { children: any }) {
  const pathname = usePathname();
  const tokenRef = useRef("");
  const verificationSequence = useRef(0);
  const [status, setStatus] = useState<"checking" | "signed-out" | "checking-role" | "authorized" | "forbidden" | "error">("checking");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [authClient] = useState(() => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost",
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "development-placeholder",
  ));

  async function applySession(accessToken: string) {
    const requestId = ++verificationSequence.current;
    tokenRef.current = accessToken;
    publishAdminToken(accessToken);
    setError("");

    if (!accessToken) {
      setStatus("signed-out");
      return;
    }

    setStatus("checking-role");
    try {
      const response = await fetch(`${api}/admin/dashboard`, {
        headers: { authorization: `Bearer ${accessToken}` },
      });
      if (requestId !== verificationSequence.current) return;
      if (response.status === 401) {
        await authClient.auth.signOut();
        return;
      }
      if (response.status === 403) {
        setStatus("forbidden");
        return;
      }
      if (!response.ok) throw new Error();
      setStatus("authorized");
    } catch {
      if (requestId !== verificationSequence.current) return;
      setError("The administrator service is temporarily unavailable.");
      setStatus("error");
    }
  }

  useEffect(() => {
    let active = true;
    void authClient.auth.getSession().then(({ data, error: sessionError }) => {
      if (!active) return;
      if (sessionError) {
        setError("We could not verify your session. Please try again.");
        setStatus("error");
        return;
      }
      void applySession(data.session?.access_token ?? "");
    });
    const { data } = authClient.auth.onAuthStateChange((_, session) => {
      if (!active) return;
      const next = session?.access_token ?? "";
      if (next && next === tokenRef.current) return;
      void applySession(next);
    });
    return () => {
      active = false;
      verificationSequence.current += 1;
      data.subscription.unsubscribe();
    };
  }, [authClient]);

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
    setPassword("");
    await applySession(data.session.access_token);
  }

  if (status === "checking" || status === "checking-role") {
    return <main className="admin-login-shell"><section className="admin-login-card admin-status-card"><div className="admin-brand">autoroa</div><p className="admin-kicker">Administration</p><h1>Checking access</h1><p className="admin-login-copy">We are verifying your administrator permissions.</p><div className="admin-status-progress" aria-hidden="true" /></section></main>;
  }

  if (status === "signed-out") {
    return <main className="admin-login-shell"><form className="admin-login-card" onSubmit={signIn}><div className="admin-brand">autoroa</div><p className="admin-kicker">Administration</p><h1>Welcome back</h1><p className="admin-login-copy">Sign in with your administrator account to continue.</p><label>Email<input autoComplete="email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label><label>Password<input autoComplete="current-password" type="password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>{error && <p className="admin-alert" role="alert">{error}</p>}<button className="admin-primary" type="submit">Sign in</button></form></main>;
  }

  if (status === "forbidden" || status === "error") {
    return <main className="admin-login-shell"><section className="admin-login-card admin-status-card"><div className="admin-brand">autoroa</div><p className="admin-kicker">Administration</p><h1>{status === "forbidden" ? "Access denied" : "Unable to verify access"}</h1><p className="admin-login-copy" role="alert">{status === "forbidden" ? "Your account does not have permission to access Autoroa administration." : error}</p><button className="admin-primary" type="button" onClick={() => void authClient.auth.signOut()}>Sign in with another account</button></section></main>;
  }

  return <main className="admin-shell"><aside className="admin-sidebar"><div className="admin-brand admin-brand-light">autoroa</div><nav aria-label="Admin sections">{adminSections.map(([slug, label]) => {
    const href = `/admin/${slug}`;
    const active = pathname === href || pathname.startsWith(`${href}/`);
    return <Link className={active ? "active" : ""} href={href} key={slug}>{label}</Link>;
  })}</nav><button className="admin-signout" type="button" onClick={() => void authClient.auth.signOut()}>Sign out</button></aside><section className="admin-content">{children}</section></main>;
}
