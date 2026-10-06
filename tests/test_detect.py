from __future__ import annotations

import gzip
import zipfile
from pathlib import Path

import pytest

from conftest import write_als, write_dawproject, write_logic_bundle, write_rpp, write_zip
from rackcheck_engine.detect import ProjectFormat, detect
from rackcheck_engine.model import Confidence


def test_ableton_by_content(tmp_path: Path):
    d = detect(write_als(tmp_path / "set.als"))
    assert d.format == ProjectFormat.ABLETON_ALS
    assert d.confidence == Confidence.CONFIRMED


def test_renamed_ableton_still_detected(tmp_path: Path):
    d = detect(write_als(tmp_path / "renamed.txt"))
    assert d.format == ProjectFormat.ABLETON_ALS


def test_gzip_that_is_not_ableton(tmp_path: Path):
    p = tmp_path / "x.gz"
    p.write_bytes(gzip.compress(b"hello"))
    assert detect(p).format == ProjectFormat.UNSUPPORTED


def test_truncated_gzip_does_not_crash(tmp_path: Path):
    full = gzip.compress(b"<?xml version='1.0'?><Ableton>" + b"x" * 5000)
    p = tmp_path / "trunc.als"
    p.write_bytes(full[: len(full) // 2])
    assert detect(p).format in (ProjectFormat.ABLETON_ALS, ProjectFormat.UNSUPPORTED)


def test_dawproject(tmp_path: Path):
    d = detect(write_dawproject(tmp_path / "song.dawproject"))
    assert d.format == ProjectFormat.DAWPROJECT
    assert d.confidence == Confidence.CONFIRMED


def test_studio_one_song(tmp_path: Path):
    p = write_zip(tmp_path / "a.song", {"Song/song.xml": b"<Song/>"})
    d = detect(p)
    assert d.format == ProjectFormat.STUDIOONE_SONG
    assert d.confidence == Confidence.PROBABLE


def test_generic_zip(tmp_path: Path):
    p = write_zip(tmp_path / "a.zip", {"readme.txt": b"hi"})
    assert detect(p).format == ProjectFormat.GENERIC_ZIP


def test_zip_limits_are_checked_before_enumerating_names(tmp_path: Path, monkeypatch):
    p = write_zip(tmp_path / "too-many.zip", {"readme.txt": b"hi"})

    def reject_archive(_zf):
        from rackcheck_engine.errors import ARCHIVE_REJECTED, EngineError

        raise EngineError(ARCHIVE_REJECTED, "Archive exceeds the safe entry limit.")

    def names_must_not_be_enumerated(_zf):
        raise AssertionError("archive entry names were enumerated before safety validation")

    monkeypatch.setattr("rackcheck_engine.detect.check_zip", reject_archive)
    monkeypatch.setattr(zipfile.ZipFile, "namelist", names_must_not_be_enumerated)

    result = detect(p)
    assert result.format == ProjectFormat.UNSUPPORTED
    assert "safe entry limit" in result.reason


def test_reaper_with_bom(tmp_path: Path):
    p = tmp_path / "a.rpp-bak"
    p.write_bytes(b"\xef\xbb\xbf<REAPER_PROJECT 0.1\n>")
    assert detect(p).format == ProjectFormat.REAPER_RPP


def test_reaper(tmp_path: Path):
    assert detect(write_rpp(tmp_path / "a.rpp")).format == ProjectFormat.REAPER_RPP


def test_flp(tmp_path: Path):
    p = tmp_path / "a.flp"
    p.write_bytes(b"FLhd\x06\x00\x00\x00" + b"\x00" * 6 + b"FLdt")
    assert detect(p).format == ProjectFormat.FLSTUDIO_FLP


def test_cubase_probable(tmp_path: Path):
    p = tmp_path / "a.cpr"
    p.write_bytes(b"RIFF\x00\x00\x00\x00NUNDROOT" + b"\x00" * 64)
    d = detect(p)
    assert d.format == ProjectFormat.CUBASE_CPR
    assert d.confidence == Confidence.PROBABLE


def test_protools_text(tmp_path: Path):
    p = tmp_path / "session.txt"
    p.write_text("SESSION NAME:\tSong\nSAMPLE RATE:\t48000.000000\n", encoding="utf-8")
    assert detect(p).format == ProjectFormat.PROTOOLS_TEXT


def test_ptx_extension_is_only_heuristic(tmp_path: Path):
    p = tmp_path / "a.ptx"
    p.write_bytes(b"\x03" + b"\x00" * 100)
    d = detect(p)
    assert d.format == ProjectFormat.PROTOOLS_PTX
    assert d.confidence == Confidence.HEURISTIC


def test_logic_bundle(tmp_path: Path):
    d = detect(write_logic_bundle(tmp_path / "Song.logicx"))
    assert d.format == ProjectFormat.LOGIC_BUNDLE


@pytest.mark.parametrize("content", [b"", b"random bytes that mean nothing"])
def test_unsupported(tmp_path: Path, content: bytes):
    p = tmp_path / "x.bin"
    p.write_bytes(content)
    d = detect(p)
    assert d.format == ProjectFormat.UNSUPPORTED
    assert d.reason


def test_detection_never_writes(tmp_path: Path):
    p = write_als(tmp_path / "set.als")
    before = (p.read_bytes(), p.stat().st_mtime_ns)
    detect(p)
    assert (p.read_bytes(), p.stat().st_mtime_ns) == before
