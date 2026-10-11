"""Owner-only management API; these records are never student practice."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ManagementRecord(BaseModel):
    preview_only: Literal[True] = True
    purpose: Literal["unassigned"] = "unassigned"
    student_view_eligible: Literal[False] = False


class Issue(BaseModel):
    code: str
    severity: Literal["warning", "error"]
    path: str
    question_number: int | None = None


class BankSummary(ManagementRecord):
    id: UUID
    name: str
    current_import_id: UUID
    import_version: int
    question_count: int
    subject: str
    source: str
    created_at: datetime


class ImportResult(ManagementRecord):
    bank: BankSummary
    import_id: UUID
    import_version: int
    manifest_sha256: str
    reused: bool
    report: dict[str, object]


class FacetValue(BaseModel):
    value: str
    label: str
    count: int


class BankFacets(BaseModel):
    subjects: list[FacetValue]
    sources: list[FacetValue]
    years: list[FacetValue]
    chapters: list[FacetValue]


class QuestionSummary(ManagementRecord):
    id: UUID
    bank_id: UUID
    bank_name: str
    label: str
    subject: str
    source: str
    year: int | None
    chapters: list[str]
    paper_ref: str | None
    question_number: int
    source_path: str
    version_id: UUID
    version_number: int
    issues: list[Issue]


class QuestionPage(BaseModel):
    items: list[QuestionSummary]
    total: int
    page: int
    page_size: int


class Resource(BaseModel):
    id: UUID
    reference: str
    path: str
    sha256: str
    size_bytes: int
    media_type: str
    url: str


class Subquestion(BaseModel):
    path: list[str]
    parent_path: list[str] | None
    raw_markdown: str
    prompt_markdown: str
    answer_markdown: str | None
    chapters: list[str]
    learning_outcomes: list[str]
    printed_marks: int | None
    withdrawn: bool


class SourceDocument(BaseModel):
    path: str
    sha256: str
    raw_markdown: str
    years: list[int]


class QuestionVersionSummary(BaseModel):
    id: UUID
    version_number: int
    created_at: datetime
    content_sha256: str


class MirrorSource(BaseModel):
    source_path: str
    question_number: int
    canonical_identity: str
    canonical_path: str
    source: dict[str, object]


class QuestionDetail(QuestionSummary):
    source_header: str
    raw_markdown: str
    source_sha256: str
    subquestions: list[Subquestion]
    resources: list[Resource]
    mirrors: list[MirrorSource]
    versions: list[QuestionVersionSummary]
    syllabus: SourceDocument | None
    general_ms: SourceDocument | None
    unsupported_renderers: list[str] = Field(default_factory=list)
