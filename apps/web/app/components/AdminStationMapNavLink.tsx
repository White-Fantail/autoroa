"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function AdminStationMapNavLink() {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (pathname !== "/admin") return;

    let mapButton: HTMLButtonElement | null = null;
    let reportsButton: HTMLButtonElement | null = null;
    let observer: MutationObserver | null = null;

    const install = () => {
      const navigation = document.querySelector<HTMLElement>(".admin-sidebar nav");
      if (!navigation) return false;

      if (!reportsButton?.isConnected) {
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

      if (!mapButton?.isConnected) {
        const stationButton = Array.from(
          navigation.querySelectorAll<HTMLButtonElement>("button"),
        ).find((button) => button.textContent?.trim() === "Stations");
        if (stationButton) {
          mapButton = document.createElement("button");
          mapButton.type = "button";
          mapButton.dataset.adminStationMapLink = "true";
          mapButton.textContent = "Map & duplicates";
          mapButton.setAttribute("aria-label", "Station map and duplicates");
          Object.assign(mapButton.style, {
            marginTop: "-3px",
            marginBottom: "5px",
            paddingLeft: "28px",
            fontSize: "13px",
            fontWeight: "600",
          });
          mapButton.addEventListener("click", () => router.push("/admin/stations/map"));
          stationButton.insertAdjacentElement("afterend", mapButton);
        }
      }

      return Boolean(reportsButton?.isConnected && mapButton?.isConnected);
    };

    if (!install()) {
      observer = new MutationObserver(() => {
        if (install()) {
          observer?.disconnect();
          observer = null;
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }

    return () => {
      observer?.disconnect();
      reportsButton?.remove();
      mapButton?.remove();
    };
  }, [pathname, router]);

  return null;
}
