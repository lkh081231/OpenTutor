"""Deterministic read-only bank preflight and metadata-only report."""

from __future__ import annotations
import os
import re
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from schemas.exam_bank import (
    BankClassification,
    BankPreview,
    DocumentPreview,
    MirrorPreview,
    PreviewIssue,
    QuestionPreview,
)
from services.exam_bank.markdown_adapter import (
    adapt_markdown,
    checked_path,
    comparable_body,
    comparable_header,
    comparable_title,
    is_link,
    sha256,
)


def _document(
    root: Path, reference: str | None, kind: str, issues: list[PreviewIssue]
) -> DocumentPreview | None:
    if reference is None:
        issues.append(PreviewIssue(f"missing_{kind}", "warning", ""))
        return None
    try:
        path = checked_path(root, root, reference)
        data = path.read_bytes()
        text = data.decode("utf-8")
    except UnicodeError:
        issues.append(PreviewIssue(f"unreadable_{kind}_encoding", "error", ""))
        return None
    except ValueError:
        issues.append(PreviewIssue(f"unsafe_{kind}_path", "error", ""))
        return None
    except OSError:
        issues.append(PreviewIssue(f"missing_or_unreadable_{kind}", "warning", ""))
        return None
    years: set[int] = set()
    if kind == "syllabus":
        # Version evidence comes only from document headings, never outcome text.
        for line in text.splitlines()[:8]:
            if line.lstrip("\ufeff").startswith("#"):
                years.update(int(year) for year in re.findall(r"\b20\d{2}\b", line))
                for first, last in re.findall(
                    r"\b(20\d{2})\s*[–-]\s*(20\d{2})\b", line
                ):
                    if 0 <= int(last) - int(first) <= 20:
                        years.update(range(int(first), int(last) + 1))
        if not years:
            issues.append(PreviewIssue("unknown_syllabus_years", "warning", reference))
    return DocumentPreview(
        path.relative_to(root).as_posix(), sha256(data), text, tuple(sorted(years))
    )


def _files(root: Path, directory: Path, issues: list[PreviewIssue]) -> list[Path]:
    files: list[Path] = []

    def walk_error(_: OSError) -> None:
        issues.append(PreviewIssue("unreadable_question_directory", "error", ""))

    for base, dirs, names in os.walk(directory, followlinks=False, onerror=walk_error):
        for name in sorted(dirs):
            child = Path(base) / name
            if is_link(child):
                issues.append(
                    PreviewIssue(
                        "unsafe_directory_link",
                        "error",
                        child.relative_to(root).as_posix(),
                    )
                )
                dirs.remove(name)
        dirs.sort()
        for name in sorted(names):
            child = Path(base) / name
            if child.suffix.lower() != ".md":
                continue
            if is_link(child):
                issues.append(
                    PreviewIssue(
                        "unsafe_markdown_link",
                        "error",
                        child.relative_to(root).as_posix(),
                    )
                )
            else:
                files.append(child)
    return files


