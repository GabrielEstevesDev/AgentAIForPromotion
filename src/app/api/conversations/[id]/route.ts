import { NextRequest, NextResponse } from "next/server";

import { getBackendUrl } from "@/lib/backend";

type RouteContext = {
  params: Promise<{
    id: string;
  }>;
};

export async function GET(_request: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  const response = await fetchBackend(`${getBackendUrl()}/api/conversations/${id}`, {
    cache: "no-store",
  });

  return proxyJson(response);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  const response = await fetchBackend(`${getBackendUrl()}/api/conversations/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });

  return proxyJson(response);
}

export async function DELETE(_request: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  const response = await fetchBackend(`${getBackendUrl()}/api/conversations/${id}`, {
    method: "DELETE",
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

function internalKeyHeader(): Record<string, string> {
  const key = process.env.BACKEND_INTERNAL_KEY;
  return key ? { "X-Internal-Key": key } : {};
}

async function fetchBackend(input: string, init?: RequestInit) {
  try {
    return await fetch(input, {
      ...init,
      headers: { ...internalKeyHeader(), ...(init?.headers ?? {}) },
    });
  } catch (error) {
    const detail =
      error instanceof Error ? error.message : "Unable to reach the backend service.";
    return NextResponse.json({ error: detail }, { status: 502 });
  }
}
