import { createDataStreamResponse } from "ai";

import { getBackendUrl } from "@/lib/backend";

// Allow long-running agent responses (complex multi-tool queries)
export const maxDuration = 120;

type IncomingBody = {
  messages?: Array<{
    role: string;
    content: string;
  }>;
  conversationId?: string;
};

export async function POST(request: Request) {
  const body = (await request.json()) as IncomingBody;

  if (!body.conversationId) {
    return Response.json(
      { error: "conversationId is required." },
      { status: 400 },
    );
  }

  let backendResponse: Response;
  try {
    // 3-minute timeout to match the backend agent timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120_000);

    // Forward admin token if present
    const backendHeaders: Record<string, string> = {
      "Content-Type": "application/json",
    };
    const adminToken = request.headers.get("x-admin-token");
    if (adminToken) {
      backendHeaders["x-admin-token"] = adminToken;
    }

    backendResponse = await fetch(`${getBackendUrl()}/api/chat`, {
      method: "POST",
      headers: backendHeaders,
      body: JSON.stringify({
        messages: body.messages ?? [],
        conversationId: body.conversationId,
      }),
      cache: "no-store",
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return Response.json(
        { error: "The request took too long. Try a simpler question or break it into steps." },
        { status: 504 },
      );
    }
    const detail =
      error instanceof Error ? error.message : "Unable to reach the backend chat service.";
    return Response.json({ error: detail }, { status: 502 });
  }

  if (!backendResponse.ok || !backendResponse.body) {
    const errorText = await backendResponse.text();

    // For 429 rate-limit responses, parse and forward the structured detail
    if (backendResponse.status === 429) {
      try {
        const parsed = JSON.parse(errorText);
        // FastAPI wraps detail in { detail: "..." } — the detail itself is JSON
        const detail = typeof parsed.detail === "string" ? JSON.parse(parsed.detail) : parsed;
        return Response.json(detail, { status: 429 });
      } catch {
        return Response.json(
          { error: "rate_limit", message: "Too many requests. Please try again later." },
          { status: 429 },
        );
      }
    }

    return Response.json(
      { error: errorText || "Backend chat request failed." },
      { status: backendResponse.status || 500 },
    );
  }

  return createDataStreamResponse({
    execute: async (dataStream) => {
      const reader = backendResponse.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
        const { events, remaining } = extractSseEvents(buffer);
        buffer = remaining;

        for (const eventChunk of events) {
          const parsed = parseSseEvent(eventChunk);
          if (!parsed) {
            continue;
          }

          if (parsed.event === "token") {
            const payload = safeParse(parsed.data);
            const token = typeof payload?.token === "string" ? payload.token : "";
            if (token) {
              dataStream.write(formatDataPart("0", token));
            }
            // Empty token = heartbeat from backend; just receiving it keeps
            // the reader loop alive — no need to write anything to the data stream.
          }

          // Forward perf events as data stream annotations for dev visibility
          if (parsed.event === "perf") {
            const payload = safeParse(parsed.data);
            if (payload && typeof payload === "object") {
              dataStream.writeMessageAnnotation({
                type: "perf",
                ...payload,
              });
            }
          }

          // Forward trace events as data stream annotations
          if (parsed.event === "trace") {
            const tracePayload = safeParseArray(parsed.data);
            if (tracePayload) {
              dataStream.writeMessageAnnotation({
                type: "trace",
                events: tracePayload as unknown as string,
              });
            }
          }

          if (parsed.event === "error") {
            const payload = safeParse(parsed.data);
            const detail =
              typeof payload?.detail === "string" ? payload.detail : "Chat stream failed.";
            dataStream.write(formatDataPart("3", detail));
          }

          if (parsed.event === "done") {
            // AI SDK v4 requires finish_step (e) before finish_message (d)
            dataStream.write(
              formatDataPart("e", {
                finishReason: "stop",
                usage: { promptTokens: 0, completionTokens: 0 },
                isContinued: false,
              }),
            );
            dataStream.write(
              formatDataPart("d", {
                finishReason: "stop",
                usage: { promptTokens: 0, completionTokens: 0 },
              }),
            );
          }
        }
      }

      buffer += decoder.decode().replace(/\r\n/g, "\n").replace(/\r/g, "\n");

      if (buffer.trim()) {
        const parsed = parseSseEvent(buffer);
        if (parsed?.event === "error") {
          const payload = safeParse(parsed.data);
          const detail =
            typeof payload?.detail === "string" ? payload.detail : "Chat stream failed.";
          dataStream.write(formatDataPart("3", detail));
        }

        if (parsed?.event === "done") {
          dataStream.write(
            formatDataPart("e", {
              finishReason: "stop",
              usage: { promptTokens: 0, completionTokens: 0 },
              isContinued: false,
            }),
          );
          dataStream.write(
            formatDataPart("d", {
              finishReason: "stop",
              usage: { promptTokens: 0, completionTokens: 0 },
            }),
          );
        }
      }
    },
    onError: (error) => {
      if (error instanceof Error) {
        return error.message;
      }

      return "Chat stream failed.";
    },
  });
}

/**
 * Robust SSE event extractor. Splits a buffer into complete SSE events using
 * blank-line boundaries (line-by-line state machine). Returns complete events
 * and any partial trailing event still in the buffer.
 *
 * This replaces the fragile `/\n{2,}/` split which can produce fragments
 * containing raw `event:` or `data:` field names that then leak into the
 * Vercel AI SDK data stream parser when chunks arrive in unexpected sizes.
 */
function extractSseEvents(buffer: string): { events: string[]; remaining: string } {
  const events: string[] = [];
  const lines = buffer.split("\n");
  let current = "";

  for (const line of lines) {
    if (line === "") {
      // Blank line = SSE event boundary
      if (current.trim()) {
        events.push(current);
        current = "";
      }
    } else {
      current = current ? current + "\n" + line : line;
    }
  }

  return { events, remaining: current };
}

function parseSseEvent(chunk: string) {
  const lines = chunk.split("\n");
  let event = "message";
  const dataParts: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    }

    if (line.startsWith("data:")) {
      dataParts.push(line.slice(5).trim());
    }
  }

  if (dataParts.length === 0) {
    return null;
  }

  return {
    event,
    data: dataParts.join("\n"),
  };
}

function safeParse(value: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(value);
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function safeParseArray(value: string): unknown[] | null {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function formatDataPart<TPrefix extends "0" | "3" | "d" | "e">(
  prefix: TPrefix,
  value: unknown,
): `${TPrefix}:${string}\n` {
  return `${prefix}:${JSON.stringify(value)}\n`;
}