def preview_bank(
    root: Path | str,
    *,
    subject: str,
    source: str,
    question_dir: str = "passyear/extracted",
    syllabus_path: str | None = "reference.md",
    general_ms_path: str | None = None,
) -> BankPreview:
    """Inspect sources without writes, databases, LLM calls or pool assignment.

    subject/source are explicit caller classifications. This adapter recognizes
    CIE paper filenames, not arbitrary Markdown schemas or final JSON delivery.
    """
    if not subject.strip() or not source.strip():
        raise ValueError("subject_and_source_required")
    classification = BankClassification(subject.strip(), source.strip())
    original_root = Path(root)
    if is_link(original_root):
        raise ValueError("unsafe_root")
    root = original_root.resolve()
    if not root.is_dir():
        raise ValueError("missing_root")
    directory = checked_path(root, root, question_dir)
    if not directory.is_dir():
        raise ValueError("missing_question_directory")
    issues: list[PreviewIssue] = []
    syllabus = _document(root, syllabus_path, "syllabus", issues)
    general_ms = _document(root, general_ms_path, "general_ms", issues)
    paths = _files(root, directory, issues)
    candidates: list[QuestionPreview] = []
    for path in paths:
        try:
            questions, file_issues = adapt_markdown(root, path, classification)
        except (OSError, UnicodeError):
            issues.append(
                PreviewIssue(
                    "unreadable_markdown", "error", path.relative_to(root).as_posix()
                )
            )
            continue
        candidates.extend(questions)
        issues.extend(file_issues)
    canonical = [question for question in candidates if not question.is_mirror]
    mirror_candidates = [question for question in candidates if question.is_mirror]
    # Keep duplicates and conflicts inspectable; never silently select a winner.
    identities = Counter(
        (q.paper_ref, q.question_number) for q in canonical if q.paper_ref
    )
    by_location: dict[tuple[str, int], list[QuestionPreview]] = {}
    for question in canonical:
        by_location.setdefault(
            (question.source_path, question.question_number), []
        ).append(question)
        if (
            question.paper_ref
            and identities[(question.paper_ref, question.question_number)] > 1
        ):
            issues.append(
                PreviewIssue(
                    "duplicate_canonical_identity",
                    "error",
                    question.source_path,
                    question.question_number,
                )
            )
        if (
            syllabus
            and syllabus.years
            and question.year
            and question.year not in syllabus.years
        ):
            issues.append(
                PreviewIssue(
                    "question_outside_syllabus_years",
                    "warning",
                    question.source_path,
                    question.question_number,
                )
            )
    mirrors: list[MirrorPreview] = []
    unresolved: list[QuestionPreview] = []
    for mirror in mirror_candidates:
        qn, rel = mirror.question_number, mirror.source_path
        target: QuestionPreview | None = None
        error = None
        if not mirror.mirror_target:
            error = "unresolved_mirror_target"
        else:
            try:
                target_path = checked_path(
                    root, (root / rel).parent, mirror.mirror_target, parent=True
                )
                target_rel = target_path.relative_to(root).as_posix()
            except ValueError:
                error = "unsafe_mirror_target"
            else:
                targets = by_location.get((target_rel, qn), [])
                if len(targets) != 1:
                    error = "missing_or_ambiguous_mirror_canonical"
                else:
                    target = targets[0]
        if target and not error:
            if (
                not mirror.paper_ref
                or mirror.paper_ref != target.paper_ref
                or identities[(target.paper_ref, target.question_number)] != 1
            ):
                error = "mirror_identity_mismatch"
            elif (
                mirror.printed_marks != target.printed_marks
                or mirror.effective_marks != target.effective_marks
            ):
                error = "mirror_marks_conflict"
            elif not comparable_title(
                mirror.raw_markdown, mirror=True
            ) or not comparable_title(target.raw_markdown, mirror=False):
                error = "mirror_unrecognized_title"
            elif comparable_header(mirror.source_header) != comparable_header(
                target.source_header
            ):
                error = "mirror_shared_context_conflict"
            else:
                mirror_body = comparable_body(mirror.raw_markdown, mirror=True)
                canonical_body = comparable_body(target.raw_markdown, mirror=False)
                if mirror_body is None or mirror_body != canonical_body:
                    error = "mirror_content_conflict"
                elif (
                    any(
                        resource.sha256 is None
                        for resource in mirror.resources + target.resources
                    )
                    or any(
                        issue.severity == "error"
                        and issue.path in {rel, target.source_path}
                        and issue.question_number == qn
                        and "resource" in issue.code
                        for issue in issues
                    )
                    or any(
                        issue.code
                        in {"unresolved_reference_image", "unresolved_image_syntax"}
                        and issue.path in {rel, target.source_path}
                        and issue.question_number == qn
                        for issue in issues
                    )
                ):
                    error = "mirror_unverified_resources"
                elif [(r.reference, r.sha256) for r in mirror.resources] != [
                    (r.reference, r.sha256) for r in target.resources
                ]:
                    error = "mirror_resource_conflict"
        if error:
            unresolved.append(mirror)
            issues.append(PreviewIssue(error, "error", rel, qn))
        elif target:
            mirrors.append(
                MirrorPreview(rel, qn, target.identity, target.source_path, mirror)
            )
    return BankPreview(
        classification,
        tuple(canonical),
        tuple(mirrors),
        tuple(unresolved),
        tuple(
            sorted(
                set(issues),
                key=lambda issue: (issue.path, issue.question_number or 0, issue.code),
            )
        ),
        syllabus,
        general_ms,
        len(paths),
    )


def metadata_report(preview: BankPreview) -> dict[str, object]:
    """Explicit allowlist: do not serialize the raw-content dataclass tree."""
    all_questions = preview.questions + preview.unresolved_mirrors
    return {
        "mode": "markdown_dry_run",
        "preview_only": True,
        "purpose": "unassigned",
        "student_view_eligible": False,
        "subject": preview.classification.subject,
        "source": preview.classification.source,
        "scanned_markdown_files": preview.scanned_files,
        "canonical_question_blocks": len(preview.questions),
        "distinct_canonical_identities": len(
            {question.identity for question in preview.questions}
        ),
        "verified_mirrors": len(preview.mirrors),
        "unresolved_mirrors": len(preview.unresolved_mirrors),
        "canonical_papers": len(
            {q.paper_ref for q in preview.questions if q.paper_ref}
        ),
        "canonical_years": sorted({q.year for q in preview.questions if q.year}),
        "canonical_image_references": sum(len(q.resources) for q in preview.questions),
        "hashed_canonical_image_references": sum(
            r.sha256 is not None for q in preview.questions for r in q.resources
        ),
        "syllabus_years": list(preview.syllabus.years) if preview.syllabus else [],
        "general_ms_loaded": preview.general_ms is not None,
        "issue_counts": dict(
            sorted(Counter(issue.code for issue in preview.issues).items())
        ),
        "error_count": sum(issue.severity == "error" for issue in preview.issues),
        "all_content_unreviewed": all(
            not q.student_view_eligible for q in all_questions
        ),
        "issues": [asdict(issue) for issue in preview.issues],
    }
