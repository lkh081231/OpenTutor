import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { listBankQuestions, uploadExamBank } from "./exam-bank";

describe("exam bank API contract", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    window.localStorage.setItem("access_token", "synthetic-token");
    document.cookie = "csrf_token=synthetic-csrf; Path=/";
  });
  afterEach(() => {
    window.localStorage.clear();
    document.cookie = "csrf_token=; Max-Age=0; Path=/";
    vi.unstubAllGlobals();
  });
  it("encodes filters, unknown year and pagination using the agreed endpoint", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ items: [], total: 0, page: 2, page_size: 20 }),
      ),
    );
    await listBankQuestions(
      { subject: "Synthetic & subject", year: "unknown", chapter: "Chapter 1" },
      2,
    );
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    const query = new URL(url, "https://synthetic.invalid").searchParams;
    expect(url).toContain("/api/exam-banks/questions?");
    expect(query.get("subject")).toBe("Synthetic & subject");
    expect(query.get("year")).toBe("unknown");
    expect(query.get("page")).toBe("2");
    expect(query.get("page_size")).toBe("20");
    expect(new Headers(options.headers).get("Authorization")).toBe(
      "Bearer synthetic-token",
    );
  });
  it("sends multipart unchanged with auth, CSRF and cookies", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error_count: 0 })),
    );
    const data = new FormData();
    data.set("file", new File(["synthetic"], "bank.zip"));
    data.set("subject", "Synthetic");
    data.set("source", "Synthetic");
    await uploadExamBank("preview", data);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/exam-banks/preview");
    expect(options.method).toBe("POST");
    expect(options.body).toBe(data);
    expect(options.credentials).toBe("include");
    const headers = new Headers(options.headers);
    expect(headers.get("Authorization")).toBe("Bearer synthetic-token");
    expect(headers.get("X-CSRF-Token")).toBe("synthetic-csrf");
    expect(headers.has("Content-Type")).toBe(false);
  });
  it("does not automatically retry import on a server failure", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Synthetic conflict" }), {
        status: 503,
      }),
    );
    await expect(uploadExamBank("import", new FormData())).rejects.toThrow(
      "Synthetic conflict",
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
