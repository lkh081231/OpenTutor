import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { buildAuthHeaders, clearAuthTokens, fetchWithAuth, getStoredAccessToken, safeReturnPath, storeAuthTokens } from "./auth";

const tokens = { access_token: "fresh", refresh_token: "refresh-new" };
const response = (status: number, data: unknown = {}) => new Response(JSON.stringify(data), { status });
const mockFetch = vi.fn();
beforeEach(() => { clearAuthTokens(); mockFetch.mockReset(); vi.stubGlobal("fetch", mockFetch); });
afterEach(() => { vi.unstubAllGlobals(); });

describe("safe login return", () => {
  it.each([null, "https://evil.test", "//evil.test", "/\\evil.test", "/login", "/path\nnext", "/path next"])("rejects %s", (path) => {
    expect(safeReturnPath(path)).toBe("/exam-practice");
  });
  it("preserves a local route and query", () => { expect(safeReturnPath("/course/123?q=review#notes")).toBe("/course/123?q=review#notes"); });
});

describe("JWT refresh", () => {
  beforeEach(() => storeAuthTokens({ access_token: "expired", refresh_token: "refresh" }));
  it("refreshes and retries the original request once", async () => {
    mockFetch.mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(200, tokens)).mockResolvedValueOnce(response(200));
    expect((await fetchWithAuth("/api/auth/me", { headers: buildAuthHeaders() })).status).toBe(200);
    expect(mockFetch).toHaveBeenCalledTimes(3);
    expect(new Headers(mockFetch.mock.calls[2][1].headers).get("Authorization")).toBe("Bearer fresh");
  });
  it("clears an invalid refresh session without looping", async () => {
    mockFetch.mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(401));
    expect((await fetchWithAuth("/api/auth/me", {})).status).toBe(401);
    expect(getStoredAccessToken()).toBeNull();
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
  it.each(["network", "server"])("preserves credentials after a %s failure", async (failure) => {
    mockFetch.mockResolvedValueOnce(response(401));
    if (failure === "network") mockFetch.mockRejectedValueOnce(new TypeError("offline"));
    else mockFetch.mockResolvedValueOnce(response(503));
    await expect(fetchWithAuth("/api/auth/me", {})).rejects.toThrow();
    expect(getStoredAccessToken()).toBe("expired");
  });
  it("does not overwrite a new login with a delayed refresh", async () => {
    let finish: (value: Response) => void = () => {};
    const delayed = new Promise<Response>(resolve => { finish = resolve; });
    mockFetch.mockResolvedValueOnce(response(401)).mockReturnValueOnce(delayed);
    const request = fetchWithAuth("/api/auth/me", {});
    await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
    clearAuthTokens(); storeAuthTokens({ access_token: "new-login", refresh_token: "new-refresh" });
    finish(response(200, tokens));
    await request;
    expect(getStoredAccessToken()).toBe("new-login");
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
  it("does not refresh successful requests in the original open mode", async () => {
    clearAuthTokens(); mockFetch.mockResolvedValueOnce(response(200));
    await fetchWithAuth("/api/courses", {});
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});
