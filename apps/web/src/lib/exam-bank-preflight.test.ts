import { describe, expect, it } from "vitest";
import { canImportPreflight, preflightIssues } from "./exam-bank-preflight";

const base = {
  mode: "markdown_dry_run",
  preview_only: true,
  purpose: "unassigned",
  student_view_eligible: false,
  error_count: 0,
  issues: [],
};
const issue = (code: string) => ({
  code,
  severity: "error",
  path: "synthetic.md",
  question_number: 1,
});
describe("management preflight policy", () => {
  it("allows valid reports and the exact official-MS content-gap exception", () => {
    expect(canImportPreflight(base)).toBe(true);
    expect(
      canImportPreflight({
        ...base,
        error_count: 1,
        issues: [issue("missing_official_ms")],
      }),
    ).toBe(true);
  });
  it.each([
    "unsafe_resource_path",
    "duplicate_canonical_identity",
    "unknown_new_error",
  ])("blocks structural or unknown error %s", (code) => {
    expect(
      canImportPreflight({ ...base, error_count: 1, issues: [issue(code)] }),
    ).toBe(false);
  });
  it("blocks incomplete, mismatched and malformed reports", () => {
    expect(canImportPreflight()).toBe(false);
    expect(canImportPreflight({ error_count: 0, issues: [] })).toBe(false);
    expect(
      canImportPreflight({
        ...base,
        error_count: 0,
        issues: [issue("missing_official_ms")],
      }),
    ).toBe(false);
    expect(canImportPreflight({ ...base, error_count: 1, issues: [] })).toBe(
      false,
    );
    expect(canImportPreflight({ ...base, issues: [null] })).toBe(false);
    expect(
      preflightIssues({
        ...base,
        issues: [null, issue("missing_official_ms")],
      }),
    ).toHaveLength(1);
  });
});
