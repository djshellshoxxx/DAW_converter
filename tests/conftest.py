"""Synthetic signature samples for detector tests.

These are minimal byte patterns that match the SPEC-02 section 2 signatures. They are
NOT real DAW fixtures and do not verify reader behaviour; real crafted fixtures live in
``fixtures/<daw>/<version>/`` (SPEC-06 section 2).
"""

from __future__ import annotations

import gzip
import zipfile
from pathlib import Path


def write_als(path: Path) -> Path:
    xml = b'<?xml version="1.0" encoding="UTF-8"?>\n<Ableton MajorVersion="5" Creator="Ableton Live 12.1.5"></Ableton>'
    path.write_bytes(gzip.compress(xml))
    return path


def write_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def write_dawproject(path: Path) -> Path:
    return write_zip(path, {"project.xml": b"<Project/>", "metadata.xml": b"<MetaData/>"})


def write_rpp(path: Path) -> Path:
    path.write_text('<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n>\n', encoding="utf-8")
    return path


def write_logic_bundle(path: Path) -> Path:
    (path / "Alternatives" / "000").mkdir(parents=True)
    (path / "Alternatives" / "000" / "MetaData.plist").write_bytes(b"<plist/>")
    (path / "Resources").mkdir(parents=True)
    (path / "Resources" / "ProjectInformation.plist").write_bytes(b"<plist/>")
    return path
