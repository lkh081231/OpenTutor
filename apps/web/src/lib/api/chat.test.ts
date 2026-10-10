import { beforeEach, describe, expect, it, vi } from "vitest";
import { streamChat } from "./chat";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

describe("streamChat", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    localStorage.clear();
    document.cookie = "csrf_token=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/";
  });

  it("sends auth + csrf headers with credentials include", async () => {
    localStorage.setItem("access_token", "token-123");
    document.cookie = "csrf_token=csrf-123;path=/";
    mockFetch.mockResolvedValueOnce(
      new Response("event: done\ndata: {}\n\n", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );

    for await (const event of streamChat({ courseId: "course-1", message: "hello" })) {
      if (event.type === "done") break;
    }

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/chat");
    const headers = new Headers(init.headers);
    expect(init.credentials).toBe("include");
    expect(headers.get("Authorization")).toBe("Bearer token-123");
    expect(headers.get("X-CSRF-Token")).toBe("csrf-123");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("refreshes an expired session before opening the SSE stream", async () => {
    localStorage.setItem("access_token", "expired-token");
    localStorage.setItem("refresh_token", "refresh-token");
    mockFetch
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        access_token: "fresh-token", refresh_token: "fresh-refresh-token",
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response("event: done\ndata: {}\n\n", {
        status: 200, headers: { "Content-Type": "text/event-stream" },
      }));

    const events = [];
    for await (const event of streamChat({ courseId: "course-1", message: "hello" })) {
      events.push(event.type);
    }

    expect(events).toContain("done");
    expect(mockFetch).toHaveBeenCalledTimes(3);
    expect(mockFetch.mock.calls[1][0]).toBe("/api/auth/refresh");
    const [url, init] = mockFetch.mock.calls[2] as [string, RequestInit];
    expect(url).toBe("/api/chat");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer fresh-token");
    expect(init.body).toBe(mockFetch.mock.calls[0][1].body);
  });
});
