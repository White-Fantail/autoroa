"use client";

import { createClient } from "@supabase/supabase-js";
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

type ModerationStatus = "ACTIVE" | "SUSPENDED" | "BANNED";
type ModerationEvent = {
  id: string;
  previous_status: ModerationStatus;
  new_status: ModerationStatus;
  reason?: string | null;
  admin_user_id?: string | null;
  created_at: string;
};
type ModeratedUser = {
  id: string;
  display_name?: string | null;
  moderation_status: ModerationStatus;
  moderation_reason?: string | null;
  moderated_at?: string | null;
  moderation_history?: ModerationEvent[];
};

function currentUserDetail() {
  if (!window.location.pathname.startsWith("/admin")) return null;
  if (new URLSearchParams(window.location.search).get("section") !== "users") return null;
  const actions = document.querySelector<HTMLElement>(".admin-detail-actions");
  const details = document.querySelector<HTMLElement>(".admin-detail-sections");
  if (!actions || !details) return null;

  for (const item of document.querySelectorAll<HTMLElement>(".admin-detail-grid > div")) {
    const label = item.querySelector("dt")?.textContent?.trim().toLowerCase();
    const value = item.querySelector("dd")?.textContent?.trim() ?? "";
    if (
      label === "id" &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
    ) {
      return { id: value, actions, details };
    }
  }
  return null;
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function statusLabel(status: ModerationStatus) {
  if (status === "SUSPENDED") return "Suspended";
  if (status === "BANNED") return "Banned";
  return "Active";
}

export default function AdminUserModerationControls() {
  const [target, setTarget] = useState<ReturnType<typeof currentUserDetail>>(null);
  const [token, setToken] = useState("");
  const [user, setUser] = useState<ModeratedUser | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const authClient = useMemo(
    () =>
      createClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost",
        process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ??
          "development-placeholder",
      ),
    [],
  );

  useEffect(() => {
    let frame = 0;
    const inspect = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const next = currentUserDetail();
        setTarget((current) => {
          if (
            current?.id === next?.id &&
            current?.actions === next?.actions &&
            current?.details === next?.details
          )
            return current;
          return next;
        });
      });
    };
    inspect();
    const observer = new MutationObserver(inspect);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("popstate", inspect);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("popstate", inspect);
    };
  }, []);

  useEffect(() => {
    let active = true;
    void authClient.auth.getSession().then(({ data }) => {
      if (active) setToken(data.session?.access_token ?? "");
    });
    const { data } = authClient.auth.onAuthStateChange((_, session) => {
      if (active) setToken(session?.access_token ?? "");
    });
    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, [authClient]);

  useEffect(() => {
    if (!target?.id || !token) {
      setUser(null);
      return;
    }
    let active = true;
    setMessage("");
    setError("");
    void fetch(`${api}/admin/users/${encodeURIComponent(target.id)}`, {
      headers: { authorization: `Bearer ${token}` },
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("User moderation details could not be loaded.");
        return response.json();
      })
      .then((payload) => {
        if (active) setUser(payload);
      })
      .catch((caught) => {
        if (active)
          setError(
            caught instanceof Error
              ? caught.message
              : "User moderation details could not be loaded.",
          );
      });
    return () => {
      active = false;
    };
  }, [target?.id, token]);

  async function updateStatus(status: ModerationStatus) {
    if (!target?.id || !token || busy) return;
    let reason: string | null = null;
    if (status === "SUSPENDED" || status === "BANNED") {
      const entered = window.prompt(
        status === "SUSPENDED"
          ? "Why is this user being suspended?"
          : "Why is this user being permanently banned?",
      );
      if (entered === null) return;
      reason = entered.trim();
      if (!reason) {
        setError("A moderation reason is required.");
        return;
      }
    } else {
      if (!window.confirm("Reactivate this user and restore contribution access?"))
        return;
      reason = "Restriction lifted by administrator";
    }

    setBusy(true);
    setMessage("");
    setError("");
    try {
      const response = await fetch(
        `${api}/admin/users/${encodeURIComponent(target.id)}/moderation`,
        {
          method: "PATCH",
          headers: {
            authorization: `Bearer ${token}`,
            "content-type": "application/json",
          },
          body: JSON.stringify({ status, reason }),
        },
      );
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          payload?.error?.message ??
            payload?.detail ??
            "The moderation change was rejected.",
        );
      }
      setUser(payload);
      setMessage(
        status === "ACTIVE"
          ? "User reactivated."
          : status === "SUSPENDED"
            ? "User suspended."
            : "User banned.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "The moderation change failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!target || !user) return null;

  const controls = (
    <>
      <span
        className={`admin-status-badge admin-status-${user.moderation_status.toLowerCase()}`}
        title={user.moderation_reason ?? undefined}
      >
        {statusLabel(user.moderation_status)}
      </span>
      {user.moderation_status !== "ACTIVE" && (
        <button type="button" disabled={busy} onClick={() => void updateStatus("ACTIVE")}>
          {busy ? "Updating…" : "Reactivate"}
        </button>
      )}
      {user.moderation_status !== "SUSPENDED" && (
        <button type="button" disabled={busy} onClick={() => void updateStatus("SUSPENDED")}>
          Suspend user
        </button>
      )}
      {user.moderation_status !== "BANNED" && (
        <button
          type="button"
          disabled={busy}
          onClick={() => void updateStatus("BANNED")}
          style={{ borderColor: "#b42318", color: "#b42318" }}
        >
          Ban user
        </button>
      )}
    </>
  );

  const panel = (
    <section className="admin-detail-section" aria-label="User moderation">
      <header>
        <div>
          <h2>Moderation</h2>
          <p>Contribution restrictions and administrator action history.</p>
        </div>
      </header>
      {message && <p className="admin-success" role="status">{message}</p>}
      {error && <p className="admin-alert" role="alert">{error}</p>}
      <dl className="admin-detail-grid">
        <div>
          <dt>Status</dt>
          <dd>{statusLabel(user.moderation_status)}</dd>
        </div>
        <div>
          <dt>Reason</dt>
          <dd>{user.moderation_reason || "—"}</dd>
        </div>
        <div>
          <dt>Last moderated</dt>
          <dd>{formatDate(user.moderated_at)}</dd>
        </div>
      </dl>
      <div style={{ marginTop: 18 }}>
        <h3 style={{ marginBottom: 10 }}>History</h3>
        {(user.moderation_history ?? []).length === 0 ? (
          <p className="admin-empty">No moderation actions recorded.</p>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            {(user.moderation_history ?? []).map((event) => (
              <div
                key={event.id}
                style={{
                  borderTop: "1px solid var(--border)",
                  paddingTop: 10,
                }}
              >
                <strong>
                  {statusLabel(event.previous_status)} → {statusLabel(event.new_status)}
                </strong>
                <div className="admin-muted">
                  {formatDate(event.created_at)}
                  {event.reason ? ` · ${event.reason}` : ""}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );

  return (
    <>
      {createPortal(controls, target.actions)}
      {createPortal(panel, target.details)}
    </>
  );
}
