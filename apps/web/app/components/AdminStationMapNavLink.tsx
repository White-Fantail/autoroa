"use client";

import { useEffect } from "react";

export default function AdminStationMapNavLink() {
  useEffect(() => {
    if (window.location.pathname !== "/admin") return;
    let created: HTMLAnchorElement | null = null;

    const install = () => {
      if (created?.isConnected) return true;
      const navigation = document.querySelector<HTMLElement>(".admin-sidebar nav");
      if (!navigation) return false;
      const stationButton = Array.from(
        navigation.querySelectorAll<HTMLButtonElement>("button"),
      ).find((button) => button.textContent?.trim() === "Stations");
      if (!stationButton) return false;
      created = document.createElement("a");
      created.dataset.adminStationMapLink = "true";
      created.href = "/admin/stations/map";
      created.textContent = "Map & duplicates";
      Object.assign(created.style, {
        display: "block",
        margin: "-2px 10px 8px 22px",
        padding: "7px 10px",
        borderRadius: "8px",
        color: "inherit",
        fontSize: "12px",
        lineHeight: "1.2",
        opacity: "0.82",
        textDecoration: "none",
      });
      stationButton.insertAdjacentElement("afterend", created);
      return true;
    };

    if (!install()) {
      const observer = new MutationObserver(() => {
        if (install()) observer.disconnect();
      });
      observer.observe(document.body, { childList: true, subtree: true });
      return () => {
        observer.disconnect();
        created?.remove();
      };
    }

    return () => created?.remove();
  }, []);

  return null;
}
