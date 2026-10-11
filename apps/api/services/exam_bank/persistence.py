"""Transactional management imports with immutable source/context snapshots."""

import hashlib
import json
import shutil
import uuid
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.exam_bank import (
    ExamBank,
    ExamBankImport,
    ExamImportQuestion,
    ExamQuestion,
    ExamQuestionVersion,
    ExamResource,
)
from schemas.exam_bank import BankPreview
from services.exam_bank.archive import raster_type
from services.exam_bank.markdown_adapter import checked_path

# Content gaps may remain in management imports. Every other error blocks.
ALLOWED_CONTENT_ERRORS = frozenset({"missing_official_ms"})
ADAPTER_VERSION = "markdown-m1.2-v1"


class ImportConflict(ValueError):
    """A creation token was reused for a different request."""


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def validate_import(preview: BankPreview) -> None:
    blocked = sorted(
        {
            i.code
            for i in preview.issues
            if i.severity == "error" and i.code not in ALLOWED_CONTENT_ERRORS
        }
    )
    if blocked or preview.unresolved_mirrors:
        raise ValueError(
            "import_blocked:" + ",".join(blocked or ["unresolved_mirrors"])
        )
    identities = [q.identity for q in preview.questions]
    if len(identities) != len(set(identities)):
        raise ValueError("import_blocked:duplicate_canonical_identity")


async def owned_bank(
    db: AsyncSession, owner_id: uuid.UUID, bank_id: uuid.UUID
) -> ExamBank | None:
    return await db.scalar(
        select(ExamBank).where(ExamBank.id == bank_id, ExamBank.owner_id == owner_id)
    )


