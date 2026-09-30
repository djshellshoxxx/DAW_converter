"""Format detection by content first, extension second (SPEC-02 section 2, SPEC-01 P2).

Every detection returns ``format``, ``confidence`` and ``reason`` so failures are
explainable. Checks run in the order of the SPEC-02 table; first confident match wins.
Checks whose markers SPEC-02 flags as "verify with fixtures" return ``probable`` until
a crafted fixture confirms them.
"""

from __future__ import annotations

import zipfile
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from .model import Confidence
from .safety import read_gzip_prefix


class ProjectFormat(StrEnum):
    LOGIC_BUNDLE = "logic_bundle"
    ABLETON_ALS = "ableton_als"
    DAWPROJECT = "dawproject"
    STUDIOONE_SONG = "studioone_song"
    GENERIC_ZIP = "generic_zip"
    REAPER_RPP = "reaper_rpp"
    REAPER_FXCHAIN = "reaper_fxchain"
    REAPER_TRACK_TEMPLATE = "reaper_track_template"
    FLSTUDIO_FLP = "flstudio_flp"
    CUBASE_CPR = "cubase_cpr"
    PROTOOLS_TEXT = "protools_text"
    PROTOOLS_PTX = "protools_ptx"
    BITWIG_BWPROJECT = "bitwig_bwproject"
    REPORT_JSON = "rackcheck_report"
    UNSUPPORTED = "unsupported"


# Human-readable DAW names per format, used in messages and the Home screen list.
DAW_NAMES: dict[ProjectFormat, str] = {
    ProjectFormat.LOGIC_BUNDLE: "Logic Pro / GarageBand",
    ProjectFormat.ABLETON_ALS: "Ableton Live",
    ProjectFormat.DAWPROJECT: "DAWproject",
    ProjectFormat.STUDIOONE_SONG: "Studio One / Fender Studio Pro",
    ProjectFormat.REAPER_RPP: "REAPER",
    ProjectFormat.REAPER_FXCHAIN: "REAPER",
    ProjectFormat.REAPER_TRACK_TEMPLATE: "REAPER",
    ProjectFormat.FLSTUDIO_FLP: "FL Studio",
    ProjectFormat.CUBASE_CPR: "Cubase / Nuendo",
    ProjectFormat.PROTOOLS_TEXT: "Pro Tools (session text export)",
    ProjectFormat.PROTOOLS_PTX: "Pro Tools",
    ProjectFormat.BITWIG_BWPROJECT: "Bitwig Studio",
}

_SNIFF_BYTES = 8192
_GZIP_SNIFF_BYTES = 64 * 1024


@dataclass(frozen=True)
class Detection:
    path: str
    format: ProjectFormat
    confidence: Confidence | None
    reason: str

    @property
    def is_project(self) -> bool:
        return self.format not in (ProjectFormat.UNSUPPORTED, ProjectFormat.GENERIC_ZIP)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _det(path: Path, fmt: ProjectFormat, conf: Confidence | None, reason: str) -> Detection:
    return Detection(str(path), fmt, conf, reason)


def is_logic_bundle(path: Path) -> bool:
    return (path / "Alternatives").is_dir() and (
        path / "Resources" / "ProjectInformation.plist"
    ).is_file()


