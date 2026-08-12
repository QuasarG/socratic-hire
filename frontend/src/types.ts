export interface TextSegment {
  type: "text";
  text: string;
}

export interface ToolSegment {
  type: "tool";
  call_id: string;
  tool: string;
  label: string;
  args_summary?: string;
  status?: "ok" | "error";
  summary?: string;
  detail?: string;
}

export type ChatSegment = TextSegment | ToolSegment;

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  segments: ChatSegment[];
  error?: string;
}

export interface ProfileField {
  label: string;
  value: string | string[] | null;
  confidence: number;
  evidence: string;
  status: "empty" | "probing" | "confirmed";
}

export interface Conflict {
  fields: string[];
  description: string;
  status: "open" | "resolved";
  resolution: string | null;
}

export interface ProfileCard {
  required_fields: Record<string, ProfileField>;
  optional_fields: Record<string, ProfileField>;
  conflicts: Conflict[];
  converged: boolean;
}

export interface OutlineNode {
  id: string;
  parent_id: string | null;
  order: number;
  topic: string;
  question_hint: string;
  linked_fields: string[];
  status: "pending" | "active" | "covered" | "obsolete";
  source: "initial" | "dynamic";
  answer_summary: string | null;
}

export interface Deliverables {
  persona_profile?: string;
  jd_draft: string;
  screening_criteria: { hard_requirements?: string[]; bonus_items?: string[] };
  reference_jobs?: { job_id: string; title: string; score: number }[];
}

/** 后端持久化的历史消息（文本 + 已完成工具记录） */
export interface StoredMessage {
  role: "user" | "assistant";
  text: string;
  tools: { tool: string; label: string; status: string; summary: string; detail?: string }[];
}
