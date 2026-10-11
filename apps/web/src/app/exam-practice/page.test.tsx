import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Page from "./page";
import type { QuestionDetail, QuestionSummary } from "@/lib/api/exam-bank";

const api = vi.hoisted(() => ({
  listExamBanks: vi.fn(),
  getBankFacets: vi.fn(),
  listBankQuestions: vi.fn(),
  getBankQuestion: vi.fn(),
  uploadExamBank: vi.fn(),
}));
vi.mock("@/lib/api/exam-bank", () => api);
vi.mock("@/components/shared/exam-markdown", () => ({
  ExamMarkdown: ({ content }: { content: string }) => <div>{content}</div>,
}));
const summary: QuestionSummary = {
  id: "question-one",
  bank_id: "bank-one",
  bank_name: "Synthetic bank",
  label: "Synthetic Q1",
  subject: "Synthetic Chemistry",
  source: "Synthetic source",
  year: 2026,
  chapters: ["Chapter One"],
  paper_ref: "synthetic-paper",
  question_number: 1,
  source_path: "synthetic.md",
  version_id: "v2",
  version_number: 2,
  issues: [],
  preview_only: true,
  purpose: "unassigned",
  student_view_eligible: false,
};
const detail: QuestionDetail = {
  ...summary,
  raw_markdown: "Original source <sub>2</sub>\n\nAnswer included.",
  source_header: "Shared mother-question context",
  source_sha256: "synthetic-hash",
  subquestions: [],
  resources: [],
  mirrors: [],
  versions: [
    {
      id: "v1",
      version_number: 1,
      created_at: "2026-01-01T00:00:00Z",
      content_sha256: "old-hash",
    },
  ],
  syllabus: null,
  general_ms: null,
  unsupported_renderers: [],
};
describe("bank management browser", () => {
  beforeEach(() => {
    Object.values(api).forEach((mock) => mock.mockReset());
    api.listExamBanks.mockResolvedValue([
      { id: "bank-one", name: "Synthetic bank" },
    ]);
    api.getBankFacets.mockResolvedValue({
      subjects: [
        { value: "synthetic", label: "Synthetic Chemistry", count: 21 },
      ],
      sources: [],
      years: [],
      chapters: [{ value: "unknown", label: "未知", count: 1 }],
    });
    api.listBankQuestions.mockImplementation((_filters, page) =>
      Promise.resolve({ items: [summary], total: 21, page, page_size: 20 }),
    );
    api.getBankQuestion.mockResolvedValue(detail);
  });
  afterEach(() => cleanup());
  it("resets pagination when filters change and offers no practice action", async () => {
    render(<Page />);
    await screen.findByRole("button", { name: /Synthetic Q1/ });
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() =>
      expect(api.listBankQuestions).toHaveBeenLastCalledWith({}, 2),
    );
    fireEvent.change(screen.getByLabelText("章节"), {
      target: { value: "unknown" },
    });
    await waitFor(() =>
      expect(api.listBankQuestions).toHaveBeenLastCalledWith(
        { chapter: "unknown" },
        1,
      ),
    );
    expect(screen.getByRole("note")).toHaveTextContent("含答案");
    expect(
      screen.queryByRole("button", { name: /开始练习|提交答案/ }),
    ).toBeNull();
  });
  it("shows complete context, exact source and version history", async () => {
    render(<Page />);
    fireEvent.click(
      await screen.findByRole("button", { name: /Synthetic Q1/ }),
    );
    await screen.findByText("Shared mother-question context");
    fireEvent.click(screen.getByRole("button", { name: "查看原文" }));
    expect(
      screen.getByText(
        (_, node) =>
          node?.tagName === "PRE" && node.textContent === detail.raw_markdown,
      ),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "版本历史" }), {
      target: { value: "v1" },
    });
    await waitFor(() =>
      expect(api.getBankQuestion).toHaveBeenLastCalledWith(
        "question-one",
        "v1",
      ),
    );
  });
  it("reports list failures and retries", async () => {
    api.listBankQuestions.mockRejectedValueOnce(new Error("Unavailable"));
    render(<Page />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "题目列表加载失败",
    );
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await screen.findByRole("button", { name: /Synthetic Q1/ });
  });
  it("can select the same question again and retry a failed detail request", async () => {
    api.getBankQuestion.mockRejectedValueOnce(new Error("Unavailable"));
    render(<Page />);
    const question = await screen.findByRole("button", {
      name: /Synthetic Q1/,
    });
    fireEvent.click(question);
    fireEvent.click(await screen.findByRole("button", { name: "重试详情" }));
    await screen.findByText("Shared mother-question context");
    fireEvent.click(question);
    await screen.findByText("Shared mother-question context");
    expect(api.getBankQuestion).toHaveBeenCalledTimes(3);
  });
  it("invalidates a successful preflight when archive classifications change", async () => {
    api.uploadExamBank.mockResolvedValue({
      mode: "markdown_dry_run",
      preview_only: true,
      purpose: "unassigned",
      student_view_eligible: false,
      error_count: 0,
      canonical_question_blocks: 1,
      verified_mirrors: 0,
      issues: [],
    });
    render(<Page />);
    fireEvent.change(screen.getByLabelText("ZIP 文件"), {
      target: {
        files: [
          new File(["synthetic"], "bank.zip", { type: "application/zip" }),
        ],
      },
    });
    fireEvent.change(screen.getAllByLabelText("学科")[0], {
      target: { value: "Synthetic" },
    });
    fireEvent.change(screen.getAllByLabelText("来源")[0], {
      target: { value: "Synthetic" },
    });
    fireEvent.change(screen.getByLabelText("题库名称"), {
      target: { value: "Synthetic bank" },
    });
    fireEvent.click(screen.getByRole("button", { name: "预检 ZIP" }));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "确认管理导入" }),
      ).toBeEnabled(),
    );
    fireEvent.change(screen.getByLabelText("题文目录"), {
      target: { value: "changed" },
    });
    expect(screen.getByRole("button", { name: "确认管理导入" })).toBeDisabled();
  });
  it("retains a new-bank idempotency key after a failed import", async () => {
    api.uploadExamBank.mockImplementation((action) =>
      action === "preview"
        ? Promise.resolve({
            mode: "markdown_dry_run",
            preview_only: true,
            purpose: "unassigned",
            student_view_eligible: false,
            error_count: 0,
            issues: [],
          })
        : Promise.reject(new Error("Network unavailable")),
    );
    render(<Page />);
    fireEvent.change(screen.getByLabelText("ZIP 文件"), {
      target: { files: [new File(["synthetic"], "bank.zip")] },
    });
    fireEvent.change(screen.getAllByLabelText("学科")[0], {
      target: { value: "Synthetic" },
    });
    fireEvent.change(screen.getAllByLabelText("来源")[0], {
      target: { value: "Synthetic" },
    });
    fireEvent.change(screen.getByLabelText("题库名称"), {
      target: { value: "Synthetic bank" },
    });
    fireEvent.click(screen.getByRole("button", { name: "预检 ZIP" }));
    const importButton = screen.getByRole("button", { name: "确认管理导入" });
    await waitFor(() => expect(importButton).toBeEnabled());
    fireEvent.click(importButton);
    await screen.findByText("Network unavailable");
    const firstKey = (api.uploadExamBank.mock.calls[1][1] as FormData).get(
      "idempotency_key",
    );
    expect(firstKey).toMatch(/^[a-f0-9-]{36}$/);
    fireEvent.click(importButton);
    await waitFor(() => expect(api.uploadExamBank).toHaveBeenCalledTimes(3));
    expect(
      (api.uploadExamBank.mock.calls[2][1] as FormData).get("idempotency_key"),
    ).toBe(firstKey);
  });
});
