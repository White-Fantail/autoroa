import Link from "next/link";
import { SiteFooter, SiteHeader } from "./components/SiteChrome";

const steps = [
  "Scan your receipt",
  "Scan your odometer",
  "Track fuel economy",
  "Help verify fuel prices",
];
export default function Home() {
  return (
    <>
      <SiteHeader />
      <main>
        <section className="hero wrap">
          <div>
            <p>Fuel intelligence for New Zealand drivers</p>
            <h1>Find cheaper fuel. Know what your car really costs.</h1>
            <p>
              Turn every fill-up into useful vehicle insights—and fresher
              community fuel prices.
            </p>
            <div className="hero-actions">
              <Link className="button" href="/fuel-map">
                Explore fuel prices
              </Link>
              <Link className="text-link" href="/statistics">
                View NZ statistics →
              </Link>
            </div>
          </div>
          <div className="phone" aria-label="Example nearby fuel price">
            <small>Nearby lowest · 91</small>
            <div className="price">$2.239/L</div>
            <p>
              Verified 18 min ago
              <br />
              2.4 km away
            </p>
          </div>
        </section>
        <section id="how" className="section wrap">
          <h2>One fast fill-up flow</h2>
          <div className="grid">
            {steps.map((step, i) => (
              <article className="card" key={step}>
                <strong>{i + 1}</strong>
                <h3>{step}</h3>
                <p className="muted">
                  AI assists. You always review and confirm.
                </p>
              </article>
            ))}
          </div>
        </section>
        <section className="section wrap">
          <h2>Fuel prices, tracking, and vehicle insights</h2>
          <p className="muted">
            Compare fresh verified pump prices, understand monthly spend, and
            calculate full-tank fuel economy accurately.
          </p>
        </section>
        <section id="coming-soon" className="section wrap">
          <h2>Coming soon to iOS and Android</h2>
          <p className="muted">
            App Store and Google Play releases are in preparation.
          </p>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
