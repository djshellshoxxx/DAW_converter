"""Turn whatever the user dropped into a list of project candidates (SPEC-01 Phase 0).

Accepts a single file, a folder (searched for projects), a zip (safely extracted to a
fresh temp folder, then searched) and macOS package bundles such as ``.logicx``, which
are folders. The user's files are only ever opened for reading (SPEC-01 P3).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .detect import Detection, ProjectFormat, detect, is_logic_bundle
from .errors import PATH_NOT_FOUND, EngineError
from .safety import DEFAULT_LIMITS, Limits, safe_extract

_BACKUP_DIR_NAMES = {"backup", "backups", "history", "autosave", "autosaves"}
_BACKUP_SUFFIXES = (".rpp-bak",)


@dataclass
class ProjectCandidate:
    detection: Detection
    is_backup: bool = False
    from_archive: str | None = None  # original zip path if extracted

    def to_dict(self) -> dict[str, object]:
        return {
            **self.detection.to_dict(),
            "is_backup": self.is_backup,
            "from_archive": self.from_archive,
        }


@dataclass
class ResolvedInput:
    """Candidates found under one input path. Call ``cleanup()`` when done."""

    path: str
    candidates: list[ProjectCandidate] = field(default_factory=list)
    temp_dirs: list[Path] = field(default_factory=list)

    def cleanup(self) -> None:
        for d in self.temp_dirs:
            shutil.rmtree(d, ignore_errors=True)
        self.temp_dirs.clear()

    def __enter__(self) -> ResolvedInput:
        return self

    def __exit__(self, *exc: object) -> None:
        self.cleanup()


def _looks_like_backup(path: Path, root: Path) -> bool:
    if path.name.lower().endswith(_BACKUP_SUFFIXES):
        return True
    try:
        rel_parts = path.relative_to(root).parts[:-1]
    except ValueError:
        rel_parts = ()
    return any(p.lower() in _BACKUP_DIR_NAMES for p in rel_parts)


def resolve(path: str | os.PathLike[str], limits: Limits = DEFAULT_LIMITS) -> ResolvedInput:
    root = Path(path)
    if not root.exists():
        raise EngineError(PATH_NOT_FOUND, "That file or folder no longer exists.", {"path": str(root)})
    result = ResolvedInput(path=str(root))
    try:
        _collect(root, root, result, limits, depth=0, from_archive=None)
    except BaseException:
        result.cleanup()
        raise
    return result


def _collect(
    path: Path,
    root: Path,
    result: ResolvedInput,
    limits: Limits,
    depth: int,
    from_archive: str | None,
) -> None:
    if path.is_dir():
        if is_logic_bundle(path):
            result.candidates.append(
                ProjectCandidate(detect(path), _looks_like_backup(path, root), from_archive)
            )
            return
        _walk_folder(path, root, result, limits, depth, from_archive)
        return

    det = detect(path)
    if det.format == ProjectFormat.GENERIC_ZIP:
        _collect_zip(path, result, limits, depth, from_archive)
    elif det.is_project:
        result.candidates.append(
            ProjectCandidate(det, _looks_like_backup(path, root), from_archive)
        )
    elif path == root:
        # A single unsupported file is still reported so the UI can explain why.
        result.candidates.append(ProjectCandidate(det, False, from_archive))


def _walk_folder(
    folder: Path,
    root: Path,
    result: ResolvedInput,
    limits: Limits,
    depth: int,
    from_archive: str | None,
) -> None:
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        here = Path(dirpath)
        # Bundles are projects, not folders to descend into.
        for d in list(dirnames):
            sub = here / d
            if sub.is_symlink():
                dirnames.remove(d)
            elif is_logic_bundle(sub):
                dirnames.remove(d)
                result.candidates.append(
                    ProjectCandidate(detect(sub), _looks_like_backup(sub, root), from_archive)
                )
        dirnames.sort()
        for name in sorted(filenames):
            file = here / name
            if file.is_symlink():
                continue
            det = detect(file)
            if det.format == ProjectFormat.GENERIC_ZIP:
                _collect_zip(file, result, limits, depth, from_archive)
            elif det.is_project and det.format != ProjectFormat.REPORT_JSON:
                result.candidates.append(
                    ProjectCandidate(det, _looks_like_backup(file, root), from_archive)
                )


def _collect_zip(
    zip_path: Path,
    result: ResolvedInput,
    limits: Limits,
    depth: int,
    from_archive: str | None,
) -> None:
    if depth >= limits.max_archive_depth:
        return
    tmp = Path(tempfile.mkdtemp(prefix="rackcheck-"))
    result.temp_dirs.append(tmp)
    safe_extract(zip_path, tmp, limits)
    _walk_folder(tmp, tmp, result, limits, depth + 1, from_archive or str(zip_path))
