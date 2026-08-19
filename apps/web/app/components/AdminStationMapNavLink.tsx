"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function AdminStationMapNavLink() {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (pathname !== "/admin") return;

    let reportsButton: HTMLButtonElement | null = null;
    let mapAction: HTMLButtonElement | null = null;

    const install = () => {
      const navigation = document.querySelector<HTMLElement>(".admin-sidebar nav");
      if (navigation && !reportsButton?.isConnected) {
        const ocrButton = Array.from(
          navigation.querySelectorAll<HTMLButtonElement>("button"),
        ).find((button) => button.textContent?.trim() === "OCR Queue");
        if (ocrButton) {
          reportsButton = document.createElement("button");
          reportsButton.type = "button";
          reportsButton.dataset.adminStationReportsLink = "true";
          reportsButton.textContent = "Station reports";
          reportsButton.setAttribute("aria-label", "Station reports");
          reportsButton.addEventListener("click", () => router.push("/admin/station-reports"));
          ocrButton.insertAdjacentElement("afterend", reportsButton);
        }
      }

      const currentSection = new URLSearchParams(window.location.search).get("section") ?? "dashboard";
      if (currentSection !== "stations") {
        mapAction?.remove();
        mapAction = null;
        return;
      }

      if (mapAction?.isConnected) return;
      const actions = document.querySelector<HTMLElement>(".admin-page-actions");
      if (!actions || actions.querySelector("[data-admin-station-map-action]")) return;

      mapAction = document.createElement("button");
      mapAction.type = "button";
      mapAction.dataset.adminStationMapAction = "true";
      mapAction.textContent = "Map & duplicates";
      mapAction.setAttribute("aria-label", "Station map and duplicates");
      Object.assign(mapAction.style, {
        padding: "10px 14px",
        border: "1px solid var(--border)",
        borderRadius: "10px",
        background: "white",
        color: "var(--ink)",
        font: "inherit",
        fontSize: "13px",
        fontWeight: "750",
        cursor: "pointer",
      });
      mapAction.addEventListener("click", () => router.push("/admin/stations/map"));
      actions.prepend(mapAction);
    };

    install();
    const observer = new MutationObserver(install);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("popstate", install);

    return () => {
      observer.disconnect();
      window.removeEventListener("popstate", install);
      reportsButton?.remove();
      mapAction?.remove();
    };
  }, [pathname, router]);

  return null;
}
