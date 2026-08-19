import { SiteFooter, SiteHeader } from "../components/SiteChrome";
import ContributionsPanel from "./ContributionsPanel";

export default function ContributionsPage(){
  return <>
    <SiteHeader />
    <main className="wrap page-shell">
      <section className="page-heading compact"><p className="eyebrow">Your updates</p><h1>My Contributions</h1><p>See how your fuel-price photos were reviewed, what changed on Fuel Map, and which updates earned points.</p></section>
      <ContributionsPanel />
    </main>
    <SiteFooter />
  </>
}
