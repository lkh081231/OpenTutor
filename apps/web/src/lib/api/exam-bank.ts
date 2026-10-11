import {
  request,
  requestBlob,
  API_BASE,
  buildSecureRequestInit,
  parseApiError,
} from "./client";
import { fetchWithAuth } from "@/lib/auth";

export interface BankIssue {
  code: string;
  severity: "warning" | "error";
  path: string;
  question_number: number | null;
}
export interface BankSummary {
  id: string;
  name: string;
  question_count: number;
  subject: string;
  source: string;
  import_version: number;
}
export interface FacetValue {
  value: string;
  label: string;
  count: number;
}
export interface BankFacets {
  subjects: FacetValue[];
  sources: FacetValue[];
  years: FacetValue[];
  chapters: FacetValue[];
}
export interface QuestionSummary {
  id: string;
  bank_id: string;
  bank_name: string;
  label: string;
  subject: string;
  source: string;
  year: number | null;
  chapters: string[];
  paper_ref: string | null;
  question_number: number;
  source_path: string;
  version_id: string;
  version_number: number;
  issues: BankIssue[];
  preview_only: true;
  purpose: "unassigned";
  student_view_eligible: false;
}
export interface BankResource {
  id: string;
  reference: string;
  path: string;
  sha256: string;
  size_bytes: number;
  media_type: string;
  url: string;
}
export interface SourceDocument {
  path: string;
  sha256: string;
  raw_markdown: string;
  years: number[];
}
export interface QuestionDetail extends QuestionSummary {
  source_header: string;
  raw_markdown: string;
  source_sha256: string;
  subquestions: {
    path: string[];
    parent_path: string[] | null;
    raw_markdown: string;
    prompt_markdown: string;
    answer_markdown: string | null;
    chapters: string[];
    learning_outcomes: string[];
    printed_marks: number | null;
    withdrawn: boolean;
  }[];
  resources: BankResource[];
  mirrors: {
    source_path: string;
    question_number: number;
    canonical_identity: string;
    canonical_path: string;
  }[];
  versions: {
    id: string;
    version_number: number;
    created_at: string;
    content_sha256: string;
  }[];
  syllabus: SourceDocument | null;
  general_ms: SourceDocument | null;
  unsupported_renderers: string[];
}
export interface QuestionPage {
  items: QuestionSummary[];
  total: number;
  page: number;
  page_size: number;
}
export interface ImportResult {
  bank: BankSummary;
  reused: boolean;
  report: Record<string, unknown>;
  import_version: number;
}
export type BankFilters = Partial<
  Record<"bank_id" | "subject" | "source" | "year" | "chapter", string>
>;
function query(filters: BankFilters & { page?: number; page_size?: number }) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  return params.size ? `?${params}` : "";
}
export const listExamBanks = () => request<BankSummary[]>("/exam-banks");
export const getBankFacets = (bank_id?: string) =>
  request<BankFacets>(`/exam-banks/facets${query({ bank_id })}`);
export const listBankQuestions = (filters: BankFilters, page: number) =>
  request<QuestionPage>(
    `/exam-banks/questions${query({ ...filters, page, page_size: 20 })}`,
  );
export const getBankQuestion = (id: string, versionId?: string) =>
  request<QuestionDetail>(
    `/exam-banks/questions/${encodeURIComponent(id)}${versionId ? `/versions/${encodeURIComponent(versionId)}` : ""}`,
  );
export const getBankResource = (id: string) =>
  requestBlob(`/exam-banks/resources/${encodeURIComponent(id)}`);
export async function uploadExamBank(
  action: "preview" | "import",
  data: FormData,
): Promise<Record<string, unknown> | ImportResult> {
  const response = await fetchWithAuth(
    `${API_BASE}/exam-banks/${action}`,
    buildSecureRequestInit({
      method: "POST",
      body: data,
      includeJsonContentType: false,
    }),
  );
  if (!response.ok) throw await parseApiError(response);
  return response.json();
}
