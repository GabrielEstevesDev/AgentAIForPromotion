// ---------------------------------------------------------------------------
// USE_CASE_CARDS types
// ---------------------------------------------------------------------------

export type UseCaseCard = {
  id: string;
  category?: string;
  title: string;
  description: string;
  tool_badges: string[];
  prompt: string;
  requires_hitl: boolean;
};

export type UseCaseCategory = {
  id: string;
  label: string;
  cards: UseCaseCard[];
};

export type UseCaseCardsPayload = {
  front_actions: UseCaseCard[];
  categories: UseCaseCategory[];
};

// ---------------------------------------------------------------------------
// HITL types
// ---------------------------------------------------------------------------

export type HitlEvidence = {
  type: "RAG_POLICY" | "SQL_FACT" | "WEB_SOURCE";
  label: string;
  content: string;
  reference?: string;
};

export type HitlArtifactPreview = {
  type: string;
  format: "text" | "markdown" | "table";
  content: string;
};

export type HitlControl = {
  id: string;
  label: string;
  type: "select" | "number" | "boolean" | "text";
  required: boolean;
  options?: string[];
  min?: number;
  max?: number;
  default?: unknown;
  help?: string;
};

export type HitlAction = {
  id: string;
  label: string;
};

export type HitlRequestPayload = {
  id: string;
  title: string;
  risk_tags: string[];
  summary: string;
  tools_used: string[];
  assumptions: string[];
  evidence: HitlEvidence[];
  artifacts_preview: HitlArtifactPreview[];
  controls: HitlControl[];
  actions: HitlAction[];
  on_approve: { next_step: string; outputs: string[] };
  on_request_changes: { expected_input: string; regeneration_rule: string };
  on_reject: { fallback: string };
};
