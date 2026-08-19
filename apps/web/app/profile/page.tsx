import { SiteFooter, SiteHeader } from "../components/SiteChrome";
import ContributionsPanel from "../contributions/ContributionsPanel";
import AchievementProfile from "./AchievementProfile";
import ProfileIdentity from "./ProfileIdentity";

export default function ProfilePage(){
  return <>
    <SiteHeader />
    <main className="wrap page-shell achievement-profile-page">
      <section className="page-heading compact">
        <p className="eyebrow">Community profile</p>
        <h1>Your profile</h1>
        <p>See your contribution activity, track achievement progress, and manage your Autoroa account in one place.</p>
      </section>
      <ProfileIdentity />
      <section className="achievement-section">
        <div className="achievement-section-heading"><div><p className="eyebrow">Contribution overview</p><h2>My contributions</h2></div></div>
        <ContributionsPanel embedded />
      </section>
      <AchievementProfile />
    </main>
    <SiteFooter />
  </>;
}
