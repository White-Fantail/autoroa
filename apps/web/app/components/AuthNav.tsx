"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabaseBrowser } from "../../lib/supabase";

export default function AuthNav() {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    try {
      const client = supabaseBrowser();
      void client.auth.getSession().then(({ data }) => {
        if (active) {
          setSession(data.session);
          setReady(true);
        }
      });
      const { data: { subscription } } = client.auth.onAuthStateChange((_event, nextSession) => {
        if (active) {
          setSession(nextSession);
          setReady(true);
        }
      });
      return () => {
        active = false;
        subscription.unsubscribe();
      };
    } catch {
      setReady(true);
      return () => {
        active = false;
      };
    }
  }, []);

  if (!ready) return <span className="button nav-cta" aria-hidden="true">Account</span>;
  if (!session) return <Link className="button nav-cta" href="/login">Sign in</Link>;

  const label = session.user.user_metadata?.full_name || session.user.user_metadata?.name || session.user.email || "Account";
  return <Link className="button nav-cta" href="/login">{label}</Link>;
}
