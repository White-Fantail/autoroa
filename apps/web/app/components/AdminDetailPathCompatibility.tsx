"use client";

import { createClient } from "@supabase/supabase-js";
import { useEffect, useRef, useState } from "react";
import {
  adminDetailIdFromLocation,
  adminSectionFromLocation,
  pushAdminDetail,
  replaceAdminSection,
} from "../admin/admin-routing";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const standardSections = new Set([
  "stations",
  "brands",
  "observations",
  "receipt-failures",
  "unmatched-stations",
  "users",
  "vehicles",
  "fill-ups",
]);
const routableSections = new Set([...standardSections, "ocr-queue", "station-reports"]);

type Row = Record<string, unknown>;
type CacheEntry = { at: number; rows: Row[] };

function currentTableRows(section: string) {
  if (section === "ocr-queue") {
    return Array.from(document.querySelectorAll<HTMLTableRowElement>(".admin-ocr-table tbody tr"));
  }
  if (section === "station-reports") {
    return Array.from(document.querySelectorAll<HTMLTableRowElement>("[data-admin-station-reports-host] .admin-table tbody tr"));
  }
  return Array.from(document.querySelectorAll<HTMLTableRowElement>(".admin-shell > .admin-content .admin-list-card .admin-table tbody tr"));
}

function detailIsVisible(section: string) {
  if (section === "ocr-queue") return Boolean(document.querySelector(".admin-ocr-review"));
  if (section === "station-reports") {
    return Boolean(document.querySelector("[data-admin-station-reports-host] .admin-detail-header"));
  }
  return Boolean(document.querySelector(".admin-shell > .admin-content .admin-detail-header"));
}

function selectedCoreId() {
  const sections = Array.from(
    document.querySelectorAll<HTMLElement>(".admin-shell > .admin-content .admin-detail-section"),
  );
  for (const section of sections) {
    const terms = Array.from(section.querySelectorAll<HTMLElement>("dt"));
    const idTerm = terms.find((term) => term.textContent?.trim().toLowerCase() === "id");
    const value = idTerm?.nextElementSibling?.textContent?.trim();
    if (value) return value;
  }
  return null;
}

function filteredRowsForDom(section: string, rows: Row[]) {
  if (section === "station-reports") {
    const host = document.querySelector<HTMLElement>("[data-admin-station-reports-host]");
    const selectedFilter = Array.from(host?.querySelectorAll<HTMLButtonElement>("button") ?? []).find(
      (button) =>
        button.classList.contains("admin-primary") &&
        ["Open", "Closed", "All"].includes(button.textContent?.trim() ?? ""),
    )?.textContent?.trim().toUpperCase();
    if (!selectedFilter || selectedFilter === "ALL") return rows;
    return rows.filter((row) => String(row.status ?? "").toUpperCase() === selectedFilter);
  }

  if (standardSections.has(section)) {
    const query = document
      .querySelector<HTMLInputElement>(".admin-shell > .admin-content .admin-list-toolbar input")
      ?.value.trim()
      .toLowerCase();
    if (query) return rows.filter((row) => JSON.stringify(row).toLowerCase().includes(query));
  }

  return rows;
}

function chooseStationReportFilter(detailId: string, rows: Row[]) {
  const report = rows.find((row) => String(row.id ?? "") === detailId);
  if (!report) return false;
  const status = String(report.status ?? "").toUpperCase();
  if (status !== "OPEN" && status !== "CLOSED") return false;
  const host = document.querySelector<HTMLElement>("[data-admin-station-reports-host]");
  const button = Array.from(host?.querySelectorAll<HTMLButtonElement>("button") ?? []).find(
    (item) => item.textContent?.trim().toUpperCase() === status,
  );
  if (!button || button.classList.contains("admin-primary")) return false;
  button.click();
  return true;
}

function specialBackButton(section: string) {
  if (section === "ocr-queue") {
    return document.querySelector<HTMLButtonElement>(".admin-ocr-review .admin-back");
  }
  if (section === "station-reports") {
    return document.querySelector<HTMLButtonElement>("[data-admin-station-reports-host] .admin-back");
  }
  return null;
}

