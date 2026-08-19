import { SiteFooter, SiteHeader } from "../components/SiteChrome";
import LeaderboardPanel from "./LeaderboardPanel";

export default function LeaderboardPage(){
  return <>
    <SiteHeader />
    <main className="wrap page-shell">
      <section className="page-heading compact"><p className="eyebrow">Community</p><h1>Leaderboard</h1><p>Rank contributors by verified fuel-price updates. Rankings are derived from the stations where updates were actually applied.</p></section>
      <LeaderboardPanel />
    </main>
    <SiteFooter />
  </>
}
