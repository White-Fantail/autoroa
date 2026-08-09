import { SiteFooter, SiteHeader } from "../components/SiteChrome";
import { FuelMapExplorer } from "./FuelMapExplorer";

export default function FuelMapPage() {
  return (
    <>
      <SiteHeader />
      <main className="wrap page-shell map-page">
        <section className="page-heading compact">
          <p className="eyebrow">Nearby prices</p>
          <h1>Fuel map</h1>
          <p>Choose a fuel type and compare visible pump prices around you.</p>
        </section>
        <FuelMapExplorer />
      </main>
      <SiteFooter />
    </>
  );
}
