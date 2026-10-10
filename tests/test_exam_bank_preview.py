"""Synthetic behavior tests for read-only Markdown preflight (also pytest collectable)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from services.exam_bank.preview import metadata_report, preview_bank

BODY = "\nShared synthetic premise.\n\n### (a) Parent context.\n\n### (a)(i) [1] · ch1 ch2\n\nSynthetic prompt H₂O $x^2$.\n\n**答案** — synthetic answer\n**判分** — allow equivalent answer\n"


def canonical(qn: int = 1, body: str = BODY, marks: int = 1) -> str:
    return f"## Q{qn} [{marks}]" + body


def mirrored(
    qn: int = 1,
    body: str = BODY,
    target: str = "../ch01-a/9701_s25_21.md",
    marks: int = 1,
) -> str:
    note = (
        f"> 本题正本在 [`ch01-a/9701_s25_21.md`]({target})，此处为镜像。"
        "**不要在本文件里改它** —— 改正本，再跑 `python tools/mirror.py`。"
    )
    return (
        f"## Q{qn} [{marks}]　⟨镜像 · 主章 ch1 Synthetic⟩\n\n{note}\n"
        + body.removeprefix("\n")
    )


class BankPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write(
            "reference.md",
            "# Synthetic syllabus\n## Subject content (2025 / 2026 / 2027)\n",
        )
        (self.root / "passyear/extracted").mkdir(parents=True)

    def write(self, rel: str, content: str | bytes) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        return path

    def preview(self):
        return preview_bank(
            self.root, subject="Chemistry", source="Synthetic Cambridge"
        )

    def codes(self, preview=None) -> set[str]:
        return {issue.code for issue in (preview or self.preview()).issues}

    def test_multi_question_nested_context_and_source_bytes(self):
        text = (
            "\ufeff# Source\r\n\r\nShared preamble.\r\n"
            + canonical()
            + "\n"
            + canonical(2)
        )
        path = self.write("passyear/extracted/ch01-a/9701_s25_21.md", text)
        before = path.read_bytes()
        preview = self.preview()
        self.assertEqual(len(preview.questions), 2)
        self.assertTrue(
            all(
                q.source_header == text[: text.index("## Q1")]
                for q in preview.questions
            )
        )
        self.assertEqual(
            preview.questions[0].source_header
            + "".join(q.raw_markdown for q in preview.questions),
            text,
        )
        child = preview.questions[0].subquestions[1]
        self.assertEqual(child.path, ("a", "i"))
        self.assertEqual(child.parent_path, ("a",))
        self.assertEqual(child.chapters, ("1", "2"))
        self.assertIn("H₂O $x^2$", child.prompt_markdown)
        self.assertIn("**判分**", child.answer_markdown)
        self.assertEqual(path.read_bytes(), before)

    def test_fenced_fake_questions_do_not_split(self):
        body = (
            BODY
            + "\n````text\n## Q99 [9]\n```\n### (fake) [9]\n````\n~~~text\n## Q98 [8]\n~~~\n"
        )
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", canonical(body=body))
        self.assertEqual(len(self.preview().questions), 1)
        self.assertEqual(len(self.preview().questions[0].subquestions), 2)

    def test_confirmed_mirror_and_idempotent_report(self):
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", canonical())
        self.write("passyear/extracted/ch02-b/9701_s25_21.md", mirrored())
        first = self.preview()
        self.assertEqual((len(first.questions), len(first.mirrors)), (1, 1))
        self.assertEqual(
            first.mirrors[0].canonical_identity, first.questions[0].identity
        )
        self.assertEqual(first.mirrors[0].source.raw_markdown, mirrored())
        self.assertEqual(
            first.mirrors[0].source.source_sha256,
            hashlib.sha256(mirrored().encode()).hexdigest(),
        )
        self.assertEqual(metadata_report(first), metadata_report(self.preview()))

    def test_mirror_newline_equivalence_preserves_snapshots_hashes_and_idempotence(
        self,
    ):
        for canonical_crlf, mirror_crlf in ((False, True), (True, False)):
            with self.subTest(canonical_crlf=canonical_crlf):
                source = canonical() + "\n\n"
                copy = mirrored().rstrip("\n")
                if canonical_crlf:
                    source = source.replace("\n", "\r\n")
                if mirror_crlf:
                    copy = copy.replace("\n", "\r\n") + "\r\n"
                source_path = self.write(
                    "passyear/extracted/ch01-a/9701_s25_21.md", source
                )
                mirror_path = self.write(
                    "passyear/extracted/ch02-b/9701_s25_21.md", copy
                )
                preview = self.preview()
                self.assertEqual((len(preview.questions), len(preview.mirrors)), (1, 1))
                self.assertEqual(len(preview.unresolved_mirrors), 0)
                self.assertEqual(preview.questions[0].raw_markdown, source)
                self.assertEqual(preview.mirrors[0].source.raw_markdown, copy)
                for record, original, file_path in (
                    (preview.questions[0], source, source_path),
                    (preview.mirrors[0].source, copy, mirror_path),
                ):
                    self.assertEqual(
                        record.source_sha256,
                        hashlib.sha256(original.encode()).hexdigest(),
                    )
                    self.assertEqual(file_path.read_bytes(), original.encode())
                    self.assertTrue(record.preview_only)
                    self.assertEqual(record.purpose, "unassigned")
                    self.assertFalse(record.student_view_eligible)
                self.assertNotEqual(
                    preview.questions[0].source_sha256,
                    preview.mirrors[0].source.source_sha256,
                )
                self.assertEqual(
                    metadata_report(preview), metadata_report(self.preview())
                )

    def test_newline_equivalence_keeps_text_spaces_hard_breaks_and_internal_lines_significant(
        self,
    ):
        cases = {
            "text": BODY.replace("equivalent", "different"),
            "one_trailing_space": BODY.replace(
                "Synthetic prompt H₂O $x^2$.", "Synthetic prompt H₂O $x^2$. "
            ),
            "hard_break": BODY.replace(
                "Synthetic prompt H₂O $x^2$.", "Synthetic prompt H₂O $x^2$.  "
            ),
            "terminal_content_spaces": BODY.rstrip("\n") + "  \n",
            "internal_blank_line": BODY.replace(
                "Shared synthetic premise.\n", "Shared synthetic premise.\n\n"
            ),
            "internal_bare_cr": BODY.replace(
                "Shared synthetic premise.\n", "Shared synthetic premise.\r"
            ),
        }
        for name, changed_body in cases.items():
            with self.subTest(change=name):
                self.write(
                    "passyear/extracted/ch01-a/9701_s25_21.md", canonical() + "\n\n"
                )
                self.write(
                    "passyear/extracted/ch02-b/9701_s25_21.md",
                    mirrored(body=changed_body).replace("\n", "\r\n"),
                )
                preview = self.preview()
                self.assertEqual(len(preview.mirrors), 0)
                self.assertEqual(len(preview.unresolved_mirrors), 1)
                self.assertIn("mirror_content_conflict", self.codes(preview))

    def test_same_year_question_different_component_never_merges(self):
        for ref in ("9701_s25_21", "9701_s25_22", "9701_w25_21"):
            self.write(f"passyear/extracted/ch01-a/{ref}.md", canonical())
        preview = self.preview()
        self.assertEqual(len(preview.questions), 3)
        self.assertEqual(len({q.identity for q in preview.questions}), 3)

    def test_ms_conflict_keeps_unresolved_source(self):
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", canonical())
        self.write(
            "passyear/extracted/ch02-b/9701_s25_21.md",
            mirrored(body=BODY.replace("equivalent", "different")),
        )
        preview = self.preview()
        self.assertEqual(len(preview.mirrors), 0)
        self.assertEqual(len(preview.unresolved_mirrors), 1)
        self.assertIn("mirror_content_conflict", self.codes(preview))
        self.assertIn("different", preview.unresolved_mirrors[0].raw_markdown)

    def test_mirror_image_bytes_must_match(self):
        body = BODY + "\n![synthetic](img/picture.png)\n"
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", canonical(body=body))
        self.write("passyear/extracted/ch02-b/9701_s25_21.md", mirrored(body=body))
        self.write("passyear/extracted/ch01-a/img/picture.png", b"synthetic-image-one")
        self.write("passyear/extracted/ch02-b/img/picture.png", b"synthetic-image-two")
        self.assertIn("mirror_resource_conflict", self.codes())
        self.write("passyear/extracted/ch02-b/img/picture.png", b"synthetic-image-one")
        self.assertEqual(len(self.preview().mirrors), 1)

    def test_unsafe_mirror_target_and_wrong_paper(self):
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", canonical())
        mirror = self.write(
            "passyear/extracted/ch02-b/9701_s25_21.md",
            mirrored(target="../../../../../outside.md"),
        )
        self.assertIn("unsafe_mirror_target", self.codes())
        mirror.unlink()
        self.write("passyear/extracted/ch02-b/9701_s25_22.md", mirrored())
        self.assertIn("mirror_identity_mismatch", self.codes())

    def test_images_reject_all_unsafe_forms_and_unsupported_resources(self):
        refs = [
            "../outside.png",
            "/tmp/outside.png",
            "C:\\outside.png",
            "\\\\host\\share\\a.png",
            "https://example.invalid/a.png",
            "img/%2e%2e/a.png",
            "img/missing.png",
            "img/private.env",
        ]
        body = BODY + "\n" + "\n".join(f"![synthetic]({ref})" for ref in refs)
        body += '\n<img src="https://example.invalid/secret">\n![reference][hidden]\n'
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", canonical(body=body))
        codes = self.codes()
        self.assertTrue(
            {
                "unsafe_image_path",
                "missing_or_unreadable_image",
                "unsupported_image_resource",
                "unresolved_embedded_resource",
                "unresolved_reference_image",
            }
            <= codes
        )
        self.assertTrue(
            all(r.sha256 is None for r in self.preview().questions[0].resources)
        )

    def test_symlink_resources_and_markdown_are_rejected(self):
        image = self.write("outside.png", b"untrusted")
        parent = self.root / "passyear/extracted/ch01-a"
        parent.mkdir(parents=True)
        try:
            (parent / "linked.png").symlink_to(image)
        except OSError:
            self.skipTest("OS does not permit symlink creation")
        self.write(
            "passyear/extracted/ch01-a/9701_s25_21.md",
            canonical(body=BODY + "\n![x](linked.png)\n"),
        )
        (parent / "9701_s25_22.md").symlink_to(parent / "9701_s25_21.md")
        self.assertTrue({"unsafe_image_path", "unsafe_markdown_link"} <= self.codes())

    def test_missing_metadata_and_syllabus_years_are_explicit(self):
        self.write("passyear/extracted/misc/unknown.md", canonical())
        self.write("passyear/extracted/ch01-a/9701_s24_21.md", canonical())
        self.assertTrue(
            {
                "missing_paper_ref_and_year",
                "missing_learning_outcomes",
                "missing_general_ms",
                "question_outside_syllabus_years",
            }
            <= self.codes()
        )
        self.assertIsNone(self.preview().questions[-1].year)
        self.assertTrue(
            all(
                not sub.learning_outcomes
                for q in self.preview().questions
                for sub in q.subquestions
            )
        )

    def test_content_gaps_withdrawal_and_answer_risks(self):
        body = (
            "\n> 本题没有官方 mark scheme。不是 MS 原文。\n"
            "### (a) [2]\n| blank | **answer** |\n**答案** — table\n"
            "### (b) [官方撤销，原分值 [2]]\n**答案** — withdrawn\n"
            "```tikz\n\\usepackage{chemfig}\n\\chemfig{C-C}\n```\n实际可得 2 分\n"
        )
        self.write(
            "passyear/extracted/ch01-a/9701_s25_21.md", canonical(body=body, marks=4)
        )
        preview = self.preview()
        self.assertTrue(
            {
                "missing_official_ms",
                "withdrawn_subquestion",
                "answer_embedded_in_prompt_table",
                "tikz_chemfig_requires_renderer",
            }
            <= self.codes(preview)
        )
        self.assertEqual(
            (preview.questions[0].printed_marks, preview.questions[0].effective_marks),
            (4, 2),
        )
        self.assertTrue(preview.questions[0].subquestions[1].withdrawn)

    def test_preview_flags_cannot_be_constructed_or_replaced_as_student_ready(self):
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", canonical())
        preview = self.preview()
        self.assertTrue(preview.preview_only)
        self.assertEqual(preview.purpose, "unassigned")
        self.assertFalse(preview.student_view_eligible)
        with self.assertRaises((ValueError, TypeError)):
            replace(preview, student_view_eligible=True)
        with self.assertRaises(FrozenInstanceError):
            preview.questions[0].student_view_eligible = True

    def test_shared_preamble_images_and_semantics_are_not_discarded(self):
        header = "# Shared premise\n![shared](img/shared.png)\n"
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", header + canonical())
        self.write("passyear/extracted/ch02-b/9701_s25_21.md", header + mirrored())
        self.write("passyear/extracted/ch01-a/img/shared.png", b"same")
        self.write("passyear/extracted/ch02-b/img/shared.png", b"different")
        self.assertIn("mirror_resource_conflict", self.codes())
        self.assertEqual(len(self.preview().questions[0].resources), 1)
        self.write("passyear/extracted/ch02-b/img/shared.png", b"same")
        self.assertEqual(len(self.preview().mirrors), 1)
        self.write(
            "passyear/extracted/ch02-b/9701_s25_21.md",
            header.replace("premise", "different premise") + mirrored(),
        )
        self.assertIn("mirror_shared_context_conflict", self.codes())

    def test_shared_preamble_content_risks_are_reported(self):
        header = (
            "# Shared source\n> 本题没有官方 mark scheme。\n"
            "| blank | **answer** |\n```tikz\n\\chemfig{C-C}\n```\n"
        )
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", header + canonical())
        self.assertTrue(
            {
                "missing_official_ms",
                "answer_embedded_in_prompt_table",
                "tikz_chemfig_requires_renderer",
            }
            <= self.codes()
        )

    def test_duplicate_paper_question_keeps_independent_source_identities(self):
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", canonical())
        self.write("passyear/extracted/ch02-b/9701_s25_21.md", canonical())
        preview = self.preview()
        self.assertEqual(len(preview.questions), 2)
        self.assertEqual(len({q.identity for q in preview.questions}), 2)
        self.assertIn("duplicate_canonical_identity", self.codes(preview))

    def test_mirror_marks_and_unknown_title_are_conflicts(self):
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", canonical())
        self.write("passyear/extracted/ch02-b/9701_s25_21.md", mirrored(marks=2))
        self.assertIn("mirror_marks_conflict", self.codes())
        self.write("passyear/extracted/ch02-b/9701_s25_21.md", mirrored())
        self.write(
            "passyear/extracted/ch01-a/9701_s25_21.md",
            canonical().replace("Q1 [1]", "Q1 [1] Meaningful title"),
        )
        self.assertIn("mirror_unrecognized_title", self.codes())

    def test_fenced_answer_marker_is_not_a_pairing_boundary(self):
        body = "\n### (a) [1]\n```text\n**答案** — not an MS\n```\nSynthetic prompt\n"
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", canonical(body=body))
        sub = self.preview().questions[0].subquestions[0]
        self.assertIsNone(sub.answer_markdown)
        self.assertIn("missing_subquestion_ms", self.codes())

    def test_unrecognized_documents_and_invalid_utf8_are_reported(self):
        self.write("passyear/extracted/unknown.md", "# Not a question\n")
        self.write("reference.md", b"\xff\xfe")
        self.assertTrue(
            {"unrecognized_question_document", "unreadable_syllabus_encoding"}
            <= self.codes()
        )
        self.write("general.md", b"\xff\xfe")
        preview = preview_bank(
            self.root, subject="Test", source="Test", general_ms_path="general.md"
        )
        self.assertIn("unreadable_general_ms_encoding", self.codes(preview))

    def test_unresolved_html_and_reference_resources_never_verify_mirrors(self):
        for resource in (
            '<img src="secret.png">',
            "![unknown][definition]",
            "![shortcut]",
        ):
            with self.subTest(resource=resource):
                body = BODY + resource + "\n"
                self.write(
                    "passyear/extracted/ch01-a/9701_s25_21.md", canonical(body=body)
                )
                self.write(
                    "passyear/extracted/ch02-b/9701_s25_21.md", mirrored(body=body)
                )
                self.assertIn("mirror_unverified_resources", self.codes())
                self.assertEqual(len(self.preview().mirrors), 0)

    def test_cli_has_no_body_no_writes_and_reports_errors(self):
        self.write("passyear/extracted/ch01-a/9701_s25_21.md", canonical())
        script = Path(__file__).resolve().parents[1] / "scripts/preview_exam_bank.py"
        before = {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(script),
                str(self.root),
                "--subject",
                "Synthetic",
                "--source",
                "Test archive",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertNotIn("Synthetic prompt", result.stdout)
        self.assertNotIn("synthetic answer", result.stdout)
        self.assertNotIn(str(self.root), result.stdout)
        self.assertFalse(report["student_view_eligible"])
        after = {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)
        self.write(
            "passyear/extracted/ch01-a/9701_s25_21.md",
            canonical(body=BODY + "\n![x](../bad.png)\n"),
        )
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(script),
                str(self.root),
                "--subject",
                "Synthetic",
                "--source",
                "Test archive",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
