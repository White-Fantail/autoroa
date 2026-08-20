import { notFound } from "next/navigation";
import AdminRoutePageClient from "../AdminRoutePageClient";

const supported = new Set(["dashboard","ocr-queue","station-reports","stations","brands","observations","receipt-failures","unmatched-stations","users","vehicles","fill-ups"]);

export default async function AdminSectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  if (!supported.has(section)) notFound();
  return <AdminRoutePageClient section={section} />;
}
