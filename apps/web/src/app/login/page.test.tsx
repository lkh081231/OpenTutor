import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import LoginPage from "./page";
const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
const fetchMock = vi.fn();
beforeEach(() => { localStorage.clear(); replace.mockReset(); fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); window.history.replaceState({}, "", "/login?returnTo=%2Fexam-practice"); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function submit() {
  fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "student@example.com" } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "password123" } });
  fireEvent.click(screen.getByRole("button", { name: "登录" }));
}
it("stores the API session and enters the requested local page", async () => {
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ access_token: "access", refresh_token: "refresh" })));
  render(<LoginPage />); submit();
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/exam-practice"));
  expect(localStorage.getItem("access_token")).toBe("access");
});
it("shows failed credentials without entering the application", async () => {
  fetchMock.mockResolvedValue(new Response("{}", { status: 401 }));
  render(<LoginPage />); submit();
  expect(await screen.findByRole("alert")).toHaveTextContent("邮箱或密码不正确");
  expect(replace).not.toHaveBeenCalled();
  expect(localStorage.getItem("access_token")).toBeNull();
});
