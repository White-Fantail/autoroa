"use client";

import { MouseEvent, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import AchievementAdmin from "../admin/achievements/AchievementAdmin";

const isAchievementSection = () =>
  window.location.pathname === "/admin" &&
  new URLSearchParams(window.location.search).get("section") === "achievements";

export default function AdminAchievementNavLink() {
  const [active, setActive] = useState(false);
  const [content, setContent] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (window.location.pathname !== "/admin") return;

    setActive(isAchievementSection());
    let button: HTMLButtonElement | null = null;
    let nav: HTMLElement | null = null;

    const openAchievements = () => {
      const params = new URLSearchParams(window.location.search);
      params.set("section", "achievements");
      window.history.pushState(
        { section: "achievements" },
        "",
        `${window.location.pathname}?${params.toString()}${window.location.hash}`,
      );
      setActive(true);
    };

    const onNavClick = (event: Event) => {
      const target = event.target as Element | null;
      const clickedButton = target?.closest("button");
      if (clickedButton && clickedButton !== button) setActive(false);
    };

    const install = () => {
      const nextNav = document.querySelector<HTMLElement>(".admin-sidebar nav");
      const nextContent = document.querySelector<HTMLElement>(".admin-content");
      if (nextContent) setContent(nextContent);
      if (!nextNav) return;

      if (nav !== nextNav) {
        nav?.removeEventListener("click", onNavClick, true);
        nav = nextNav;
        nav.addEventListener("click", onNavClick, true);
      }

      const existing = nextNav.querySelector<HTMLButtonElement>(
        '[data-achievement-admin-link="true"]',
      );
      if (existing) {
        button = existing;
        return;
      }

      button = document.createElement("button");
      button.type = "button";
      button.textContent = "Achievements";
      button.dataset.achievementAdminLink = "true";
      button.addEventListener("click", openAchievements);
      nextNav.appendChild(button);
    };

    const onPopState = () => setActive(isAchievementSection());
    install();
    window.addEventListener("popstate", onPopState);
    const observer = new MutationObserver(install);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      observer.disconnect();
      window.removeEventListener("popstate", onPopState);
      nav?.removeEventListener("click", onNavClick, true);
      button?.remove();
    };
  }, []);

  useEffect(() => {
    if (!content) return;
    const navButtons = Array.from(
      document.querySelectorAll<HTMLButtonElement>(".admin-sidebar nav button"),
    );
    const achievementButton = navButtons.find(
      (button) => button.dataset.achievementAdminLink === "true",
    );

    if (active) {
      navButtons.forEach((button) => button.classList.remove("active"));
      achievementButton?.classList.add("active");
      achievementButton?.setAttribute("aria-current", "page");
    } else {
      achievementButton?.classList.remove("active");
      achievementButton?.removeAttribute("aria-current");
    }

    const hidden = new Map<HTMLElement, boolean>();
    const hideNativeContent = () => {
      Array.from(content.children).forEach((child) => {
        if (!(child instanceof HTMLElement)) return;
        if (child.dataset.achievementSectionHost === "true") return;
        if (!hidden.has(child)) hidden.set(child, child.hidden);
        child.hidden = active;
      });
    };

    hideNativeContent();
    if (!active) return;

    const observer = new MutationObserver(hideNativeContent);
    observer.observe(content, { childList: true });
    return () => {
      observer.disconnect();
      hidden.forEach((wasHidden, child) => {
        child.hidden = wasHidden;
      });
    };
  }, [active, content]);

  if (!active || !content) return null;

  const handleAchievementClick = (event: MouseEvent<HTMLDivElement>) => {
    const target = event.target as Element | null;
    const adminLink = target?.closest('a[href="/admin"]');
    if (!adminLink) return;
    event.preventDefault();
    const dashboard = Array.from(
      document.querySelectorAll<HTMLButtonElement>(".admin-sidebar nav button"),
    ).find((item) => item.textContent?.trim() === "Dashboard");
    dashboard?.click();
  };

  return createPortal(
    <div
      data-achievement-section-host="true"
      onClickCapture={handleAchievementClick}
    >
      <AchievementAdmin />
    </div>,
    content,
  );
}
