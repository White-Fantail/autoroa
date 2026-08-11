import Link from "next/link";

const links = [
  { href: "/", label: "Home" },
  { href: "/statistics", label: "Statistics" },
  { href: "/fuel-map", label: "Fuel map" },
];

export function SiteHeader() {
  return (
    <header className="site-header">
      <nav className="nav wrap" aria-label="Main navigation">
        <Link className="logo" href="/" aria-label="Autoroa home">
          autoroa<span>.</span>
        </Link>
        <div className="nav-links">
          {links.map((link) => (
            <Link key={link.href} href={link.href}>
              {link.label}
            </Link>
          ))}
        </div>
        <a className="button nav-cta" href="/#coming-soon">
          Get early access
        </a>
      </nav>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer>
      <div className="wrap footer-row">
        <span>© Autoroa</span>
        <span>
          <Link href="/privacy">Privacy</Link> ·{" "}
          <Link href="/terms">Terms</Link>
        </span>
      </div>
    </footer>
  );
}
