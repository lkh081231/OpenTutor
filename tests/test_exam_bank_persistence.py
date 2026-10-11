"""Synthetic transactional/history/ownership and archive boundary regressions."""

import io
import stat
import tempfile
import unittest
import uuid
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from database import Base, get_db
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from models.exam_bank import ExamBank, ExamBankImport, ExamQuestionVersion, ExamResource
from models.user import User
from routers.exam_bank import router
from schemas.exam_bank import PreviewIssue
from services.auth.dependency import get_current_user
from services.exam_bank.archive import unpack_archive
from services.exam_bank.browse import current_questions, question_detail
from services.exam_bank.persistence import (
    ImportConflict,
    import_preview,
    validate_import,
)
from services.exam_bank.preview import preview_bank
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452")


class ArchiveTests(unittest.TestCase):
    def test_cli_database_exception_never_prints_source_parameters(self):
        import contextlib
        import importlib.util
        import sys

        from sqlalchemy.exc import SQLAlchemyError

        spec = importlib.util.spec_from_file_location(
            "synthetic_import_cli",
            Path(__file__).parents[1] / "scripts/import_exam_bank.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = [
            "import_exam_bank.py",
            "synthetic",
            "--owner-id",
            str(uuid.uuid4()),
            "--name",
            "synthetic",
            "--subject",
            "synthetic",
            "--source",
            "synthetic",
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(
                module,
                "run",
                new=AsyncMock(side_effect=SQLAlchemyError("SECRET_SOURCE_SENTINEL")),
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(module.main(), 3)
        self.assertIn("import_failed", stdout.getvalue())
        self.assertNotIn(
            "SECRET_SOURCE_SENTINEL", stdout.getvalue() + stderr.getvalue()
        )

    def test_alias_special_files_and_expansion_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("./a", "a//b", "a/./b"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    unpack_archive(self.archive(name), Path(directory), 10000)
            for mode in (stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR):
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    unpack_archive(self.archive(mode=mode), Path(directory), 10000)
            for constant in ("MAX_FILE", "MAX_EXPANDED", "MAX_FILES"):
                with (
                    patch("services.exam_bank.archive." + constant, 0),
                    self.assertRaises(ValueError),
                ):
                    unpack_archive(self.archive(), Path(directory), 10000)

    def test_file_directory_prefix_conflict(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("a", "file")
            archive.writestr("a/b", "nested file")
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            unpack_archive(data.getvalue(), Path(directory), 10000)

    def archive(self, name="safe.md", content=b"hello", mode=None):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            info = zipfile.ZipInfo(name)
            if mode:
                info.external_attr = mode << 16
            archive.writestr(info, content)
        return data.getvalue()

    def test_reject_paths_links_and_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in (
                "../escape",
                "/escape",
                "C:/escape",
                "dir\\escape",
                "a/../escape",
            ):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    unpack_archive(self.archive(name), Path(directory), 10000)
            with self.assertRaises(ValueError):
                unpack_archive(
                    self.archive(mode=stat.S_IFLNK | 0o777), Path(directory), 10000
                )
            with self.assertRaises(ValueError):
                unpack_archive(self.archive(), Path(directory), 1)

    def test_reject_case_duplicate(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("A.md", "one")
            archive.writestr("a.md", "two")
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            unpack_archive(data.getvalue(), Path(directory), 10000)


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "source"
        self.storage = Path(self.temp.name) / "storage"
        self.path = self.root / "passyear/extracted/ch01/9701_s25_21.md"
        self.path.parent.mkdir(parents=True)
        self.root.joinpath("reference.md").write_text(
            "# Synthetic 2025 syllabus\n", encoding="utf-8"
        )
        self.write("A")
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.db = self.sessions()
        self.owner = User(name="Synthetic owner")
        self.other = User(name="Synthetic other")
        self.db.add_all([self.owner, self.other])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()
        self.temp.cleanup()

    def write(self, text, image=False):
        self.path.write_text(
            f"## Q1 [1]\n\n### (a) [1] · ch1\n\nSynthetic {text}\n"
            + ("![synthetic](image.png)\n" if image else "")
            + "\n**答案** synthetic answer\n",
            encoding="utf-8",
        )
        if image:
            self.path.with_name("image.png").write_bytes(PNG)

    def preview(self):
        return preview_bank(
            self.root, subject="Synthetic Chemistry", source="Synthetic CIE"
        )

    async def save(self, bank_id=None, preview=None):
        return await import_preview(
            self.db,
            preview or self.preview(),
            self.root,
            self.storage,
            self.owner.id,
            name="Synthetic bank",
            bank_id=bank_id,
        )

    async def test_noop_revision_return_and_history(self):
        bank, first, reused = await self.save()
        self.assertFalse(reused)
        _, same, reused = await self.save(bank.id)
        self.assertTrue(reused)
        self.assertEqual(first.id, same.id)
        first_question = (await current_questions(self.db, self.owner.id))[0]
        self.write("B")
        _, second, _ = await self.save(bank.id)
        self.assertEqual(second.version_number, 2)
        self.write("A")
        _, third, reused = await self.save(bank.id)
        self.assertFalse(reused)
        self.assertEqual(third.version_number, 3)
        restored = (await current_questions(self.db, self.owner.id))[0]
        self.assertEqual(restored.version_id, first_question.version_id)
        self.assertEqual(
            await self.db.scalar(select(func.count()).select_from(ExamQuestionVersion)),
            2,
        )
        old = await question_detail(
            self.db, self.owner.id, restored.id, first_question.version_id
        )
        self.assertIn("Synthetic A", old.raw_markdown)

    async def test_context_revision_and_deleted_members_preserve_history(self):
        bank, _, _ = await self.save()
        original = (await current_questions(self.db, self.owner.id))[0]
        self.root.joinpath("reference.md").write_text(
            "# Synthetic changed 2025 syllabus\n", encoding="utf-8"
        )
        await self.save(bank.id)
        current = (await current_questions(self.db, self.owner.id))[0]
        self.assertNotEqual(current.version_id, original.version_id)
        old = await question_detail(
            self.db, self.owner.id, original.id, original.version_id
        )
        self.assertNotIn("changed", old.syllabus.raw_markdown)
        self.path.unlink()
        await self.save(bank.id)
        self.assertEqual(await current_questions(self.db, self.owner.id), [])
        with self.assertRaises(LookupError):
            await question_detail(self.db, self.owner.id, original.id)
        self.assertEqual(
            (
                await question_detail(
                    self.db, self.owner.id, original.id, original.version_id
                )
            ).version_id,
            original.version_id,
        )

    async def test_owner_boundaries(self):
        bank, _, _ = await self.save()
        question = (await current_questions(self.db, self.owner.id))[0]
        self.assertEqual(await current_questions(self.db, self.other.id), [])
        with self.assertRaises(LookupError):
            await current_questions(self.db, self.other.id, bank.id)
        with self.assertRaises(LookupError):
            await question_detail(
                self.db, self.other.id, question.id, question.version_id
            )

    async def test_resource_revision_and_reuse(self):
        self.write("A", image=True)
        bank, _, _ = await self.save()
        original = (await current_questions(self.db, self.owner.id))[0]
        self.path.with_name("image.png").write_bytes(PNG + b"revision")
        await self.save(bank.id)
        current = (await current_questions(self.db, self.owner.id))[0]
        self.assertNotEqual(original.version_id, current.version_id)
        self.assertEqual(
            await self.db.scalar(select(func.count()).select_from(ExamResource)), 2
        )
        old = await question_detail(
            self.db, self.owner.id, original.id, original.version_id
        )
        self.assertTrue(
            (
                self.storage
                / (await self.db.get(ExamResource, old.resources[0].id)).storage_key
            ).exists()
        )

    async def test_changed_resource_rolls_back_everything(self):
        self.write("A", image=True)
        preview = self.preview()
        self.path.with_name("image.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "resource_changed"):
            await self.save(preview=preview)
        self.assertEqual(
            await self.db.scalar(select(func.count()).select_from(ExamBank)), 0
        )
        self.assertEqual(
            await self.db.scalar(select(func.count()).select_from(ExamBankImport)), 0
        )
        self.assertEqual(
            list(self.storage.rglob("*")) if self.storage.exists() else [], []
        )

    async def test_database_failure_removes_only_new_batch(self):
        self.write("A", image=True)
        bank, _, _ = await self.save()
        resources = (await self.db.scalars(select(ExamResource))).all()
        old_path = self.storage / resources[0].storage_key
        self.path.with_name("image.png").write_bytes(PNG + b"new")
        owner_id, bank_id = self.owner.id, bank.id
        with (
            patch.object(
                self.db,
                "commit",
                side_effect=RuntimeError("synthetic database failure"),
            ),
            self.assertRaises(RuntimeError),
        ):
            await import_preview(
                self.db,
                self.preview(),
                self.root,
                self.storage,
                owner_id,
                name="Synthetic",
                bank_id=bank_id,
            )
        self.assertTrue(old_path.exists())
        self.assertEqual(
            await self.db.scalar(select(func.count()).select_from(ExamResource)), 1
        )
        self.assertEqual(len([p for p in self.storage.rglob("*") if p.is_file()]), 1)

    async def test_api_management_browse_resources_and_authentication(self):
        self.write("A", image=True)
        application = FastAPI()
        application.include_router(router, prefix="/api/exam-banks")

        async def database_override():
            yield self.db

        application.dependency_overrides[get_db] = database_override
        application.dependency_overrides[get_current_user] = lambda: self.owner
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            for path in self.root.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(self.root).as_posix())
        from config import settings

        with patch.object(settings, "upload_dir", str(self.storage)):
            async with AsyncClient(
                transport=ASGITransport(app=application), base_url="http://synthetic"
            ) as client:
                preview = await client.post(
                    "/api/exam-banks/preview",
                    files={"file": ("synthetic.zip", data.getvalue())},
                    data={"subject": "Synthetic", "source": "Synthetic"},
                )
                self.assertEqual(preview.status_code, 200, preview.text)
                self.assertNotIn("Synthetic A", preview.text)
                result = await client.post(
                    "/api/exam-banks/import",
                    files={"file": ("synthetic.zip", data.getvalue())},
                    data={"subject": "Synthetic", "source": "Synthetic"},
                )
                self.assertEqual(result.status_code, 200, result.text)
                from sqlalchemy.exc import SQLAlchemyError

                with patch(
                    "routers.exam_bank.import_preview",
                    new=AsyncMock(
                        side_effect=SQLAlchemyError("SECRET_SOURCE_SENTINEL")
                    ),
                ):
                    failed = await client.post(
                        "/api/exam-banks/import",
                        files={"file": ("synthetic.zip", data.getvalue())},
                        data={"subject": "Synthetic", "source": "Synthetic"},
                    )
                self.assertEqual(failed.status_code, 500)
                self.assertNotIn("SECRET_SOURCE_SENTINEL", failed.text)
                banks = await client.get("/api/exam-banks")
                self.assertEqual(len(banks.json()), 1)
                listing = await client.get(
                    "/api/exam-banks/questions?year=2025&page_size=1"
                )
                self.assertEqual(listing.json()["total"], 1)
                question = listing.json()["items"][0]
                detail = await client.get("/api/exam-banks/questions/" + question["id"])
                self.assertEqual(detail.status_code, 200, detail.text)
                self.assertFalse(detail.json()["student_view_eligible"])
                resource = detail.json()["resources"][0]
                image = await client.get(resource["url"])
                self.assertEqual(image.status_code, 200)
                self.assertEqual(image.headers["x-content-type-options"], "nosniff")
                self.assertEqual(image.headers["cache-control"], "private, no-store")
                self.assertNotIn(str(self.storage), detail.text)
                facet = await client.get("/api/exam-banks/facets")
                self.assertEqual(
                    facet.json()["years"],
                    [{"value": "2025", "label": "2025", "count": 1}],
                )
                application.dependency_overrides[get_current_user] = lambda: self.other
                self.assertEqual((await client.get(resource["url"])).status_code, 404)
                bank_id = result.json()["bank"]["id"]
                for endpoint in (
                    "/api/exam-banks/facets?bank_id=" + bank_id,
                    "/api/exam-banks/questions?bank_id=" + bank_id,
                    "/api/exam-banks/questions/"
                    + question["id"]
                    + "/versions/"
                    + question["version_id"],
                ):
                    self.assertEqual((await client.get(endpoint)).status_code, 404)
                denied = await client.post(
                    "/api/exam-banks/import",
                    files={"file": ("synthetic.zip", data.getvalue())},
                    data={
                        "subject": "Synthetic",
                        "source": "Synthetic",
                        "bank_id": bank_id,
                    },
                )
                self.assertEqual(denied.status_code, 404)
                self.assertEqual(
                    (
                        await client.get("/api/exam-banks/questions/" + question["id"])
                    ).status_code,
                    404,
                )
                application.dependency_overrides.pop(get_current_user)
                with patch.object(settings, "auth_enabled", True):
                    self.assertEqual(
                        (await client.get("/api/exam-banks/questions")).status_code, 401
                    )

    async def test_stale_concurrent_session_conflict_preserves_winner(self):
        self.write("A", image=True)
        bank, _, _ = await self.save()
        owner_id, bank_id = self.owner.id, bank.id
        self.write("B", image=True)
        changed = self.preview()
        loser = self.sessions()
        original_scalar = loser.scalar
        raced = False

        async def stale_read(query, *args, **kwargs):
            nonlocal raced
            result = await original_scalar(query, *args, **kwargs)
            if not raced and "max(exam_bank_imports.version_number)" in str(query):
                raced = True
                async with self.sessions() as winner:
                    await import_preview(
                        winner,
                        changed,
                        self.root,
                        self.storage,
                        owner_id,
                        name="Winner",
                        bank_id=bank_id,
                    )
            return result

        try:
            with (
                patch.object(loser, "scalar", side_effect=stale_read),
                self.assertRaises(IntegrityError),
            ):
                await import_preview(
                    loser,
                    changed,
                    self.root,
                    self.storage,
                    owner_id,
                    name="Loser",
                    bank_id=bank_id,
                )
        finally:
            await loser.close()
        self.assertTrue(raced)
        self.db.expire_all()
        visible = await current_questions(self.db, owner_id)
        self.assertEqual(visible[0].version_number, 2)
        detail = await question_detail(self.db, owner_id, visible[0].id)
        self.assertIn("Synthetic B", detail.raw_markdown)
        self.assertEqual(len([p for p in self.storage.rglob("*") if p.is_file()]), 1)

    async def test_creation_retry_late_replay_and_owner_key_scope(self):
        key = uuid.uuid4()
        first_preview = self.preview()
        owner_id, other_id = self.owner.id, self.other.id
        bank, first, _ = await import_preview(
            self.db,
            first_preview,
            self.root,
            self.storage,
            owner_id,
            name="Synthetic bank",
            idempotency_key=key,
        )
        duplicate, replay, reused = await import_preview(
            self.db,
            first_preview,
            self.root,
            self.storage,
            owner_id,
            name="Synthetic bank",
            idempotency_key=key,
        )
        self.assertTrue(reused)
        self.assertEqual(duplicate.id, bank.id)
        self.assertEqual(replay.id, first.id)
        self.write("B")
        _, second, _ = await self.save(bank.id)
        _, replay, reused = await import_preview(
            self.db,
            first_preview,
            self.root,
            self.storage,
            owner_id,
            name="Synthetic bank",
            idempotency_key=key,
        )
        self.assertTrue(reused)
        self.assertEqual(replay.id, first.id)
        self.assertEqual(bank.current_import_id, second.id)
        with self.assertRaises(ImportConflict):
            await import_preview(
                self.db,
                first_preview,
                self.root,
                self.storage,
                owner_id,
                name="Changed name",
                idempotency_key=key,
            )
        other_bank, _, _ = await import_preview(
            self.db,
            first_preview,
            self.root,
            self.storage,
            other_id,
            name="Synthetic bank",
            idempotency_key=key,
        )
        self.assertNotEqual(other_bank.id, bank.id)

    async def test_additive_schema_on_copy_preserves_existing_user(self):
        import shutil

        from sqlalchemy import inspect

        original = Path(self.temp.name) / "legacy.db"
        copied = Path(self.temp.name) / "upgrade-copy.db"
        old_engine = create_async_engine(f"sqlite+aiosqlite:///{original.as_posix()}")
        legacy_tables = [
            t for t in Base.metadata.sorted_tables if not t.name.startswith("exam_")
        ]
        async with old_engine.begin() as connection:
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(sync, tables=legacy_tables)
            )
        async with async_sessionmaker(old_engine, expire_on_commit=False)() as session:
            user = User(name="Preserved synthetic legacy owner")
            session.add(user)
            await session.commit()
            user_id = user.id
        await old_engine.dispose()
        shutil.copyfile(original, copied)
        new_engine = create_async_engine(f"sqlite+aiosqlite:///{copied.as_posix()}")
        async with new_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            tables = await connection.run_sync(
                lambda sync: inspect(sync).get_table_names()
            )
        self.assertIn("exam_bank_imports", tables)
        async with async_sessionmaker(new_engine)() as session:
            self.assertEqual(
                (await session.get(User, user_id)).name,
                "Preserved synthetic legacy owner",
            )
        await new_engine.dispose()

    def test_error_allowlist(self):
        preview = self.preview()
        validate_import(
            replace(
                preview,
                issues=(PreviewIssue("missing_official_ms", "error", "synthetic"),),
            )
        )
        for code in (
            "unsafe_resource_path",
            "duplicate_canonical_identity",
            "mirror_content_conflict",
            "unknown_future_error",
        ):
            with self.subTest(code=code), self.assertRaises(ValueError):
                validate_import(
                    replace(preview, issues=(PreviewIssue(code, "error", "synthetic"),))
                )
