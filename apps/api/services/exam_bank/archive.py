"""Bounded ZIP intake and raster-only resource validation."""

import io
import stat
import zipfile
from pathlib import Path, PurePosixPath

import filetype

MAX_EXPANDED = 200 * 1024 * 1024
MAX_FILE = 25 * 1024 * 1024
MAX_FILES = 5000
FORMATS = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}


def raster_type(data: bytes) -> str:
    kind = filetype.guess(data)
    if kind is None or kind.mime not in FORMATS:
        raise ValueError("unsupported_raster_resource")
    return kind.mime


def unpack_archive(data: bytes, destination: Path, max_compressed: int) -> None:
    if len(data) > max_compressed:
        raise ValueError("archive_too_large")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("invalid_zip") from exc
    with archive:
        members = archive.infolist()
        if len(members) > MAX_FILES:
            raise ValueError("too_many_archive_entries")
        seen: set[str] = set()
        total = 0
        for member in members:
            name = member.filename
            path = PurePosixPath(name)
            mode = member.external_attr >> 16
            if (
                not name
                or path.as_posix() != name.rstrip("/")
                or "\\" in name
                or path.is_absolute()
                or ".." in path.parts
                or any(
                    ":" in part or any(ord(c) < 32 for c in part) for part in path.parts
                )
                or name.casefold().rstrip("/") in seen
                or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))
                or member.flag_bits & 1
            ):
                raise ValueError("unsafe_archive_entry")
            seen.add(name.casefold().rstrip("/"))
            total += member.file_size
            if member.file_size > MAX_FILE or total > MAX_EXPANDED:
                raise ValueError("expanded_archive_too_large")
        files = {m.filename.casefold() for m in members if not m.is_dir()}
        for member in members:
            if any(
                str(parent).casefold() in files
                for parent in PurePosixPath(member.filename).parents
            ):
                raise ValueError("archive_file_directory_conflict")
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.filename).parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with archive.open(member) as source, target.open("xb") as output:
                    count = 0
                    while chunk := source.read(65536):
                        count += len(chunk)
                        if count > MAX_FILE or count > member.file_size:
                            raise ValueError("expanded_archive_too_large")
                        output.write(chunk)
            except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
                raise ValueError("invalid_archive_entry") from exc
