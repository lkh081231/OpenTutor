const TOKEN_STORAGE_KEYS = [
  "access_token",
  "accessToken",
  "auth.access_token",
  "authToken",
  "token",
  "opentutor.access_token",
  "opentutor.auth",
  "opentutor.session",
] as const;

const TOKEN_COOKIE_KEYS = [
  "access_token",
  "auth_token",
  "token",
] as const;

function extractTokenFromObject(value: Record<string, unknown>): string | null {
  const directKeys = ["access_token", "accessToken", "token"] as const;
  for (const key of directKeys) {
    const candidate = value[key];
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }

  const nested = value.tokens;
  if (nested && typeof nested === "object") {
    return extractTokenFromObject(nested as Record<string, unknown>);
  }

  return null;
}

function normalizeToken(raw: string | null): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;

  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (typeof parsed === "string") {
      return parsed.trim() || null;
    }
    if (parsed && typeof parsed === "object") {
      return extractTokenFromObject(parsed as Record<string, unknown>);
    }
  } catch {
    // Fall back to treating the value as a raw token string.
  }

  return trimmed;
}

function readFromStorage(storage: Storage): string | null {
  for (const key of TOKEN_STORAGE_KEYS) {
    const token = normalizeToken(storage.getItem(key));
    if (token) return token;
  }
  return null;
}

function readFromCookies(): string | null {
  if (typeof document === "undefined" || !document.cookie) {
    return null;
  }

  const cookies = document.cookie.split(";").map((entry) => entry.trim());
  for (const key of TOKEN_COOKIE_KEYS) {
    const prefix = `${key}=`;
    const match = cookies.find((cookie) => cookie.startsWith(prefix));
    if (!match) continue;
    const token = normalizeToken(decodeURIComponent(match.slice(prefix.length)));
    if (token) return token;
  }
  return null;
}

export function getStoredAccessToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  const localToken = readFromStorage(window.localStorage);
  if (localToken) return localToken;

  const sessionToken = readFromStorage(window.sessionStorage);
  if (sessionToken) return sessionToken;

  return readFromCookies();
}

export function buildAuthHeaders(headers?: HeadersInit): Headers {
  const resolved = new Headers(headers);
  const token = getStoredAccessToken();
  if (token && !resolved.has("Authorization")) {
    resolved.set("Authorization", `Bearer ${token}`);
  }
  return resolved;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
}

let sessionGeneration = 0;
let pendingRefresh: { generation: number; promise: Promise<boolean> } | null = null;

export function storeAuthTokens(tokens: AuthTokens): void {
  sessionGeneration += 1;
  window.localStorage.setItem("access_token", tokens.access_token);
  window.localStorage.setItem("refresh_token", tokens.refresh_token);
}

export function clearAuthTokens(): void {
  sessionGeneration += 1;
  for (const storage of [window.localStorage, window.sessionStorage]) {
    for (const key of [...TOKEN_STORAGE_KEYS, "refresh_token"]) storage.removeItem(key);
  }
  for (const key of TOKEN_COOKIE_KEYS) document.cookie = `${key}=; Max-Age=0; Path=/; SameSite=Lax`;
  window.dispatchEvent(new Event("opentutor:logout"));
}

export function safeReturnPath(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u0020]/.test(value)) return "/exam-practice";
  try {
    const url = new URL(value, "https://opentutor.invalid");
    if (url.origin !== "https://opentutor.invalid" || url.pathname === "/login") return "/exam-practice";
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "/exam-practice";
  }
}

async function refreshAccessToken(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  const refreshToken = window.localStorage.getItem("refresh_token");
  if (!refreshToken) return false;
  if (pendingRefresh?.generation === sessionGeneration) return pendingRefresh.promise;
  const generation = sessionGeneration;
  const promise = (async () => {
    const response = await fetch("/api/auth/refresh", {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) {
      if (response.status !== 401) throw new Error("Session refresh unavailable");
      if (generation === sessionGeneration) clearAuthTokens();
      return false;
    }
    const tokens = await response.json() as AuthTokens;
    if (generation !== sessionGeneration) return false;
    if (typeof tokens.access_token !== "string" || !tokens.access_token || typeof tokens.refresh_token !== "string" || !tokens.refresh_token) throw new Error("Invalid session");
    window.localStorage.setItem("access_token", tokens.access_token);
    window.localStorage.setItem("refresh_token", tokens.refresh_token);
    return true;
  })().finally(() => {
    if (pendingRefresh?.promise === promise) pendingRefresh = null;
  });
  pendingRefresh = { generation, promise };
  return promise;
}

/** Retry once after refreshing the existing API JWT session. */
export async function fetchWithAuth(url: string, options: RequestInit): Promise<Response> {
  const generation = sessionGeneration;
  const response = await fetch(url, options);
  if (response.status !== 401 || url.includes("/auth/login") || url.includes("/auth/refresh")) return response;
  if (generation !== sessionGeneration) return response;
  if (await refreshAccessToken()) {
    if (generation !== sessionGeneration) return response;
    options.signal?.throwIfAborted();
    const headers = new Headers(options.headers);
    headers.set("Authorization", `Bearer ${getStoredAccessToken()}`);
    const retried = await fetch(url, { ...options, headers });
    if (retried.status === 401 && generation === sessionGeneration) clearAuthTokens();
    return retried;
  }
  if (generation === sessionGeneration && getStoredAccessToken()) clearAuthTokens();
  return response;
}
