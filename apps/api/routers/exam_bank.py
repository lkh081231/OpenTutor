"""Authenticated management-only exam-bank intake and browsing."""

import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models.exam_bank import ExamBank, ExamResource
from models.user import User
from schemas.exam_bank_api import (
    BankFacets,
    BankSummary,
    ImportResult,
    QuestionDetail,
    QuestionPage,
)
from services.auth.dependency import get_current_user
from services.exam_bank.archive import raster_type, unpack_archive
from services.exam_bank.browse import (
    bank_summary,
    current_questions,
    facets,
    question_detail,
)
from services.exam_bank.markdown_adapter import checked_path
from services.exam_bank.persistence import ImportConflict, import_preview
from services.exam_bank.preview import metadata_report, preview_bank

router = APIRouter()


def failure(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, "Exam bank record not found")
    if isinstance(exc, (IntegrityError, ImportConflict)):
        return HTTPException(409, "Concurrent import conflict; retry the import")
    return HTTPException(422, str(exc))


async def intake(
    file: UploadFile,
    subject: str,
    source: str,
    question_dir: str,
    syllabus_path: str | None,
    general_ms_path: str | None,
    handler,
):
    maximum = settings.max_upload_size_mb * 1024 * 1024
    data = await file.read(maximum + 1)
    try:
        with tempfile.TemporaryDirectory(prefix="exam-bank-") as directory:
            root = Path(directory)
            unpack_archive(data, root, maximum)
            preview = preview_bank(
                root,
                subject=subject,
                source=source,
                question_dir=question_dir,
                syllabus_path=syllabus_path or None,
                general_ms_path=general_ms_path or None,
            )
            return await handler(preview, root)
    except (ValueError, LookupError, IntegrityError) as exc:
        raise failure(exc) from None
    except Exception:  # noqa: BLE001 - privacy boundary for source-bearing DB errors
        # The upstream generic DB handler logs SQL parameters. Import parameters
        # include source snapshots, so contain unexpected failures at this edge.
        raise HTTPException(500, "Exam bank operation failed") from None
    finally:
        await file.close()


@router.get("", response_model=list[BankSummary])
async def list_banks(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    banks = (
        await db.scalars(
            select(ExamBank)
            .where(
                ExamBank.owner_id == user.id, ExamBank.current_import_id.is_not(None)
            )
            .order_by(ExamBank.created_at, ExamBank.id)
        )
    ).all()
    return [await bank_summary(db, bank) for bank in banks]


@router.post("/preview")
async def preview_archive(
    file: UploadFile = File(...),
    subject: str = Form(...),
    source: str = Form(...),
    question_dir: str = Form("passyear/extracted"),
    syllabus_path: str | None = Form("reference.md"),
    general_ms_path: str | None = Form(None),
    user: User = Depends(get_current_user),
):
    async def report(preview, root):
        return metadata_report(preview)

    return await intake(
        file, subject, source, question_dir, syllabus_path, general_ms_path, report
    )


@router.post("/import", response_model=ImportResult)
async def import_archive(
    file: UploadFile = File(...),
    subject: str = Form(...),
    source: str = Form(...),
    name: str = Form("Exam bank"),
    bank_id: uuid.UUID | None = Form(None),
    idempotency_key: uuid.UUID | None = Form(None),
    question_dir: str = Form("passyear/extracted"),
    syllabus_path: str | None = Form("reference.md"),
    general_ms_path: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    async def save(preview, root):
        bank, imported, reused = await import_preview(
            db,
            preview,
            root,
            Path(settings.upload_dir).resolve(),
            user.id,
            name=name,
            bank_id=bank_id,
            idempotency_key=idempotency_key,
            request_options={
                "subject": subject,
                "source": source,
                "question_dir": question_dir,
                "syllabus_path": syllabus_path,
                "general_ms_path": general_ms_path,
            },
        )
        return ImportResult(
            bank=await bank_summary(db, bank),
            import_id=imported.id,
            import_version=imported.version_number,
            manifest_sha256=imported.manifest_sha256,
            reused=reused,
            report=metadata_report(preview),
        )

    return await intake(
        file, subject, source, question_dir, syllabus_path, general_ms_path, save
    )


@router.get("/facets", response_model=BankFacets)
async def get_facets(
    bank_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return facets(await current_questions(db, user.id, bank_id))
    except LookupError as exc:
        raise failure(exc) from exc


@router.get("/questions", response_model=QuestionPage)
async def list_questions(
    bank_id: uuid.UUID | None = None,
    subject: str | None = None,
    source: str | None = None,
    year: str | None = None,
    chapter: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await current_questions(db, user.id, bank_id)
    except LookupError as exc:
        raise failure(exc) from exc
    items = [
        q
        for q in items
        if (subject is None or subject == (q.subject or "unknown"))
        and (source is None or source == (q.source or "unknown"))
        and (year is None or year == (str(q.year) if q.year is not None else "unknown"))
        and (chapter is None or chapter in (q.chapters or ["unknown"]))
    ]
    start = (page - 1) * page_size
    return QuestionPage(
        items=items[start : start + page_size],
        total=len(items),
        page=page,
        page_size=page_size,
    )


@router.get("/questions/{question_id}", response_model=QuestionDetail)
async def get_question(
    question_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await question_detail(db, user.id, question_id)
    except LookupError as exc:
        raise failure(exc) from exc


@router.get(
    "/questions/{question_id}/versions/{version_id}", response_model=QuestionDetail
)
async def get_question_version(
    question_id: uuid.UUID,
    version_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await question_detail(db, user.id, question_id, version_id)
    except LookupError as exc:
        raise failure(exc) from exc


@router.get("/resources/{resource_id}")
async def get_resource(
    resource_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resource = await db.scalar(
        select(ExamResource).where(
            ExamResource.id == resource_id, ExamResource.owner_id == user.id
        )
    )
    if resource is None:
        raise HTTPException(404, "Exam bank record not found")
    try:
        storage = Path(settings.upload_dir).resolve()
        path = checked_path(storage, storage, resource.storage_key)
        data = path.read_bytes()
        import hashlib

        if (
            hashlib.sha256(data).hexdigest() != resource.sha256
            or raster_type(data) != resource.media_type
        ):
            raise ValueError("invalid_stored_resource")
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "Exam bank resource unavailable") from exc
    return FileResponse(
        path,
        media_type=resource.media_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
