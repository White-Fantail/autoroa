import { SiteFooter, SiteHeader } from "../components/SiteChrome";
import LoginPanel from "./LoginPanel";

export default function LoginPage() {
  return <>
    <SiteHeader />
    <main className="wrap page-shell">
      <section className="page-heading compact" style={{textAlign:"center"}}>
        <p className="eyebrow">Account</p>
        <h1>Sign in to Autoroa</h1>
        <p>Contribute verified fuel prices and keep your updates connected to your account.</p>
      </section>
      <LoginPanel />
    </main>
    <SiteFooter />
  </>;
}
