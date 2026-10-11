"""Independent immutable exam-bank history, unrelated to learning observations."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.compat import CompatJSONB, CompatUUID


class ExamBank(Base):
    __tablename__ = "exam_banks"
    __table_args__ = (UniqueConstraint("owner_id", "creation_key"),)
    id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, ForeignKey("users.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    creation_key: Mapped[uuid.UUID | None] = mapped_column(CompatUUID, nullable=True)
    creation_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_import_id: Mapped[uuid.UUID | None] = mapped_column(
        CompatUUID, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExamBankImport(Base):
    __tablename__ = "exam_bank_imports"
    __table_args__ = (UniqueConstraint("bank_id", "version_number"),)
    id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, primary_key=True, default=uuid.uuid4
    )
    bank_id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, ForeignKey("exam_banks.id"), index=True
    )
    version_number: Mapped[int]
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(CompatJSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    __table_args__ = (UniqueConstraint("bank_id", "identity"),)
    id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, primary_key=True, default=uuid.uuid4
    )
    bank_id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, ForeignKey("exam_banks.id"), index=True
    )
    identity: Mapped[str] = mapped_column(String(500))


class ExamQuestionVersion(Base):
    __tablename__ = "exam_question_versions"
    __table_args__ = (
        UniqueConstraint("question_id", "version_number"),
        UniqueConstraint("question_id", "content_sha256"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, primary_key=True, default=uuid.uuid4
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, ForeignKey("exam_questions.id"), index=True
    )
    version_number: Mapped[int]
    content_sha256: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(CompatJSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExamImportQuestion(Base):
    __tablename__ = "exam_import_questions"
    import_id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, ForeignKey("exam_bank_imports.id"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, ForeignKey("exam_questions.id"), primary_key=True
    )
    question_version_id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, ForeignKey("exam_question_versions.id")
    )


class ExamResource(Base):
    __tablename__ = "exam_resources"
    __table_args__ = (UniqueConstraint("owner_id", "sha256"),)
    id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        CompatUUID, ForeignKey("users.id"), index=True
    )
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    media_type: Mapped[str] = mapped_column(String(60))
    storage_key: Mapped[str] = mapped_column(String(300))
