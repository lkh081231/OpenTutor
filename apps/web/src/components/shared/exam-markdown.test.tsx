import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExamMarkdown } from "./exam-markdown";
import type { BankResource } from "@/lib/api/exam-bank";

const getResource = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/exam-bank", () => ({ getBankResource: getResource }));
const resource: BankResource = {
  id: "asset-one",
  reference: "images/plot.png",
  path: "images/plot.png",
  sha256: "hash",
  size_bytes: 10,
  media_type: "image/png",
  url: "/api/exam-banks/resources/asset-one",
};
describe("exam Markdown safety and fidelity", () => {
  beforeEach(() => {
    getResource.mockReset();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:asset"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
  });
  afterEach(() => cleanup());
  it("renders tables, exact safe subscripts and math while ignoring arbitrary HTML", () => {
    const { container } = render(
      <ExamMarkdown
        resources={[]}
        content={
          'H<sub>2</sub>O and x<sup>2</sup> $x^2$\n\n| Atom | Count |\n|---|---|\n| H | 2 |\n\n<script>alert(1)</script>\n\n<img src="https://evil.invalid/a" onerror="alert(1)">'
        }
      />,
    );
    expect(container.querySelector("sub")).toHaveTextContent("2");
    expect(container.querySelector("sup")).toHaveTextContent("2");
    expect(screen.getByRole("table")).toHaveTextContent("Atom");
    expect(container.querySelector(".katex")).toBeTruthy();
    expect(container.querySelector("script, img")).toBeNull();
  });
  it("blocks remote images and links and displays unsupported diagram source", async () => {
    const { container } = render(
      <ExamMarkdown
        resources={[resource]}
        content={
          "![remote](https://evil.invalid/a.png)\n\n[external](https://evil.invalid/)\n\n```chemfig\nC(-H)-O\n```\n\n```tikz\n\\draw (0,0)--(1,1);\n```"
        }
      />,
    );
    await waitFor(() =>
      expect(screen.getByText(/资源不可用或被阻止/)).toBeInTheDocument(),
    );
    expect(getResource).not.toHaveBeenCalled();
    expect(container.querySelector("a, img")).toBeNull();
    expect(screen.getByText(/chemfig 源码/)).toBeInTheDocument();
    expect(screen.getByText(/tikz 源码/)).toBeInTheDocument();
    expect(screen.getByText("C(-H)-O")).toBeInTheDocument();
  });
  it("fetches only listed assets and releases URLs on replacement and unmount", async () => {
    getResource.mockResolvedValue({
      blob: new Blob(["image"]),
      contentType: "image/png",
    });
    const { rerender, unmount } = render(
      <ExamMarkdown
        resources={[resource]}
        content="![plot](images/plot.png)"
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("img")).toHaveAttribute("src", "blob:asset"),
    );
    expect(getResource).toHaveBeenCalledWith("asset-one");
    rerender(<ExamMarkdown resources={[]} content="no image" />);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:asset");
    unmount();
  });
  it("does not create or retain an object URL when a request finishes after unmount", async () => {
    let resolve: (value: {
      blob: Blob;
      contentType: string;
    }) => void = () => {};
    getResource.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    const { unmount } = render(
      <ExamMarkdown
        resources={[resource]}
        content="![plot](images/plot.png)"
      />,
    );
    unmount();
    resolve({ blob: new Blob(["late"]), contentType: "image/png" });
    await Promise.resolve();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
