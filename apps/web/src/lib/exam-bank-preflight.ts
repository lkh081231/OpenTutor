import type { BankIssue } from "./api/exam-bank";

function isIssue(value: unknown): value is BankIssue {
  if (!value || typeof value !== "object") return false;
  const issue = value as Record<string, unknown>;
  return (
    typeof issue.code === "string" &&
    typeof issue.path === "string" &&
    (issue.severity === "error" || issue.severity === "warning") &&
    (issue.question_number === null || Number.isInteger(issue.question_number))
  );
}

export function preflightIssues(report?: Record<string, unknown>): BankIssue[] {
  return Array.isArray(report?.issues) ? report.issues.filter(isIssue) : [];
}

/** Match the server's narrow content-gap exception; unknown errors fail closed. */
export function canImportPreflight(report?: Record<string, unknown>): boolean {
  if (
    !report ||
    report.mode !== "markdown_dry_run" ||
    report.preview_only !== true ||
    report.purpose !== "unassigned" ||
    report.student_view_eligible !== false ||
    !Number.isInteger(report.error_count) ||
    (report.error_count as number) < 0 ||
    !Array.isArray(report.issues) ||
    !report.issues.every(isIssue)
  )
    return false;
  const errors = report.issues.filter((issue) => issue.severity === "error");
  return (
    errors.length === report.error_count &&
    errors.every((issue) => issue.code === "missing_official_ms")
  );
}