def detect(path: Path) -> Detection:
    """Detect the project format of a single file or bundle directory."""
    if path.is_dir():
        if is_logic_bundle(path):
            return _det(
                path,
                ProjectFormat.LOGIC_BUNDLE,
                Confidence.CONFIRMED,
                "Folder contains Alternatives/ and Resources/ProjectInformation.plist",
            )
        return _det(path, ProjectFormat.UNSUPPORTED, None, "Folder is not a project bundle")

    try:
        with open(path, "rb") as f:
            head = f.read(_SNIFF_BYTES)
    except OSError as exc:
        return _det(path, ProjectFormat.UNSUPPORTED, None, f"Could not read file: {exc}")

    ext = path.suffix.lower()

    if not head:
        return _det(path, ProjectFormat.UNSUPPORTED, None, "File is empty")

    if head[:2] == b"\x1f\x8b":
        data = read_gzip_prefix(path, _GZIP_SNIFF_BYTES)
        if data is not None and data.lstrip().startswith(b"<?xml") and b"<Ableton" in data:
            return _det(
                path,
                ProjectFormat.ABLETON_ALS,
                Confidence.CONFIRMED,
                "Gzip stream containing XML with an <Ableton> root",
            )
        return _det(path, ProjectFormat.UNSUPPORTED, None, "Gzip file that is not an Ableton set")

    if head[:4] == b"PK\x03\x04":
        return _detect_zip(path)

    text_head = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if text_head.startswith(b"<REAPER_PROJECT"):
        return _det(
            path, ProjectFormat.REAPER_RPP, Confidence.CONFIRMED, "Text starts with <REAPER_PROJECT"
        )

    if head[:4] == b"FLhd":
        return _det(path, ProjectFormat.FLSTUDIO_FLP, Confidence.CONFIRMED, "Header chunk FLhd")

    if head[:4] == b"RIFF" and b"NUND" in head[:256]:
        return _det(
            path,
            ProjectFormat.CUBASE_CPR,
            Confidence.PROBABLE,
            "RIFF header with NUND marker near start (marker pending fixture confirmation)",
        )

    if b"SESSION NAME:" in head and b"SAMPLE RATE:" in head:
        return _det(
            path,
            ProjectFormat.PROTOOLS_TEXT,
            Confidence.PROBABLE,
            "Text with Pro Tools session info headers (pending fixture confirmation)",
        )

    if ext in (".rfxchain", ".rtracktemplate") and (
        text_head.startswith((b"<", b"BYPASS")) or b"<VST" in head
    ):
        fmt = (
            ProjectFormat.REAPER_FXCHAIN
            if ext == ".rfxchain"
            else ProjectFormat.REAPER_TRACK_TEMPLATE
        )
        return _det(path, fmt, Confidence.PROBABLE, f"REAPER chunk text with {ext} extension")

    if ext in (".ptx", ".ptf", ".pts"):
        # SPEC-02 2 asks for a ptformat header check. Until clean-room notes exist in
        # docs/format-notes/protools.md, only the extension is known, so say so.
        return _det(
            path,
            ProjectFormat.PROTOOLS_PTX,
            Confidence.HEURISTIC,
            "Pro Tools session extension; header validation not yet implemented",
        )

    if ext == ".bwproject":
        return _det(
            path, ProjectFormat.BITWIG_BWPROJECT, Confidence.HEURISTIC, "Bitwig project extension"
        )

    if head[:1] == b"{" and b'"schema_version"' in head and b'"plugins"' in head:
        return _det(
            path,
            ProjectFormat.REPORT_JSON,
            Confidence.PROBABLE,
            "JSON with schema_version and plugins; validate against report schema before use",
        )

    return _det(path, ProjectFormat.UNSUPPORTED, None, "No known project signature found")


def _detect_zip(path: Path) -> Detection:
    try:
        with zipfile.ZipFile(path) as zf:
            names = {n.replace("\\", "/") for n in zf.namelist()}
    except (zipfile.BadZipFile, OSError) as exc:
        return _det(path, ProjectFormat.UNSUPPORTED, None, f"Damaged zip archive: {exc}")

    if "project.xml" in names and "metadata.xml" in names:
        return _det(
            path,
            ProjectFormat.DAWPROJECT,
            Confidence.CONFIRMED,
            "Zip with project.xml and metadata.xml at root",
        )
    if "Song/song.xml" in names or "Song/mediapool.xml" in names:
        return _det(
            path,
            ProjectFormat.STUDIOONE_SONG,
            Confidence.PROBABLE,
            "Zip with Song/song.xml or Song/mediapool.xml (entry names pending fixtures)",
        )
    return _det(
        path, ProjectFormat.GENERIC_ZIP, Confidence.CONFIRMED, "Zip archive of other files"
    )
