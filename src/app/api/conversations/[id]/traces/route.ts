import { NextResponse } from "next/server";

import { getBackendUrl } from "@/lib/backend";

type RouteContext = {
  params: Promise<{
    id: string;
  }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { id } = await context.params;
  try {
    const response = await fetch(
      `${getBackendUrl()}/api/conversations/${id}/traces`,
      { cache: "no-store" },
    );

    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "application/json",
      },
    });
  } catch (error) {
    const detail =
      error instanceof Error ? error.message : "Unable to reach the backend service.";
    return NextResponse.json({ error: detail }, { status: 502 });
  }
}
