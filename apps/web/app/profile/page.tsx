import { SiteFooter, SiteHeader } from "../components/SiteChrome";
import AchievementProfile from "./AchievementProfile";

export default function ProfilePage(){
  return <>
    <SiteHeader />
    <main className="wrap page-shell achievement-profile-page">
      <section className="page-heading compact">
        <p className="eyebrow">Community profile</p>
        <h1>Your achievements</h1>
        <p>Track progress, choose the achievements you want to feature, and keep a permanent record of regional trophies.</p>
      </section>
      <AchievementProfile />
    </main>
    <SiteFooter />
  </>;
}
