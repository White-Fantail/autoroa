import { notFound } from "next/navigation";
import AdminDetailPageClient from "../../AdminDetailPageClient";
import AdminOcrDetail from "../../AdminOcrDetail";
import AdminStationDetail from "../../AdminStationDetail";

const supported = new Set(["ocr-queue","station-reports","stations","brands","observations","receipt-failures","unmatched-stations","users","vehicles","fill-ups"]);

export default async function AdminDetailPage({ params }: { params: Promise<{ section: string; id: string }> }) {
  const { section, id } = await params;
  if (!supported.has(section) || !id) notFound();
  if (section === "ocr-queue") return <AdminOcrDetail id={id} />;
  if (section === "stations") return <AdminStationDetail id={id} />;
  return <AdminDetailPageClient section={section} id={id} />;
}
