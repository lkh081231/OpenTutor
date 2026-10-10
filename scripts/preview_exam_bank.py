#!/usr/bin/env python3
"""Metadata-only, read-only Markdown bank preflight. No production imports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# A dry run must not create bytecode beside source files.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from services.exam_bank.preview import metadata_report, preview_bank


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--question-dir", default="passyear/extracted")
    parser.add_argument("--syllabus", default="reference.md")
    parser.add_argument("--general-ms")
    args = parser.parse_args(argv)
    try:
        preview = preview_bank(
            args.root,
            subject=args.subject,
            source=args.source,
            question_dir=args.question_dir,
            syllabus_path=args.syllabus,
            general_ms_path=args.general_ms,
        )
    except (ValueError, OSError) as error:
        # Errors are fixed codes; never echo source text or an exception pathname.
        print(
            json.dumps(
                {
                    "mode": "markdown_dry_run",
                    "error": str(error)
                    if isinstance(error, ValueError)
                    else "unreadable_input",
                }
            )
        )
        return 2
    report = metadata_report(preview)
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
    return 1 if report["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
