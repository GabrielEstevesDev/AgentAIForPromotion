import type { UseCaseCardsPayload, HitlRequestPayload } from "./types";

// ---------------------------------------------------------------------------
// Extract a JSON code block with a specific top-level key
// ---------------------------------------------------------------------------

function extractJsonBlock<T>(
  content: string,
  topLevelKey: string,
): { payload: T; remainingContent: string } | null {
  // Match ```json ... ``` blocks
  const regex = /```json\s*\n([\s\S]*?)```/g;

  for (const match of content.matchAll(regex)) {
    try {
      const parsed = JSON.parse(match[1]);
      if (parsed && typeof parsed === "object" && topLevelKey in parsed) {
        const remainingContent =
          content.slice(0, match.index!) + content.slice(match.index! + match[0].length);
        return { payload: parsed[topLevelKey] as T, remainingContent };
      }
    } catch {
      // Not valid JSON — skip
    }
  }

  return null;
}

// ---------------------------------------------------------------------------
// Public extractors
// ---------------------------------------------------------------------------

export function extractUseCaseCards(
  content: string,
): { payload: UseCaseCardsPayload | null; remainingContent: string } {
  const result = extractJsonBlock<UseCaseCardsPayload>(content, "USE_CASE_CARDS");
  if (result) return { payload: result.payload, remainingContent: result.remainingContent };
  return { payload: null, remainingContent: content };
}

export function extractHitlRequest(
  content: string,
): { payload: HitlRequestPayload | null; remainingContent: string } {
  const result = extractJsonBlock<HitlRequestPayload>(content, "HITL_REQUEST");
  if (result) return { payload: result.payload, remainingContent: result.remainingContent };
  return { payload: null, remainingContent: content };
}

export function extractStructuredBlocks(content: string): {
  useCaseCards: UseCaseCardsPayload | null;
  hitlRequest: HitlRequestPayload | null;
  cleanContent: string;
} {
  const ucResult = extractUseCaseCards(content);
  const hitlResult = extractHitlRequest(ucResult.remainingContent);

  return {
    useCaseCards: ucResult.payload,
    hitlRequest: hitlResult.payload,
    cleanContent: hitlResult.remainingContent,
  };
}
