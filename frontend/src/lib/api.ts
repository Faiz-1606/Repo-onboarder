/* Typed client for the Repo Onboarding Assistant API.
 *
 * VITE_API_BASE_URL is empty by default, which means "same origin as this
 * page" - correct when the backend serves the built frontend. Set it when the
 * two are deployed separately, and add this page's origin to the backend's
 * ALLOWED_ORIGINS or the browser will block the request before it is sent.
 */

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

/** Thrown for any non-2xx response, carrying the API's own `detail` string. */
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
    // A CORS rejection also lands here, indistinguishable from the API being
    // down - the browser deliberately withholds the reason.
    throw new ApiError(
      `Could not reach the API${API_BASE ? ` at ${API_BASE}` : ""}.`,
      0,
    );
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    /* a non-JSON error page; fall through to statusText */
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
