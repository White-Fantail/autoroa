import type { ReactNode } from "react";
import AdminAuthShell from "./AdminAuthShell";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminAuthShell>{children}</AdminAuthShell>;
}
