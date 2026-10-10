"""Internal preview records: source text is never approved for student use."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class BankClassification:
    subject: str
    source: str


@dataclass(frozen=True)
class PreviewIssue:
    code: str
    severity: Literal["warning", "error"]
    path: str
    question_number: int | None = None


@dataclass(frozen=True)
class ResourcePreview:
    reference: str
    path: str | None
    sha256: str | None
    size_bytes: int | None


@dataclass(frozen=True)
class SubquestionPreview:
    path: tuple[str, ...]
    parent_path: tuple[str, ...] | None
    raw_markdown: str
    prompt_markdown: str
    answer_markdown: str | None
    chapters: tuple[str, ...]
    learning_outcomes: tuple[str, ...] = ()
    printed_marks: int | None = None
    withdrawn: bool = False


@dataclass(frozen=True)
class QuestionPreview:
    identity: str
    source_path: str
    source_sha256: str
    classification: BankClassification
    paper_ref: str | None
    year: int | None
    question_number: int
    source_header: str
    raw_markdown: str
    subquestions: tuple[SubquestionPreview, ...]
    chapters: tuple[str, ...]
    resources: tuple[ResourcePreview, ...]
    printed_marks: int | None
    effective_marks: int | None
    mirror_target: str | None = None
    is_mirror: bool = False
    preview_only: Literal[True] = field(default=True, init=False)
    purpose: Literal["unassigned"] = field(default="unassigned", init=False)
    student_view_eligible: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True)
class MirrorPreview:
    source_path: str
    question_number: int
    canonical_identity: str
    canonical_path: str
    source: QuestionPreview


@dataclass(frozen=True)
class DocumentPreview:
    path: str
    sha256: str
    raw_markdown: str
    years: tuple[int, ...] = ()


@dataclass(frozen=True)
class BankPreview:
    classification: BankClassification
    questions: tuple[QuestionPreview, ...]
    mirrors: tuple[MirrorPreview, ...]
    unresolved_mirrors: tuple[QuestionPreview, ...]
    issues: tuple[PreviewIssue, ...]
    syllabus: DocumentPreview | None
    general_ms: DocumentPreview | None
    scanned_files: int
    preview_only: Literal[True] = field(default=True, init=False)
    purpose: Literal["unassigned"] = field(default="unassigned", init=False)
    student_view_eligible: Literal[False] = field(default=False, init=False)
