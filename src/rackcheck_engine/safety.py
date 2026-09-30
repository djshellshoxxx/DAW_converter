"""Defensive limits for hostile input (SPEC-07 section 1).

Zip handling rejects bombs and path traversal before anything is written to disk, and
extraction only ever targets a fresh temporary folder.
"""

from __future__ import annotations

import gzip
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .errors import ARCHIVE_REJECTED, EngineError


@dataclass(frozen=True)
class Limits:
    max_uncompressed_bytes: int = 4 * 1024**3  # 4 GB
    max_entries: int = 100_000
    max_compression_ratio: float = 100.0
    max_archive_depth: int = 2  # zip inside zip inside zip is rejected


DEFAULT_LIMITS = Limits()


def _entry_is_unsafe(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        return True
    return ".." in PurePosixPath(normalized).parts


def _entry_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def check_zip(zf: zipfile.ZipFile, limits: Limits = DEFAULT_LIMITS) -> None:
    """Raise ``EngineError(ARCHIVE_REJECTED)`` if the archive breaks any limit."""
    infos = zf.infolist()
    if len(infos) > limits.max_entries:
        raise EngineError(
            ARCHIVE_REJECTED,
            "This archive has too many files to scan safely.",
            {"entries": len(infos), "limit": limits.max_entries},
        )
    total = 0
    for info in infos:
        if _entry_is_unsafe(info.filename):
            raise EngineError(
                ARCHIVE_REJECTED,
                "This archive contains an unsafe file path.",
                {"entry": info.filename},
            )
        if _entry_is_symlink(info):
            raise EngineError(
                ARCHIVE_REJECTED,
                "This archive contains a symbolic link, which is not allowed.",
                {"entry": info.filename},
            )
        total += info.file_size
        if total > limits.max_uncompressed_bytes:
            raise EngineError(
                ARCHIVE_REJECTED,
                "This archive expands to more data than can be scanned safely.",
                {"limit_bytes": limits.max_uncompressed_bytes},
            )
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > limits.max_compression_ratio:
                raise EngineError(
                    ARCHIVE_REJECTED,
                    "This archive is compressed suspiciously well and was not opened.",
                    {"entry": info.filename, "ratio": round(ratio, 1)},
                )


def safe_extract(zip_path: Path, dest: Path, limits: Limits = DEFAULT_LIMITS) -> None:
    """Extract ``zip_path`` into the empty folder ``dest`` after all checks pass."""
    with zipfile.ZipFile(zip_path) as zf:
        check_zip(zf, limits)
        dest_resolved = dest.resolve()
        for info in zf.infolist():
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(dest_resolved):
                raise EngineError(
                    ARCHIVE_REJECTED,
                    "This archive contains an unsafe file path.",
                    {"entry": info.filename},
                )
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # Stream with a hard cap in case the header lied about file_size.
            remaining = info.file_size
            with zf.open(info) as src, open(target, "wb") as out:
                while chunk := src.read(1024 * 1024):
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise EngineError(
                            ARCHIVE_REJECTED,
                            "An archive entry is larger than its header says.",
                            {"entry": info.filename},
                        )
                    out.write(chunk)


def read_gzip_prefix(path: Path, max_bytes: int) -> bytes | None:
    """Decompress at most ``max_bytes`` from a gzip file. Returns None if not valid gzip."""
    try:
        with gzip.open(path, "rb") as gz:
            return gz.read(max_bytes)
    except (OSError, EOFError, gzip.BadGzipFile):
        return None
