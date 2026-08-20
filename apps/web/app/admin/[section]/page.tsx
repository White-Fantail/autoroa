import { notFound } from "next/navigation";
import AdminRoutePageClient from "../AdminRoutePageClient";
import AdminOcrQueueList from "../AdminOcrQueueList";
import AdminStationReportsList from "../AdminStationReportsList";
import AdminStationsPageClient from "../AdminStationsPageClient";

const supported = new Set(["dashboard","ocr-queue","station-reports","stations","brands","observations","receipt-failures","unmatched-stations","users","vehicles","fill-ups"]);

export default async function AdminSectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  if (!supported.has(section)) notFound();
  if (section === "ocr-queue") return <AdminOcrQueueList />;
  if (section === "station-reports") return <AdminStationReportsList />;
  if (section === "stations") return <AdminStationsPageClient />;
  return <AdminRoutePageClient section={section} />;
}
