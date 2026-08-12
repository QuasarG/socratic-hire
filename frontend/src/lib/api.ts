import type { Deliverables, OutlineNode, ProfileCard, StoredMessage } from "@/types";

export interface SessionState {
  session_id: string;
  profile: ProfileCard;
  outline: OutlineNode[];
  messages: StoredMessage[];
  deliverables: Deliverables | null;
  converged: boolean;
  running: boolean;
}

export async function* parseSSE(
  response: Response,
  signal?: AbortSignal
): AsyncGenerator<{ type: string; payload: Record<string, unknown> }> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      if (signal?.aborted) break;
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.length ? lines.pop()! : "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;
        try {
          yield JSON.parse(trimmed.slice(6));
        } catch {
          /* 跳过坏行 */
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export interface SessionSummary {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  status: string;
}

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await fetch("/api/sessions");
  if (!res.ok) return [];
  const data = await res.json();
  return data.sessions || [];
}

export async function deleteSession(sid: string): Promise<boolean> {
  const res = await fetch(`/api/sessions/${sid}`, { method: "DELETE" });
  return res.ok;
}

export async function deleteSessions(sids: string[]): Promise<void> {
  await fetch("/api/sessions/batch-delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_ids: sids }),
  });
}

export async function createSession(): Promise<string> {
  const res = await fetch("/api/sessions", { method: "POST" });
  const data = await res.json();
  return data.session_id;
}

export async function getState(sessionId: string): Promise<SessionState | null> {
  const res = await fetch(`/api/sessions/${sessionId}/state`);
  if (!res.ok) return null;
  return res.json();
}

export function chatStream(sessionId: string, message: string) {
  return fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

export async function regenerateDeliverables(sessionId: string): Promise<Deliverables> {
  const res = await fetch(`/api/sessions/${sessionId}/deliverables/regenerate`, { method: "POST" });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `HTTP ${res.status}`);
  }
  return res.json();
}
