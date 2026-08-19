"use client";

import { useEffect } from "react";

function text(value: string | null | undefined) {
  return (value ?? "").trim();
}

export default function AdminStationReportStationLink() {
  useEffect(() => {
    let installed: HTMLButtonElement | null = null;
    let decoratedSection: HTMLElement | null = null;
    let opening = false;

    const install = () => {
      if (installed?.isConnected && decoratedSection?.isConnected) return;

      const host = document.querySelector<HTMLElement>("[data-admin-station-reports-host]");
      if (!host) return;
      const detailKicker = Array.from(host.querySelectorAll<HTMLElement>(".admin-kicker")).find(
        (element) => text(element.textContent) === "Station report detail",
      );
      if (!detailKicker) return;

      const stationSection = Array.from(host.querySelectorAll<HTMLElement>(".admin-detail-section")).find(
        (section) => text(section.querySelector("h2")?.textContent) === "Station",
      );
      const header = stationSection?.querySelector<HTMLElement>("header");
      const factsList = stationSection?.querySelector<HTMLDListElement>("dl");
      if (!stationSection || !header || !factsList) return;

      const facts = Array.from(factsList.querySelectorAll(":scope > div"));
      const readFact = (label: string) => {
        const row = facts.find((item) => text(item.querySelector("dt")?.textContent) === label);
        return text(row?.querySelector("dd")?.textContent);
      };
      const stationName = readFact("Name");
      const stationAddress = readFact("Address") || readFact("Address Line");
      const stationCity = readFact("City");
      if (!stationName) return;

      stationSection.classList.add("admin-related-section");
      decoratedSection = stationSection;

      header.replaceChildren();
      const heading = document.createElement("div");
      const kicker = document.createElement("p");
      kicker.className = "admin-kicker";
      kicker.textContent = "Related record";
      const title = document.createElement("h2");
      title.textContent = "Station";
      heading.append(kicker, title);

      installed = document.createElement("button");
      installed.type = "button";
      installed.textContent = "View station →";
      installed.setAttribute("aria-label", `View station ${stationName}`);
      installed.addEventListener("click", () => {
        if (opening) return;
        opening = true;
        installed!.disabled = true;
        installed!.textContent = "Opening…";

        const navigation = document.querySelector<HTMLElement>(".admin-sidebar nav");
        const stationsButton = Array.from(navigation?.querySelectorAll<HTMLButtonElement>("button") ?? []).find(
          (button) => text(button.textContent) === "Stations",
        );
        stationsButton?.click();

        let attempts = 0;
        const openMatchingRow = () => {
          attempts += 1;
          const nativeContent = document.querySelector<HTMLElement>(
            ".admin-shell > .admin-content:not([data-admin-station-reports-host])",
          );
          const rows = Array.from(
            nativeContent?.querySelectorAll<HTMLTableRowElement>(".admin-table tbody tr") ?? [],
          );
          const match = rows.find((row) => {
            const rowText = text(row.textContent);
            return (
              rowText.includes(stationName) &&
              (!stationAddress || stationAddress === "—" || rowText.includes(stationAddress))
            );
          });
          if (match) {
            match.click();
            opening = false;
            return;
          }
          if (attempts < 40) {
            window.setTimeout(openMatchingRow, 100);
            return;
          }
          opening = false;
          if (installed?.isConnected) {
            installed.disabled = false;
            installed.textContent = "View station →";
          }
        };
        window.setTimeout(openMatchingRow, 50);
      });
      header.append(heading, installed);

      factsList.className = "admin-related-summary";
      factsList.replaceChildren();
      const summaryFacts: Array<[string, string]> = [
        ["Name", stationName],
        ["Address line", stationAddress || "—"],
      ];
      if (stationCity) summaryFacts.push(["City", stationCity]);
      for (const [label, value] of summaryFacts) {
        const row = document.createElement("div");
        const term = document.createElement("dt");
        term.textContent = label;
        const description = document.createElement("dd");
        description.textContent = value;
        row.append(term, description);
        factsList.append(row);
      }
    };

    install();
    const observer = new MutationObserver(install);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      installed?.remove();
    };
  }, []);

  return null;
}
