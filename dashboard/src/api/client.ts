export class ApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;

  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export type SessionTokens = {
  accessToken: string;
  refreshToken: string;
};

const SESSION_KEY = "rag-platform-session";

export function loadSession(): SessionTokens | null {
  const raw = window.localStorage.getItem(SESSION_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as SessionTokens;
  } catch {
    return null;
  }
}

export function saveSession(session: SessionTokens | null): void {
  if (!session) {
    window.localStorage.removeItem(SESSION_KEY);
    return;
  }
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export async function apiRequest<T>(path: string, init: RequestInit = {}, tokens?: SessionTokens | null): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (tokens?.accessToken) {
    headers.set("Authorization", `Bearer ${tokens.accessToken}`);
  }

  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let payload: { detail?: string; code?: string; details?: unknown } | null = null;
    try {
      payload = (await response.json()) as { detail?: string; code?: string; details?: unknown };
    } catch {
      payload = null;
    }
    const fallbackText = payload?.detail ?? response.statusText ?? "请求失败";
    throw new ApiError(fallbackText, response.status, payload?.code, payload?.details);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
