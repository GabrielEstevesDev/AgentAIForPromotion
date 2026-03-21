import { NextRequest, NextResponse } from "next/server";

import { getBackendUrl } from "@/lib/backend";

export async function GET(request: NextRequest) {
  const sessionId = request.nextUrl.searchParams.get("sessionId");
  const backendUrl = sessionId
    ? `${getBackendUrl()}/api/conversations?sessionId=${encodeURIComponent(sessionId)}`
    : `${getBackendUrl()}/api/conversations`;
  const response = await fetchBackend(backendUrl, {
    cache: "no-store",
  });

  return proxyJson(response);
}

export async function POST(request: NextRequest) {
  const response = await fetchBackend(`${getBackendUrl()}/api/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });

  return proxyJson(response);
}

async function proxyJson(response: Response) {
  const text = await response.text();
  return new NextResponse(text, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/json",
    },
  });
}

async function fetchBackend(input: string, init?: RequestInit) {
  try {
    return await fetch(input, init);
  } catch (error) {
    const detail =
      error instanceof Error ? error.message : "Unable to reach the backend service.";
    return NextResponse.json({ error: detail }, { status: 502 });
  }
}
