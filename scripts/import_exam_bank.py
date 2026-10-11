"""Explicit local administrator import; stdout never includes question text."""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))


async def run(args: argparse.Namespace) -> dict[str, object]:
    from config import settings
    from database import async_session
    from models.user import User
    from services.exam_bank.persistence import import_preview
    from services.exam_bank.preview import metadata_report, preview_bank

    preview = preview_bank(
        args.root,
        subject=args.subject,
        source=args.source,
        question_dir=args.question_dir,
        syllabus_path=args.syllabus,
        general_ms_path=args.general_ms,
    )
    async with async_session() as db:
        owner = await db.get(User, args.owner_id)
        if owner is None or not owner.is_active:
            raise ValueError("active_owner_required")
        bank, imported, reused = await import_preview(
            db,
            preview,
            Path(args.root),
            Path(settings.upload_dir).resolve(),
            owner.id,
            name=args.name,
            bank_id=args.bank_id,
        )
        return {
            "bank_id": str(bank.id),
            "import_id": str(imported.id),
            "import_version": imported.version_number,
            "reused": reused,
            "report": metadata_report(preview),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("--owner-id", required=True, type=uuid.UUID)
    parser.add_argument("--bank-id", type=uuid.UUID)
    parser.add_argument("--name", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--question-dir", default="passyear/extracted")
    parser.add_argument("--syllabus", default="reference.md")
    parser.add_argument("--general-ms")
    args = parser.parse_args()
    try:
        report = asyncio.run(run(args))
    except (ValueError, LookupError):
        print(json.dumps({"error": "import_rejected"}))
        return 2
    except Exception:  # noqa: BLE001 - never print source-bearing exception parameters
        # SQLAlchemy exception parameters may contain entire source snapshots.
        # Keep operational failures content-free, including stderr tracebacks.
        print(json.dumps({"error": "import_failed"}))
        return 3
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
