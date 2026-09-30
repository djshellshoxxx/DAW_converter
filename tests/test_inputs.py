from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from conftest import write_als, write_dawproject, write_logic_bundle, write_rpp, write_zip

from rackcheck_engine.detect import ProjectFormat
from rackcheck_engine.errors import ARCHIVE_REJECTED, PATH_NOT_FOUND, EngineError
from rackcheck_engine.inputs import resolve
from rackcheck_engine.safety import Limits


def formats(resolved) -> list[ProjectFormat]:
    return sorted(c.detection.format for c in resolved.candidates)


def test_single_file(tmp_path: Path):
    with resolve(write_rpp(tmp_path / "a.rpp")) as r:
        assert formats(r) == [ProjectFormat.REAPER_RPP]


def test_missing_path(tmp_path: Path):
    with pytest.raises(EngineError) as exc:
        resolve(tmp_path / "nope.als")
    assert exc.value.code == PATH_NOT_FOUND


def test_folder_finds_projects_and_marks_backups(tmp_path: Path):
    write_als(tmp_path / "Song.als")
    (tmp_path / "Backup").mkdir()
    write_als(tmp_path / "Backup" / "Song [2026-09-01 101010].als")
    (tmp_path / "Samples").mkdir()
    (tmp_path / "Samples" / "kick.wav").write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    with resolve(tmp_path) as r:
        assert formats(r) == [ProjectFormat.ABLETON_ALS, ProjectFormat.ABLETON_ALS]
        backups = {Path(c.detection.path).name: c.is_backup for c in r.candidates}
        assert backups == {"Song.als": False, "Song [2026-09-01 101010].als": True}


def test_folder_treats_logic_bundle_as_project(tmp_path: Path):
    write_logic_bundle(tmp_path / "Song.logicx")
    with resolve(tmp_path) as r:
        assert formats(r) == [ProjectFormat.LOGIC_BUNDLE]


def test_zipped_project(tmp_path: Path):
    als = write_als(tmp_path / "inner.als")
    z = write_zip(tmp_path / "send.zip", {"Project/inner.als": als.read_bytes()})
    with resolve(z) as r:
        assert formats(r) == [ProjectFormat.ABLETON_ALS]
        assert r.candidates[0].from_archive == str(z)
        extracted = Path(r.candidates[0].detection.path)
        assert extracted.exists()
    assert not extracted.exists()  # temp folder cleaned up


def test_zipped_logic_bundle(tmp_path: Path):
    bundle = write_logic_bundle(tmp_path / "src" / "Song.logicx")
    z = tmp_path / "logic.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in bundle.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(tmp_path / "src").as_posix())
    with resolve(z) as r:
        assert formats(r) == [ProjectFormat.LOGIC_BUNDLE]


def test_dawproject_is_not_unzipped(tmp_path: Path):
    with resolve(write_dawproject(tmp_path / "a.dawproject")) as r:
        assert formats(r) == [ProjectFormat.DAWPROJECT]
        assert r.temp_dirs == []


def test_zip_slip_rejected(tmp_path: Path):
    z = write_zip(tmp_path / "evil.zip", {"../escape.txt": b"x"})
    with pytest.raises(EngineError) as exc:
        resolve(z)
    assert exc.value.code == ARCHIVE_REJECTED
    assert not (tmp_path.parent / "escape.txt").exists()


def test_zip_bomb_ratio_rejected(tmp_path: Path):
    z = write_zip(tmp_path / "bomb.zip", {"zeros.bin": b"\x00" * 5_000_000})
    with pytest.raises(EngineError) as exc:
        resolve(z)
    assert exc.value.code == ARCHIVE_REJECTED


def test_zip_entry_limit(tmp_path: Path):
    z = write_zip(tmp_path / "many.zip", {f"f{i}.txt": b"abc" for i in range(20)})
    with pytest.raises(EngineError):
        resolve(z, Limits(max_entries=10))


def test_nested_zip_depth_limit(tmp_path: Path):
    als = write_als(tmp_path / "a.als").read_bytes()
    inner = write_zip(tmp_path / "inner.zip", {"a.als": als}).read_bytes()
    middle = write_zip(tmp_path / "middle.zip", {"inner.zip": inner}).read_bytes()
    outer = write_zip(tmp_path / "outer.zip", {"middle.zip": middle})
    with resolve(outer) as r:
        assert r.candidates == []  # third level is beyond max_archive_depth=2


def test_unicode_paths(tmp_path: Path):
    folder = tmp_path / "Проект 日本 ünïcode"
    folder.mkdir()
    write_rpp(folder / "曲.rpp")
    with resolve(folder) as r:
        assert formats(r) == [ProjectFormat.REAPER_RPP]
