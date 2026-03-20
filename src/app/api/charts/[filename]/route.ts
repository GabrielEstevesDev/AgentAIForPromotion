import { NextRequest } from "next/server";

import { getBackendUrl } from "@/lib/backend";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ filename: string }> },
) {
  const { filename } = await params;

  // Prevent path traversal
  if (filename.includes("/") || filename.includes("\\") || filename.includes("..")) {
    return new Response("Invalid filename.", { status: 400 });
  }

  try {
    const backendRes = await fetch(`${getBackendUrl()}/api/charts/${filename}`, {
      cache: "no-store",
    });

    if (!backendRes.ok) {
      return new Response("Chart not found.", { status: backendRes.status });
    }

    const blob = await backendRes.blob();
    return new Response(blob, {
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "public, max-age=3600",
      },
    });
  } catch {
    return new Response("Failed to fetch chart from backend.", { status: 502 });
  }
}
