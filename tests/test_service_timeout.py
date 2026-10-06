from __future__ import annotations

import time
from pathlib import Path

import pytest

from rackcheck_engine.errors import CORRUPT_PROJECT, READER_TIMEOUT, EngineError
from rackcheck_engine.model import ScanResult, SourceInfo
from rackcheck_engine.service import _read_with_timeout


class _SlowReader:
    def read(self, path: Path) -> ScanResult:
        time.sleep(30)
        return ScanResult(source=SourceInfo(path=str(path), format="test"))


class _FastReader:
    def read(self, path: Path) -> ScanResult:
        return ScanResult(source=SourceInfo(path=str(path), format="test"))


class _RejectedReader:
    def read(self, path: Path) -> ScanResult:
        raise EngineError(CORRUPT_PROJECT, "Invalid project", {"path": str(path)})


class _UnexpectedFailureReader:
    def read(self, path: Path) -> ScanResult:
        raise RuntimeError("private parser detail")


class _MalformedResultReader:
    def read(self, path: Path) -> ScanResult:
        return "not a ScanResult"  # type: ignore[return-value]


def test_reader_timeout_terminates_worker_and_later_scan_succeeds(tmp_path: Path):
    started = time.monotonic()
    with pytest.raises(EngineError) as caught:
        _read_with_timeout(_SlowReader(), tmp_path / "slow.project", timeout_seconds=0.5)
    elapsed = time.monotonic() - started

    assert caught.value.code == READER_TIMEOUT
    assert caught.value.details["path"] == str(tmp_path / "slow.project")
    assert elapsed < 5

    result = _read_with_timeout(_FastReader(), tmp_path / "fast.project", timeout_seconds=5)
    assert result.source.path == str(tmp_path / "fast.project")


def test_reader_preserves_structured_project_errors(tmp_path: Path):
    path = tmp_path / "invalid.project"
    with pytest.raises(EngineError) as caught:
        _read_with_timeout(_RejectedReader(), path, timeout_seconds=5)
    assert caught.value.code == CORRUPT_PROJECT
    assert caught.value.message == "Invalid project"
    assert caught.value.details == {"path": str(path)}


def test_reader_hides_unexpected_worker_exception_details(tmp_path: Path):
    with pytest.raises(EngineError) as caught:
        _read_with_timeout(_UnexpectedFailureReader(), tmp_path / "broken.project",
                           timeout_seconds=5)
    assert caught.value.code == CORRUPT_PROJECT
    assert "private parser detail" not in caught.value.message


def test_reader_rejects_malformed_worker_result(tmp_path: Path):
    with pytest.raises(EngineError) as caught:
        _read_with_timeout(_MalformedResultReader(), tmp_path / "malformed.project",
                           timeout_seconds=5)
    assert caught.value.code == CORRUPT_PROJECT
    assert caught.value.message == "Could not read this project file."