async def import_preview(
    db: AsyncSession,
    preview: BankPreview,
    root: Path,
    storage_root: Path,
    owner_id: uuid.UUID,
    *,
    name: str,
    bank_id: uuid.UUID | None = None,
    idempotency_key: uuid.UUID | None = None,
    request_options: dict[str, object] | None = None,
) -> tuple[ExamBank, ExamBankImport, bool]:
    """Caller commits/rolls back no other writes in this session.

    This function commits atomically; filesystem batches are independent so a
    failed import can remove only its own newly written files.
    """
    validate_import(preview)
    snapshot = asdict(preview)
    manifest = fingerprint({"adapter": ADAPTER_VERSION, "preview": snapshot})
    creation_hash = fingerprint(
        {"manifest": manifest, "name": name, "options": request_options}
    )
    if bank_id is None and idempotency_key is not None:
        previous = await db.scalar(
            select(ExamBank).where(
                ExamBank.owner_id == owner_id, ExamBank.creation_key == idempotency_key
            )
        )
        if previous is not None:
            if previous.creation_fingerprint != creation_hash:
                raise ImportConflict("idempotency_key_payload_mismatch")
            first = await db.scalar(
                select(ExamBankImport).where(
                    ExamBankImport.bank_id == previous.id,
                    ExamBankImport.version_number == 1,
                )
            )
            return previous, first, True
    bank = await owned_bank(db, owner_id, bank_id) if bank_id else None
    if bank_id and bank is None:
        raise LookupError("bank_not_found")
    if bank and bank.current_import_id:
        current = await db.get(ExamBankImport, bank.current_import_id)
        if current.manifest_sha256 == manifest:
            return bank, current, True
    batch = storage_root / "exam-bank" / str(owner_id) / str(uuid.uuid4())
    try:
        if bank is None:
            bank = ExamBank(
                owner_id=owner_id,
                name=name.strip()[:200] or "Exam bank",
                creation_key=idempotency_key,
                creation_fingerprint=creation_hash if idempotency_key else None,
            )
            db.add(bank)
            await db.flush()
        latest = await db.scalar(
            select(func.max(ExamBankImport.version_number)).where(
                ExamBankImport.bank_id == bank.id
            )
        )
        imported = ExamBankImport(
            bank_id=bank.id,
            version_number=(latest or 0) + 1,
            manifest_sha256=manifest,
            snapshot=snapshot,
        )
        db.add(imported)
        await db.flush()
        resource_map: dict[str, dict] = {}
        # Include all mirror resources: historical provenance keeps its own paths.
        sources = list(preview.questions) + [m.source for m in preview.mirrors]
        for source in sources:
            for resource in source.resources:
                if resource.sha256 is None or resource.path is None:
                    raise ValueError("unverified_resource")
                data = checked_path(
                    root.resolve(), root.resolve(), resource.path
                ).read_bytes()
                if (
                    hashlib.sha256(data).hexdigest() != resource.sha256
                    or len(data) != resource.size_bytes
                ):
                    raise ValueError("resource_changed_since_preview")
                media = raster_type(data)
                stored = await db.scalar(
                    select(ExamResource).where(
                        ExamResource.owner_id == owner_id,
                        ExamResource.sha256 == resource.sha256,
                    )
                )
                if stored is None:
                    batch.mkdir(parents=True, exist_ok=True)
                    target = batch / resource.sha256
                    target.write_bytes(data)
                    stored = ExamResource(
                        owner_id=owner_id,
                        sha256=resource.sha256,
                        size_bytes=len(data),
                        media_type=media,
                        storage_key=target.relative_to(storage_root).as_posix(),
                    )
                    db.add(stored)
                    await db.flush()
                resource_map[resource.path] = {
                    "id": str(stored.id),
                    "reference": resource.reference,
                    "path": resource.path,
                    "sha256": resource.sha256,
                    "size_bytes": resource.size_bytes,
                    "media_type": stored.media_type,
                    "url": f"/api/exam-banks/resources/{stored.id}",
                }
        context = {
            "syllabus": snapshot["syllabus"],
            "general_ms": snapshot["general_ms"],
        }
        for source in preview.questions:
            mirrors = [
                asdict(m)
                for m in preview.mirrors
                if m.canonical_identity == source.identity
            ]
            issues = [
                asdict(i)
                for i in preview.issues
                if not i.path
                or (
                    i.path == source.source_path
                    and i.question_number in (None, source.question_number)
                )
                or any(
                    i.path == m["source_path"]
                    and i.question_number in (None, m["question_number"])
                    for m in mirrors
                )
            ]
            content = {
                "question": asdict(source),
                "mirrors": mirrors,
                "issues": issues,
                **context,
            }
            content_hash = fingerprint({"adapter": ADAPTER_VERSION, **content})
            # Public resource IDs are storage pointers, excluded from source hash.
            content["resources"] = [
                {**resource_map[r.path], "reference": r.reference}
                for r in source.resources
            ]
            question = await db.scalar(
                select(ExamQuestion).where(
                    ExamQuestion.bank_id == bank.id,
                    ExamQuestion.identity == source.identity,
                )
            )
            if question is None:
                question = ExamQuestion(bank_id=bank.id, identity=source.identity)
                db.add(question)
                await db.flush()
            version = await db.scalar(
                select(ExamQuestionVersion).where(
                    ExamQuestionVersion.question_id == question.id,
                    ExamQuestionVersion.content_sha256 == content_hash,
                )
            )
            if version is None:
                last_version = await db.scalar(
                    select(func.max(ExamQuestionVersion.version_number)).where(
                        ExamQuestionVersion.question_id == question.id
                    )
                )
                version = ExamQuestionVersion(
                    question_id=question.id,
                    version_number=(last_version or 0) + 1,
                    content_sha256=content_hash,
                    snapshot=content,
                )
                db.add(version)
                await db.flush()
            db.add(
                ExamImportQuestion(
                    import_id=imported.id,
                    question_id=question.id,
                    question_version_id=version.id,
                )
            )
        bank.current_import_id = imported.id
        await db.commit()
        return bank, imported, False
    except BaseException:
        await db.rollback()
        if batch.exists():
            shutil.rmtree(batch)
        raise
