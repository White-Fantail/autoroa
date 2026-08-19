import { redirect } from "next/navigation";

export default function AchievementAdminPage() {
  redirect("/admin?section=achievements");
}
