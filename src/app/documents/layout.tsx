import { AppShell } from "@/app/components/AppShell";

export default function DocumentsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <AppShell>{children}</AppShell>;
}