export default function AdminDetailPathCompatibility() {
  const [token, setToken] = useState("");
  const cache = useRef(new Map<string, CacheEntry>());
  const syncing = useRef(false);
  const replaying = useRef(false);
  const timer = useRef<number | null>(null);
  const popNavigating = useRef(false);
  const popTimer = useRef<number | null>(null);
  const [authClient] = useState(() =>
    createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost",
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "development-placeholder",
    ),
  );

  useEffect(() => {
    void authClient.auth.getSession().then(({ data }) => setToken(data.session?.access_token ?? ""));
    const { data } = authClient.auth.onAuthStateChange((_, session) => {
      cache.current.clear();
      setToken(session?.access_token ?? "");
    });
    return () => data.subscription.unsubscribe();
  }, [authClient]);

  useEffect(() => {
    if (!token) return;
    let stopped = false;

    const loadRows = async (section: string) => {
      const cached = cache.current.get(section);
      if (cached && Date.now() - cached.at < 5000) return cached.rows;
      const path =
        section === "ocr-queue"
          ? "/ocr-jobs?kind=PRICE_BOARD&limit=20"
          : `/admin/${section}`;
      const response = await fetch(`${api}${path}`, {
        headers: { authorization: `Bearer ${token}` },
      });
      if (!response.ok) return [];
      const payload = await response.json();
      const rows = Array.isArray(payload) ? payload : [];
      cache.current.set(section, { at: Date.now(), rows });
      return rows;
    };

    const sync = async () => {
      if (stopped || syncing.current) return;
      const section = adminSectionFromLocation();
      if (!routableSections.has(section)) return;
      const detailId = adminDetailIdFromLocation(section);

      if (detailIsVisible(section)) {
        if (!detailId) {
          if (section === "ocr-queue" || section === "station-reports") {
            if (popNavigating.current) specialBackButton(section)?.click();
          } else if (!popNavigating.current) {
            const id = selectedCoreId();
            if (id) pushAdminDetail(section, id);
          }
        }
        return;
      }

      syncing.current = true;
      try {
        const records = await loadRows(section);
        if (stopped) return;

        if (section === "station-reports" && detailId) {
          const visibleRecords = filteredRowsForDom(section, records);
          if (!visibleRecords.some((row) => String(row.id ?? "") === detailId)) {
            if (chooseStationReportFilter(detailId, records)) return;
          }
        }

        const visibleRecords = filteredRowsForDom(section, records);
        const domRows = currentTableRows(section);
        domRows.forEach((row, index) => {
          const id = visibleRecords[index]?.id;
          if (id != null) row.dataset.adminRecordId = String(id);
          else delete row.dataset.adminRecordId;
        });

        if (detailId) {
          const target = domRows.find((row) => row.dataset.adminRecordId === detailId);
          if (target && !detailIsVisible(section)) target.click();
        }
      } catch {
        // The native admin screen remains usable if URL synchronization cannot load metadata.
      } finally {
        syncing.current = false;
      }
    };

    const scheduleSync = () => {
      if (timer.current != null) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void sync(), 30);
    };

    const rowForTarget = (target: EventTarget | null) => {
      if (!(target instanceof Element)) return null;
      const row = target.closest<HTMLTableRowElement>("tr");
      if (!row) return null;
      const section = adminSectionFromLocation();
      if (!routableSections.has(section)) return null;
      const domRows = currentTableRows(section);
      const index = domRows.indexOf(row);
      if (index < 0) return null;
      return { row, section, index };
    };

    const resolveRowId = async (row: HTMLTableRowElement, section: string, index: number) => {
      let id = row.dataset.adminRecordId;
      if (id) return id;
      try {
        const records = filteredRowsForDom(section, await loadRows(section));
        const recordId = records[index]?.id;
        if (recordId == null) return null;
        id = String(recordId);
        row.dataset.adminRecordId = id;
        return id;
      } catch {
        return null;
      }
    };

    const pushRowUrl = (section: string, id: string) => {
      if (adminDetailIdFromLocation(section) !== id) pushAdminDetail(section, id);
    };

    const interceptUnmappedRow = (
      event: MouseEvent | KeyboardEvent,
      row: HTMLTableRowElement,
      section: string,
      index: number,
    ) => {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      void resolveRowId(row, section, index).then((id) => {
        if (stopped) return;
        if (id) pushRowUrl(section, id);
        replaying.current = true;
        try {
          row.click();
        } finally {
          replaying.current = false;
        }
      });
    };

    const onClick = (event: MouseEvent) => {
      if (replaying.current) return;
      const target = event.target;
      if (target instanceof Element) {
        const section = adminSectionFromLocation();
        const detailId = adminDetailIdFromLocation(section);
        if (detailId) {
          const button = target.closest<HTMLButtonElement>("button");
          const label = button?.textContent?.trim().toLowerCase() ?? "";
          if (
            button?.classList.contains("admin-back") ||
            label === "back to queue" ||
            label === "back to station reports"
          ) {
            replaceAdminSection(section);
            cache.current.delete(section);
            return;
          }
        }
      }

      const match = rowForTarget(target);
      if (!match) return;
      const { row, section, index } = match;
      const id = row.dataset.adminRecordId;
      if (id) {
        pushRowUrl(section, id);
        return;
      }
      interceptUnmappedRow(event, row, section, index);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (replaying.current || (event.key !== "Enter" && event.key !== " ")) return;
      const match = rowForTarget(event.target);
      if (!match) return;
      const { row, section, index } = match;
      const id = row.dataset.adminRecordId;
      if (id) {
        pushRowUrl(section, id);
        return;
      }
      interceptUnmappedRow(event, row, section, index);
    };

    const onPopState = () => {
      popNavigating.current = true;
      cache.current.delete(adminSectionFromLocation());
      if (popTimer.current != null) window.clearTimeout(popTimer.current);
      popTimer.current = window.setTimeout(() => {
        popNavigating.current = false;
        scheduleSync();
      }, 150);
      scheduleSync();
    };

    const observer = new MutationObserver(scheduleSync);
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("click", onClick, true);
    document.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("popstate", onPopState);
    scheduleSync();

    return () => {
      stopped = true;
      observer.disconnect();
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("popstate", onPopState);
      if (timer.current != null) window.clearTimeout(timer.current);
      if (popTimer.current != null) window.clearTimeout(popTimer.current);
    };
  }, [token]);

  return null;
}
