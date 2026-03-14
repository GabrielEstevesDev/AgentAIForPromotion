import { AppShell } from "@/app/components/AppShell";

export default function DatabaseLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <AppShell>{children}</AppShell>;
}
