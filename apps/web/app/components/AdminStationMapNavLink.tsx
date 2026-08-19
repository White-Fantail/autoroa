"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function AdminStationMapNavLink() {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (pathname !== "/admin") return;

    let created: HTMLButtonElement | null = null;
    let observer: MutationObserver | null = null;

    const install = () => {
      if (created?.isConnected) return true;

      const navigation = document.querySelector<HTMLElement>(".admin-sidebar nav");
      if (!navigation) return false;

      const stationButton = Array.from(
        navigation.querySelectorAll<HTMLButtonElement>("button"),
      ).find((button) => button.textContent?.trim() === "Stations");
      if (!stationButton) return false;

      created = document.createElement("button");
      created.type = "button";
      created.dataset.adminStationMapLink = "true";
      created.textContent = "Map & duplicates";
      created.setAttribute("aria-label", "Station map and duplicates");
      Object.assign(created.style, {
        marginTop: "-3px",
        marginBottom: "5px",
        paddingLeft: "28px",
        fontSize: "13px",
        fontWeight: "600",
      });
      created.addEventListener("click", () => router.push("/admin/stations/map"));
      stationButton.insertAdjacentElement("afterend", created);
      return true;
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
      created?.remove();
    };
  }, [pathname, router]);

  return null;
}
