"use client";

import { useEffect } from "react";

export default function AdminAchievementNavLink() {
  useEffect(() => {
    if (window.location.pathname !== "/admin") return;

    let button: HTMLButtonElement | null = null;
    const install = () => {
      const nav = document.querySelector(".admin-sidebar nav");
      if (!nav || nav.querySelector('[data-achievement-admin-link="true"]')) return;

      button = document.createElement("button");
      button.type = "button";
      button.textContent = "Achievements";
      button.dataset.achievementAdminLink = "true";
      button.addEventListener("click", () => {
        window.location.assign("/admin/achievements");
      });
      nav.appendChild(button);
    };

    install();
    const observer = new MutationObserver(install);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      observer.disconnect();
      button?.remove();
    };
  }, []);

  return null;
}
