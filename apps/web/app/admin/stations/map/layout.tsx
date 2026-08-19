"use client";

import { createClient } from "@supabase/supabase-js";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const sections = [
  ["dashboard", "Dashboard"],
  ["ocr-queue", "OCR Queue"],
  ["station-reports", "Station reports"],
  ["stations", "Stations"],
  ["brands", "Brands"],
  ["observations", "Observations"],
  ["receipt-failures", "Receipt Failures"],
  ["unmatched-stations", "Unmatched Stations"],
  ["users", "Users"],
  ["vehicles", "Vehicles"],
  ["fill-ups", "Fill Ups"],
] as const;

export default function AdminStationMapLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [authClient] = useState(() =>
    createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost",
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "development-placeholder",
    ),
  );
  const [checking, setChecking] = useState(true);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    let active = true;
    void authClient.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSignedIn(Boolean(data.session?.access_token));
      setChecking(false);
    });
    return () => {
      active = false;
    };
  }, [authClient]);

  if (checking || !signedIn) return <>{children}</>;

  function navigate(section: (typeof sections)[number][0]) {
    if (section === "station-reports") {
      router.push("/admin/station-reports");
      return;
    }
    router.push(`/admin?section=${section}`);
  }

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand admin-brand-light">autoroa</div>
        <nav aria-label="Admin sections">
          {sections.map(([section, label]) => (
            <button
              className={section === "stations" ? "active" : ""}
              key={section}
              onClick={() => navigate(section)}
              type="button"
            >
              {label}
            </button>
          ))}
        </nav>
        <button
          className="admin-signout"
          onClick={() => {
            void authClient.auth.signOut().then(() => router.push("/admin"));
          }}
          type="button"
        >
          Sign out
        </button>
      </aside>
      <section className="admin-content" style={{ maxWidth: "none", padding: 0 }}>
        {children}
      </section>
    </div>
  );
}
