"use client";

import { useEffect } from "react";

export default function AdminAchievementNavLink(){
  useEffect(()=>{
    if(window.location.pathname!=="/admin")return;
    let link:HTMLAnchorElement|null=null;
    const install=()=>{
      const nav=document.querySelector(".admin-sidebar nav");
      if(!nav||nav.querySelector('[data-achievement-admin-link="true"]'))return;
      link=document.createElement("a");
      link.href="/admin/achievements";
      link.textContent="Achievements";
      link.dataset.achievementAdminLink="true";
      link.style.display="block";
      link.style.padding="10px 12px";
      link.style.borderRadius="8px";
      link.style.textDecoration="none";
      link.style.color="inherit";
      nav.appendChild(link);
    };
    install();
    const observer=new MutationObserver(install);observer.observe(document.body,{childList:true,subtree:true});
    return()=>{observer.disconnect();link?.remove()};
  },[]);
  return null;
}
