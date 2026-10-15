/**
 * client.ts — the one function every API call goes through.
 *
 * What it adds on top of fetch(): the API base URL (empty in the single-container setup), cookies
 * (`credentials: 'include'`), JSON encoding/decoding, and a typed ApiError carrying the backend's
 * { error: { code, message } } so screens can show the message directly.
 * A 401 (not logged in) sends the user to /login, except for the "who am I" check.
 */

/** Empty string = same origin (production container, or the Vite dev proxy). */
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

export class ApiError extends Error {
  status: number;
  code: string;
  extra: Record<string, unknown>;

  constructor(status: number, code: string, message: string, extra: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  /** Don't redirect to /login on 401 (used by the initial "am I logged in?" check). */
  allow401?: boolean;
}

const PUBLIC_PATHS = ['/', '/login', '/signup'];

/** Call the backend and return the parsed JSON (typed as T). Throws ApiError on failure. */
export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, allow401 = false } = options;
  let response: Response;
  try {
    response = await fetch(API_BASE + path, {
      method,
      signal,
      credentials: 'include',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    throw new ApiError(0, 'network', "Couldn't reach ChangeWatch. Check your connection and try again.");
  }

  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const errorBody = (data as { error?: { code?: string; message?: string } } | null)?.error;
    const error = new ApiError(
      response.status,
      errorBody?.code ?? 'http_error',
      errorBody?.message ?? `Something went wrong (HTTP ${response.status}).`,
      (errorBody as Record<string, unknown>) ?? {},
    );
    if (response.status === 401 && !allow401 && !PUBLIC_PATHS.includes(window.location.pathname)) {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.assign(`/login?next=${next}`);
    }
    throw error;
  }
  return data as T;
}

/** Turn a backend-relative URL (e.g. /api/media/...) into an absolute one when split hosting is used. */
export function mediaUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  return path.startsWith('http') ? path : API_BASE + path;
}
