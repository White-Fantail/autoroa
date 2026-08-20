import './globals.css';
import './achievement-profile.css';
import './admin-achievements.css';
import './admin-segmented-controls.css';
import './admin-station-report-detail.css';
import 'leaflet/dist/leaflet.css';
import ImageUploadCompatibility from './components/ImageUploadCompatibility';
import AchievementCelebration from './components/AchievementCelebration';
export const metadata={metadataBase:new URL('https://autoroa.com'),title:'Autoroa — Smarter vehicle ownership',description:'Track fuel, understand running costs, and make better vehicle decisions in New Zealand.',openGraph:{title:'Autoroa — Smarter vehicle ownership',description:'Track fuel, understand running costs, and make better vehicle decisions in New Zealand.',url:'https://autoroa.com',siteName:'Autoroa',locale:'en_NZ',type:'website'},twitter:{card:'summary_large_image',title:'Autoroa — Smarter vehicle ownership',description:'Track fuel, understand running costs, and make better vehicle decisions in New Zealand.'}};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en-NZ"><body><ImageUploadCompatibility /><AchievementCelebration />{children}</body></html>}
