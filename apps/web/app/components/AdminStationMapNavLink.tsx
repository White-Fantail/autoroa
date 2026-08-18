"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

export default function AdminStationMapNavLink() {
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (window.location.pathname !== "/admin") return;
    let created: HTMLElement | null = null;

    const install = () => {
      if (created?.isConnected) return true;
      const navigation = document.querySelector<HTMLElement>(".admin-sidebar nav");
      if (!navigation) return false;
      const stationButton = Array.from(
        navigation.querySelectorAll<HTMLButtonElement>("button"),
      ).find((button) => button.textContent?.trim() === "Stations");
      if (!stationButton) return false;
      created = document.createElement("span");
      created.dataset.adminStationMapLink = "true";
      stationButton.insertAdjacentElement("afterend", created);
      setHost(created);
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

  if (!host) return null;
  return createPortal(
    <a
      href="/admin/stations/map"
      style={{
        display: "block",
        margin: "-2px 10px 8px 22px",
        padding: "7px 10px",
        borderRadius: 8,
        color: "inherit",
        fontSize: 12,
        lineHeight: 1.2,
        opacity: 0.82,
        textDecoration: "none",
      }}
    >
      Map & duplicates
    </a>,
    host,
  );
}
