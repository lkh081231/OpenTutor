"""Lossless block adaptation of the existing CIE Markdown convention.

This is an inspection adapter, not a student renderer or a JSON importer.
Unsupported structures remain in the raw snapshot and are explicitly reported.
"""

from __future__ import annotations
import hashlib
import re
import stat
from pathlib import Path
from schemas.exam_bank import (
    BankClassification,
    PreviewIssue,
    QuestionPreview,
    ResourcePreview,
    SubquestionPreview,
)

Q_HEADING = re.compile(r"^## Q(\d+)(?=\s|$)")
SUB_HEADING = re.compile(r"^###\s+((?:\([a-zA-Z0-9]+\))+)")
PAPER_REF = re.compile(r"^\d{4}_[msw]\d{2}_\d{2}$")
MIRROR_NOTE = re.compile(
    r"^> 本题正本在 \[`[^`]+`\]\(([^)]+)\)，此处为镜像。"
    r"\*\*不要在本文件里改它\*\* —— 改正本，再跑 `python tools/mirror\.py`。$"
)
IMAGE = re.compile(r"!\[[^\]\n]*\]\(([^)\n]+)\)")
ANSWER = re.compile(r"\*\*(?:答案|判分)\*\*")
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def structural_lines(text: str) -> list[tuple[int, str]]:
    """Return line offsets outside backtick/tilde fenced code blocks."""
    result: list[tuple[int, str]] = []
    fence_character = ""
    fence_length = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", stripped)
        if fence_character:
            if (
                match
                and match[1][0] == fence_character
                and len(match[1]) >= fence_length
                and not match[2].strip()
            ):
                fence_character = ""
        elif match:
            fence_character = match[1][0]
            fence_length = len(match[1])
        else:
            result.append(
                (offset, stripped.lstrip("\ufeff") if offset == 0 else stripped)
            )
        offset += len(line)
    return result


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_link(path: Path) -> bool:
    """Path.is_junction is unavailable on Python 3.11."""
    try:
        reparse = bool(
            getattr(path.lstat(), "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        )
    except OSError:
        reparse = False
    return path.is_symlink() or reparse or getattr(path, "is_junction", lambda: False)()


def checked_path(
    root: Path, base: Path, reference: str, *, parent: bool = False
) -> Path:
    """Only explicit mirror links may use parent segments, still inside root."""
    value = reference.replace("\\", "/")
    if (
        not value
        or value.startswith("/")
        or re.search(r"[:\x00-\x1f%?#]", value)
        or (not parent and ".." in value.split("/"))
    ):
        raise ValueError("unsafe_path")
    current = base
    for part in value.split("/"):
        current = current / part
        if is_link(current):
            raise ValueError("unsafe_path")
    resolved = (base / value).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("unsafe_path")
    return resolved


def image_resources(
    root: Path, path: Path, block: str, qn: int
) -> tuple[tuple[ResourcePreview, ...], list[PreviewIssue]]:
    issues: list[PreviewIssue] = []
    resources: list[ResourcePreview] = []
    rel = path.relative_to(root).as_posix()
    for match in IMAGE.finditer(block):
        reference = match[1]
        try:
            target = checked_path(root, path.parent, reference)
            if target.suffix.lower() not in RASTER_SUFFIXES:
                issues.append(
                    PreviewIssue("unsupported_image_resource", "error", rel, qn)
                )
                resources.append(ResourcePreview(reference, None, None, None))
                continue
            data = target.read_bytes()
        except ValueError:
            issues.append(PreviewIssue("unsafe_image_path", "error", rel, qn))
            resources.append(ResourcePreview(reference, None, None, None))
        except OSError:
            issues.append(PreviewIssue("missing_or_unreadable_image", "error", rel, qn))
            resources.append(ResourcePreview(reference, None, None, None))
        else:
            resources.append(
                ResourcePreview(
                    reference,
                    target.relative_to(root).as_posix(),
                    sha256(data),
                    len(data),
                )
            )
    # Never claim complete image coverage for syntax not parsed here.
    if re.search(
        r"<\s*(?:img|svg|image|object|iframe)\b|\bsrcset\s*=|url\s*\(", block, re.I
    ):
        issues.append(PreviewIssue("unresolved_embedded_resource", "error", rel, qn))
    if re.search(r"!\[[^\]\n]*\]\s*\[", block):
        issues.append(PreviewIssue("unresolved_reference_image", "error", rel, qn))
    if len(re.findall(r"!\[", block)) > len(list(IMAGE.finditer(block))):
        issues.append(PreviewIssue("unresolved_image_syntax", "error", rel, qn))
    return tuple(resources), issues


def comparable_body(block: str, *, mirror: bool) -> str | None:
    """Remove exactly the known generated wrapper; all body whitespace matters."""
    lines = block.splitlines(keepends=True)
    if not lines:
        return None
    if not mirror:
        return "".join(lines[1:])
    if (
        len(lines) < 3
        or lines[1].strip()
        or not MIRROR_NOTE.fullmatch(lines[2].rstrip("\r\n"))
    ):
        return None
    return "".join(lines[3:])


def adapt_markdown(
    root: Path, path: Path, classification: BankClassification
) -> tuple[list[QuestionPreview], list[PreviewIssue]]:
    raw_bytes = path.read_bytes()
    # Preserve BOM and newline spelling in every source snapshot.
    text = raw_bytes.decode("utf-8")
    structural = structural_lines(text)
    starts = [
        (offset, Q_HEADING.match(line))
        for offset, line in structural
        if Q_HEADING.match(line)
    ]
    rel = path.relative_to(root).as_posix()
    issues: list[PreviewIssue] = []
    questions: list[QuestionPreview] = []
    if not starts:
        return [], [PreviewIssue("unrecognized_question_document", "warning", rel)]
    header = text[: starts[0][0]]
    paper_ref = path.stem if PAPER_REF.fullmatch(path.stem) else None
    year = 2000 + int(paper_ref.split("_")[1][1:]) if paper_ref else None
    default_chapter = re.match(r"ch(\d+)(?:-|$)", path.parent.name)
    for index, (offset, match) in enumerate(starts):
        assert match is not None
        qn = int(match[1])
        end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        block = text[offset:end]
        heading = block.splitlines()[0]
        is_mirror = "⟨镜像" in heading
        targets = [
            m[1]
            for _, line in structural_lines(block)
            if (m := MIRROR_NOTE.fullmatch(line))
        ]
        target = targets[0] if len(targets) == 1 else None
        marks_match = re.search(r"\[(\d+)\]", heading)
        printed_marks = int(marks_match[1]) if marks_match else None
        sub_starts = [
            (pos, SUB_HEADING.match(line))
            for pos, line in structural_lines(block)
            if SUB_HEADING.match(line)
        ]
        subs: list[SubquestionPreview] = []
        seen_paths: set[tuple[str, ...]] = set()
        for sub_index, (pos, sub_match) in enumerate(sub_starts):
            assert sub_match is not None
            sub_end = (
                sub_starts[sub_index + 1][0]
                if sub_index + 1 < len(sub_starts)
                else len(block)
            )
            raw_sub = block[pos:sub_end]
            sub_heading = raw_sub.splitlines()[0]
            label = tuple(re.findall(r"\(([^)]+)\)", sub_match[1]))
            if label in seen_paths:
                issues.append(
                    PreviewIssue("duplicate_subquestion_path", "error", rel, qn)
                )
            seen_paths.add(label)
            chapter_labels = re.findall(r"\bch(\d+)\b", sub_heading)
            if not chapter_labels and default_chapter and not is_mirror:
                chapter_labels = [default_chapter[1]]
                issues.append(
                    PreviewIssue("chapter_inferred_from_directory", "warning", rel, qn)
                )
            chapters = tuple(dict.fromkeys(str(int(c)) for c in chapter_labels))
            if not chapters:
                issues.append(PreviewIssue("missing_chapter", "warning", rel, qn))
            answer_positions = [
                offset + m.start()
                for offset, line in structural_lines(raw_sub)
                if (m := ANSWER.search(line))
            ]
            answer_offset = answer_positions[0] if answer_positions else None
            raw_marks = re.search(r"\[(\d+)\]", sub_heading)
            withdrawn = "官方撤销" in sub_heading
            subs.append(
                SubquestionPreview(
                    path=label,
                    parent_path=label[:-1] if len(label) > 1 else None,
                    raw_markdown=raw_sub,
                    prompt_markdown=raw_sub[:answer_offset]
                    if answer_offset is not None
                    else raw_sub,
                    answer_markdown=raw_sub[answer_offset:]
                    if answer_offset is not None
                    else None,
                    chapters=chapters,
                    printed_marks=int(raw_marks[1]) if raw_marks else None,
                    withdrawn=withdrawn,
                )
            )
            if raw_marks and answer_offset is None and not withdrawn:
                issues.append(
                    PreviewIssue("missing_subquestion_ms", "warning", rel, qn)
                )
        for sub in subs:
            if sub.parent_path and sub.parent_path not in seen_paths:
                issues.append(
                    PreviewIssue("implicit_parent_subquestion", "warning", rel, qn)
                )
        resources, resource_issues = image_resources(root, path, header + block, qn)
        issues.extend(resource_issues)
        issues.append(PreviewIssue("missing_learning_outcomes", "warning", rel, qn))
        if not paper_ref:
            issues.append(
                PreviewIssue("missing_paper_ref_and_year", "warning", rel, qn)
            )
        if not subs:
            issues.append(
                PreviewIssue("missing_subquestion_boundaries", "warning", rel, qn)
            )
        combined_content = header + block
        if re.search(
            r"^\s*(?:`{3,}|~{3,})tikz\b|\\(?:chemfig|usepackage\{chemfig\})",
            combined_content,
            re.M,
        ):
            issues.append(
                PreviewIssue("tikz_chemfig_requires_renderer", "warning", rel, qn)
            )
        if (
            "没有官方 mark scheme" in combined_content
            or "不是 MS 原文" in combined_content
        ):
            issues.append(PreviewIssue("missing_official_ms", "error", rel, qn))
        effective_marks = None
        if "官方撤销" in block:
            issues.append(PreviewIssue("withdrawn_subquestion", "warning", rel, qn))
            effective_match = re.search(r"实际可得\s*(\d+)\s*分", block + header)
            effective_marks = int(effective_match[1]) if effective_match else None
        prompt = (
            header
            + block[: sub_starts[0][0] if sub_starts else len(block)]
            + "\n".join(sub.prompt_markdown for sub in subs)
        )
        if (
            re.search(r"(?m)^\s*\|.*\*\*", prompt)
            or "加粗为学生需要填" in combined_content
        ):
            issues.append(
                PreviewIssue("answer_embedded_in_prompt_table", "warning", rel, qn)
            )
        if is_mirror and not target:
            issues.append(
                PreviewIssue("missing_or_ambiguous_mirror_target", "error", rel, qn)
            )
        key = f"{classification.subject}\0{classification.source}\0{rel}\0{qn}"
        questions.append(
            QuestionPreview(
                identity=sha256(key.encode()),
                source_path=rel,
                source_sha256=sha256(raw_bytes),
                classification=classification,
                paper_ref=paper_ref,
                year=year,
                question_number=qn,
                source_header=header,
                raw_markdown=block,
                subquestions=tuple(subs),
                chapters=tuple(
                    sorted({c for sub in subs for c in sub.chapters}, key=int)
                ),
                resources=resources,
                printed_marks=printed_marks,
                effective_marks=effective_marks,
                mirror_target=target,
                is_mirror=is_mirror,
            )
        )
    return questions, issues


def comparable_header(header: str) -> tuple[str, ...]:
    """Remove only known per-chapter catalog furniture; keep shared premises."""
    furniture = (
        r"^# ch\d+ .* · \d{4}/\d{2} .+$",
        r"^> 题卷 `originalpdf/[^`]+` ｜ 答案 `originalpdf/[^`]+`$",
        r"^> 本卷本章共 \d+ 题 / \d+ 分：.*$",
        r"^> 本卷与 \d{4}/\d{2} 同卷（逐字一致，仅条形码与印刷码不同）$",
    )
    return tuple(
        line
        for line in header.splitlines()
        if line.strip()
        and line.strip() != "---"
        and not any(re.fullmatch(pattern, line) for pattern in furniture)
    )


def comparable_title(block: str, *, mirror: bool) -> bool:
    """Only known Q/marks/chapter catalog suffixes may be treated as furniture."""
    heading = block.splitlines()[0]
    if mirror:
        pattern = r"## Q\d+ \[\d+\]\s*⟨镜像 · 主章 ch\d+ [^⟩]+⟩"
    else:
        pattern = r"## Q\d+ \[\d+\]\s*(?:[（(]兼 ch[^)）]+[)）])?"
    return re.fullmatch(pattern, heading) is not None
