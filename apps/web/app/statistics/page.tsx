import Link from "next/link";
import { SiteFooter, SiteHeader } from "../components/SiteChrome";

const averages = [
  { fuel: "Regular 91", price: "2.41", change: "↓ 3.2¢", tone: "green" },
  { fuel: "Premium 95", price: "2.58", change: "↓ 2.1¢", tone: "gold" },
  { fuel: "Premium 98", price: "2.69", change: "↑ 1.4¢", tone: "blue" },
  { fuel: "Diesel", price: "1.82", change: "↓ 4.6¢", tone: "ink" },
];
const cheapest = [
  ["NPD Moorhouse", "Christchurch", "$2.239"],
  ["Waitomo Fitzgerald", "Christchurch", "$2.259"],
  ["Gull Stanmore", "Christchurch", "$2.279"],
  ["Pak'nSave Fuel Hornby", "Christchurch", "$2.289"],
  ["Mobil Papanui", "Christchurch", "$2.309"],
];

export default function StatisticsPage() {
  return (
    <>
      <SiteHeader />
      <main className="wrap page-shell">
        <section className="page-heading">
          <p className="eyebrow">Community fuel snapshot</p>
          <h1>New Zealand fuel statistics</h1>
          <p>
            See the shape of today&apos;s market at a glance, then find the best
            price for your own journey.
          </p>
          <span className="data-note">Preview data · Illustrative only</span>
        </section>
        <section className="average-grid" aria-label="Average fuel prices">
          {averages.map((item) => (
            <article className="average-card" key={item.fuel}>
              <div className={`fuel-strip ${item.tone}`}>{item.fuel}</div>
              <div className="average-value">
                <span>$</span>
                {item.price}
                <small>/L</small>
              </div>
              <p>
                <span className={item.change.startsWith("↑") ? "up" : "down"}>
                  {item.change}
                </span>{" "}
                over 28 days
              </p>
            </article>
          ))}
        </section>
        <section className="stats-layout">
          <article className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Best value</p>
                <h2>Lowest Regular 91 prices</h2>
              </div>
              <Link href="/fuel-map">Open map →</Link>
            </div>
            <div className="price-table" role="table">
              <div className="table-row table-head" role="row">
                <span>Station</span>
                <span>Area</span>
                <span>Price/L</span>
              </div>
              {cheapest.map((row) => (
                <div className="table-row" role="row" key={row[0]}>
                  <strong>{row[0]}</strong>
                  <span>{row[1]}</span>
                  <strong>{row[2]}</strong>
                </div>
              ))}
            </div>
          </article>
          <aside className="panel insight-panel">
            <p className="eyebrow">Market pulse</p>
            <h2>Prices are easing</h2>
            <p className="insight-number">3.2¢</p>
            <p className="muted">
              Regular 91 is lower than the illustrative 28-day comparison.
            </p>
            <div
              className="mini-chart"
              aria-label="Illustrative 28-day downward price trend"
            >
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
            </div>
            <div className="watch-grid">
              <div>
                <strong>2,478</strong>
                <span>Stations watched</span>
              </div>
              <div>
                <strong>75k</strong>
                <span>Reports this week</span>
              </div>
            </div>
          </aside>
        </section>
        <section className="map-cta">
          <div>
            <p className="eyebrow">Make it local</p>
            <h2>National averages are only the start.</h2>
            <p>
              Use the fuel map to compare prices around your current location by
              fuel type.
            </p>
          </div>
          <Link className="button button-light" href="/fuel-map">
            Find fuel near me
          </Link>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
