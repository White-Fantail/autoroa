"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabaseBrowser } from "../../lib/supabase";

const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const compactAccountStyle = { padding: "8px 11px", borderRadius: 9, fontSize: 14, lineHeight: 1.2 } as const;

export default function AuthNav() {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [profileName,setProfileName]=useState<string|null>(null);
  const [compact,setCompact]=useState(false);

  useEffect(() => {
    let active = true;
    const media=window.matchMedia("(max-width: 820px)");
    const syncCompact=()=>{if(active)setCompact(media.matches)};
    syncCompact();
    media.addEventListener("change",syncCompact);
    const loadProfile=async(current:Session|null)=>{if(!current){if(active)setProfileName(null);return}try{const response=await fetch(`${api}/me/profile`,{headers:{Authorization:`Bearer ${current.access_token}`}});if(response.ok){const body=await response.json();if(active)setProfileName(body.display_name||null)}}catch{}};
    try {
      const client = supabaseBrowser();
      void client.auth.getSession().then(({ data }) => {
        if (active) {
          setSession(data.session);
          setReady(true);
          void loadProfile(data.session);
        }
      });
      const { data: { subscription } } = client.auth.onAuthStateChange((_event, nextSession) => {
        if (active) {
          setSession(nextSession);
          setReady(true);
          void loadProfile(nextSession);
        }
      });
      const onProfileUpdated=(event:Event)=>{const detail=(event as CustomEvent<{display_name?:string}>).detail;if(detail?.display_name)setProfileName(detail.display_name)};
      window.addEventListener("autoroa:profile-updated",onProfileUpdated);
      return () => {
        active = false;
        subscription.unsubscribe();
        media.removeEventListener("change",syncCompact);
        window.removeEventListener("autoroa:profile-updated",onProfileUpdated);
      };
    } catch {
      setReady(true);
      return () => {
        active = false;
        media.removeEventListener("change",syncCompact);
      };
    }
  }, []);

  const compactStyle=compact?compactAccountStyle:undefined;
  if (!ready) return <span className="button" style={compactStyle} aria-hidden="true">Account</span>;
  if (!session) return <Link className="button" style={compactStyle} href="/login">Sign in</Link>;

  const fallback = session.user.user_metadata?.full_name || session.user.user_metadata?.name || session.user.email || "Account";
  return <Link className="button" style={compactStyle} href="/profile" aria-label={`Profile: ${profileName||fallback}`}>{compact?"Profile":profileName||fallback}</Link>;
}
