import AdminAuthShell from "./AdminAuthShell";

// Keep this route boundary free of an imported ReactNode type. In the monorepo,
// Next's generated LayoutProps can resolve a different @types/react instance
// during production builds, making otherwise equivalent ReactNode types
// incompatible. The shell itself still owns the concrete children typing.
export default function AdminLayout({ children }: { children: any }) {
  return <AdminAuthShell>{children}</AdminAuthShell>;
}
