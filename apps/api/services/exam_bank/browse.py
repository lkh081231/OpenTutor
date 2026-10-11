"""Owner-filtered current-bank index and immutable management details."""

import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.exam_bank import (
    ExamBank,
    ExamBankImport,
    ExamImportQuestion,
    ExamQuestion,
    ExamQuestionVersion,
)
from schemas.exam_bank_api import (
    BankFacets,
    BankSummary,
    FacetValue,
    QuestionDetail,
    QuestionSummary,
    QuestionVersionSummary,
)
from services.exam_bank.persistence import owned_bank


async def bank_summary(db: AsyncSession, bank: ExamBank) -> BankSummary:
    imported = await db.get(ExamBankImport, bank.current_import_id)
    snapshot = imported.snapshot
    return BankSummary(
        id=bank.id,
        name=bank.name,
        current_import_id=imported.id,
        import_version=imported.version_number,
        question_count=len(snapshot["questions"]),
        subject=snapshot["classification"]["subject"],
        source=snapshot["classification"]["source"],
        created_at=bank.created_at,
    )


def question_summary(
    bank: ExamBank, question: ExamQuestion, version: ExamQuestionVersion
) -> QuestionSummary:
    source = version.snapshot["question"]
    label = (
        f"{source['paper_ref'] or source['source_path']} Q{source['question_number']}"
    )
    return QuestionSummary(
        id=question.id,
        bank_id=bank.id,
        bank_name=bank.name,
        label=label,
        subject=source["classification"]["subject"],
        source=source["classification"]["source"],
        year=source["year"],
        chapters=source["chapters"],
        paper_ref=source["paper_ref"],
        question_number=source["question_number"],
        source_path=source["source_path"],
        version_id=version.id,
        version_number=version.version_number,
        issues=version.snapshot["issues"],
    )


async def current_questions(
    db: AsyncSession, owner_id: uuid.UUID, bank_id: uuid.UUID | None = None
) -> list[QuestionSummary]:
    if bank_id and await owned_bank(db, owner_id, bank_id) is None:
        raise LookupError("bank_not_found")
    query = (
        select(ExamBank, ExamQuestion, ExamQuestionVersion)
        .join(
            ExamImportQuestion,
            ExamImportQuestion.import_id == ExamBank.current_import_id,
        )
        .join(ExamQuestion, ExamQuestion.id == ExamImportQuestion.question_id)
        .join(
            ExamQuestionVersion,
            ExamQuestionVersion.id == ExamImportQuestion.question_version_id,
        )
        .where(ExamBank.owner_id == owner_id)
    )
    if bank_id:
        query = query.where(ExamBank.id == bank_id)
    rows = (
        await db.execute(
            query.order_by(ExamBank.id, ExamQuestion.identity, ExamQuestion.id)
        )
    ).all()
    return [question_summary(*row) for row in rows]


def facets(items: list[QuestionSummary]) -> BankFacets:
    def values(entries: list[str]) -> list[FacetValue]:
        return [
            FacetValue(value=value, label=value, count=count)
            for value, count in sorted(Counter(entries).items())
        ]

    return BankFacets(
        subjects=values([q.subject or "unknown" for q in items]),
        sources=values([q.source or "unknown" for q in items]),
        years=values([str(q.year) if q.year is not None else "unknown" for q in items]),
        chapters=values(
            [chapter for q in items for chapter in (q.chapters or ["unknown"])]
        ),
    )


async def question_detail(
    db: AsyncSession,
    owner_id: uuid.UUID,
    question_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
) -> QuestionDetail:
    row = (
        await db.execute(
            select(ExamBank, ExamQuestion)
            .join(ExamQuestion, ExamQuestion.bank_id == ExamBank.id)
            .where(ExamBank.owner_id == owner_id, ExamQuestion.id == question_id)
        )
    ).one_or_none()
    if row is None:
        raise LookupError("question_not_found")
    bank, question = row
    if version_id:
        version = await db.scalar(
            select(ExamQuestionVersion).where(
                ExamQuestionVersion.id == version_id,
                ExamQuestionVersion.question_id == question.id,
            )
        )
    else:
        version = await db.scalar(
            select(ExamQuestionVersion)
            .join(
                ExamImportQuestion,
                ExamImportQuestion.question_version_id == ExamQuestionVersion.id,
            )
            .where(
                ExamImportQuestion.import_id == bank.current_import_id,
                ExamImportQuestion.question_id == question.id,
            )
        )
    if version is None:
        raise LookupError("question_version_not_found")
    versions = (
        await db.scalars(
            select(ExamQuestionVersion)
            .where(ExamQuestionVersion.question_id == question.id)
            .order_by(ExamQuestionVersion.version_number.desc())
        )
    ).all()
    snapshot = version.snapshot
    source = snapshot["question"]
    raw = source["source_header"] + source["raw_markdown"]
    return QuestionDetail(
        **question_summary(bank, question, version).model_dump(),
        source_header=source["source_header"],
        raw_markdown=source["raw_markdown"],
        source_sha256=source["source_sha256"],
        subquestions=source["subquestions"],
        resources=snapshot["resources"],
        mirrors=snapshot["mirrors"],
        syllabus=snapshot["syllabus"],
        general_ms=snapshot["general_ms"],
        versions=[
            QuestionVersionSummary(
                id=v.id,
                version_number=v.version_number,
                created_at=v.created_at,
                content_sha256=v.content_sha256,
            )
            for v in versions
        ],
        unsupported_renderers=[
            name for name in ("tikz", "chemfig") if name in raw.lower()
        ],
    )
