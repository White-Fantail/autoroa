"use client";

import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabaseBrowser } from "../../lib/supabase";

export default function LoginPanel() {
  const [session, setSession] = useState<Session | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const client = supabaseBrowser();
    void client.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: { subscription } } = client.auth.onAuthStateChange((_event, nextSession) => setSession(nextSession));
    return () => subscription.unsubscribe();
  }, []);

  async function signIn(provider: "google" | "apple" | "facebook") {
    setMessage("");
    const client = supabaseBrowser();
    const { error } = await client.auth.signInWithOAuth({ provider, options: { redirectTo: `${window.location.origin}/login` } });
    if (error) setMessage(error.message);
  }

  async function signOut() {
    const { error } = await supabaseBrowser().auth.signOut();
    if (error) setMessage(error.message);
  }

  if (session) {
    const label = session.user.user_metadata?.full_name || session.user.user_metadata?.name || session.user.email || "Autoroa member";
    return <div className="card" style={{maxWidth:520,margin:"0 auto",display:"grid",gap:16,padding:28}}>
      <div><p className="eyebrow">Signed in</p><h2 style={{marginBottom:6}}>{label}</h2><p style={{margin:0}}>You can now contribute fuel price-board photos and your submissions will be linked to your account.</p></div>
      <button className="button" type="button" onClick={()=>void signOut()}>Sign out</button>
      {message && <p role="alert" style={{margin:0}}>{message}</p>}
    </div>;
  }

  return <div className="card" style={{maxWidth:520,margin:"0 auto",display:"grid",gap:14,padding:28}}>
    <div><p className="eyebrow">Autoroa account</p><h2 style={{marginBottom:6}}>Sign in to contribute</h2><p style={{margin:0}}>Upload fuel price-board photos, track your contributions, and earn points as verified prices are updated.</p></div>
    <button className="button" type="button" onClick={()=>void signIn("google")}>Continue with Google</button>
    <button className="button secondary" type="button" onClick={()=>void signIn("apple")}>Continue with Apple</button>
    <button className="button secondary" type="button" onClick={()=>void signIn("facebook")}>Continue with Facebook</button>
    {message && <p role="alert" style={{margin:0}}>{message}</p>}
  </div>;
}
