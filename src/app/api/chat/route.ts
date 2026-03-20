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

    backendResponse = await fetch(`${getBackendUrl()}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
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

        buffer += normalizeSseChunk(decoder.decode(value, { stream: true }));
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

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

          // Phase 2.4: Forward perf events as data stream annotations for dev visibility
          if (parsed.event === "perf") {
            const payload = safeParse(parsed.data);
            if (payload) {
              dataStream.writeMessageAnnotation({
                type: "perf",
                ...payload,
              });
            }
          }

          // Forward trace events as data stream annotations
          if (parsed.event === "trace") {
            const tracePayload = safeParse(parsed.data);
            if (Array.isArray(tracePayload)) {
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
            dataStream.write(
              formatDataPart("d", {
                finishReason: "stop",
              }),
            );
          }
        }
      }

      buffer += normalizeSseChunk(decoder.decode());

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
            formatDataPart("d", {
              finishReason: "stop",
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

function normalizeSseChunk(value: string) {
  return value.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
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

function safeParse(value: string) {
  try {
    return JSON.parse(value) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function formatDataPart<TPrefix extends "0" | "3" | "d">(
  prefix: TPrefix,
  value: unknown,
): `${TPrefix}:${string}\n` {
  return `${prefix}:${JSON.stringify(value)}\n`;
}
