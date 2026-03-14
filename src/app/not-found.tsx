import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <div className="max-w-md rounded-[2rem] border border-[var(--border)] bg-[var(--card)] p-8 text-center shadow-[0_24px_80px_-40px_rgba(0,0,0,0.45)]">
        <p className="text-xs uppercase tracking-[0.28em] text-[var(--muted)]">404</p>
        <h1 className="mt-3 text-3xl font-semibold">Page not found</h1>
        <p className="mt-4 text-sm leading-6 text-[var(--muted)]">
          The requested page does not exist or is no longer available.
        </p>
        <Link
          href="/chat"
          className="mt-6 inline-flex rounded-2xl bg-[var(--accent)] px-4 py-3 text-sm font-medium text-white transition hover:bg-[var(--accent-strong)]"
        >
          Return to chat
        </Link>
      </div>
    </main>
  );
}
