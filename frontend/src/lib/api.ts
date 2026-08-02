
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export type Route = "code" | "commits" | "both";
export type SessionStatus = "indexing" | "ready" | "failed";

export interface IndexStats {
  code_chunks_indexed: number;
  commit_chunks_indexed: number;
  files_seen: number;
}

export interface IndexStatus {
  status: SessionStatus;
  stats: IndexStats | null;
  error: string | null;
}

export interface ChatReply {
  answer: string;
  route: Route;
  code_hits: number;
  commit_hits: number;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    
    throw new ApiError(
      `Could not reach the API${API_BASE ? ` at ${API_BASE}` : ""}.`,
      0,
    );
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    
  }

  if (!response.ok) {
    const detail = (body as { detail?: unknown })?.detail;
    throw new ApiError(
      typeof detail === "string" ? detail : response.statusText,
      response.status,
    );
  }
  return body as T;
}

const jsonPost = (payload: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

export const startIndexing = (repoUrl: string) =>
  request<{ session_id: string; status: SessionStatus }>(
    "/index",
    jsonPost({ repo_url: repoUrl }),
  );

export const getIndexStatus = (sessionId: string) =>
  request<IndexStatus>(`/index/${sessionId}`);

export const ask = (sessionId: string, question: string) =>
  request<ChatReply>("/chat", jsonPost({ session_id: sessionId, question }));
