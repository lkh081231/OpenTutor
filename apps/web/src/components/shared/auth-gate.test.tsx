import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthGate } from "./auth-gate";
const { replace, router } = vi.hoisted(() => { const replace = vi.fn(); return { replace, router: { replace } }; });
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/exam-practice" }));
const fetchMock = vi.fn();
beforeEach(() => { localStorage.clear(); sessionStorage.clear(); replace.mockReset(); fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it("keeps the existing application accessible when auth is disabled", async () => {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ auth_enabled: false })));
  render(<AuthGate><div>Original application</div></AuthGate>);
  expect(await screen.findByText("Original application")).toBeInTheDocument();
  expect(replace).not.toHaveBeenCalled();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
it("protects the application when auth is enabled and no session exists", async () => {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ auth_enabled: true })));
  render(<AuthGate><div>Protected application</div></AuthGate>);
  await waitFor(() => expect(replace).toHaveBeenCalledWith(expect.stringContaining("/login?returnTo=")));
  expect(screen.queryByText("Protected application")).not.toBeInTheDocument();
});
it("keeps protected content hidden if health configuration is unavailable", async () => {
  fetchMock.mockResolvedValueOnce(new Response("{}", { status: 503 }));
  render(<AuthGate><div>Protected application</div></AuthGate>);
  expect(await screen.findByRole("alert")).toHaveTextContent("无法连接服务");
  expect(screen.queryByText("Protected application")).not.toBeInTheDocument();
});
