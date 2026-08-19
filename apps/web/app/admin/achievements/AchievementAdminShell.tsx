"use client";

import AchievementAdmin from "./AchievementAdmin";
import { supabaseBrowser } from "../../../lib/supabase";

const sections = [
  ["dashboard", "Dashboard"],
  ["ocr-queue", "OCR Queue"],
  ["stations", "Stations"],
  ["brands", "Brands"],
  ["observations", "Observations"],
  ["receipt-failures", "Receipt Failures"],
  ["unmatched-stations", "Unmatched Stations"],
  ["users", "Users"],
  ["vehicles", "Vehicles"],
  ["fill-ups", "Fill Ups"],
] as const;

export default function AchievementAdminShell() {
  const navigate = (section: string) => {
    window.location.assign(`/admin?section=${encodeURIComponent(section)}`);
  };

  const signOut = async () => {
    await supabaseBrowser().auth.signOut();
    window.location.assign("/admin");
  };

  return (
    <main className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand admin-brand-light">autoroa</div>
        <nav aria-label="Admin sections">
          {sections.map(([key, label]) => (
            <button key={key} type="button" onClick={() => navigate(key)}>
              {label}
            </button>
          ))}
          <button className="active" type="button" aria-current="page">
            Achievements
          </button>
        </nav>
        <button className="admin-signout" type="button" onClick={() => void signOut()}>
          Sign out
        </button>
      </aside>
      <section className="admin-content">
        <AchievementAdmin />
      </section>
    </main>
  );
}
