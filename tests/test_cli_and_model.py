from __future__ import annotations

import json
from pathlib import Path

from conftest import write_als, write_logic_bundle
from rackcheck_engine.cli import EXIT_ERROR, main
from rackcheck_engine.model import (
    Confidence,
    PluginFormat,
    PluginRef,
    PluginRole,
    ScanResult,
    SourceInfo,
    TrackRef,
    TrackType,
)


def test_scan_json_reports_reader_not_available(tmp_path: Path, capsys):
    # Logic has no reader until Phase 4.
    write_logic_bundle(tmp_path / "Song.logicx")
    code = main(["scan", str(tmp_path / "Song.logicx"), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == EXIT_ERROR
    scan = out["scans"][0]
    assert scan["detection"]["format"] == "logic_bundle"
    assert scan["error"]["code"] == "READER_NOT_AVAILABLE"


def test_scan_json_reads_ableton(tmp_path: Path, capsys):
    write_als(tmp_path / "Song.als")
    code = main(["scan", str(tmp_path / "Song.als"), "--json", "--no-inventory"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["scans"][0]["report"]["source"]["daw_version"]


def test_scan_unsupported_file(tmp_path: Path, capsys):
    p = tmp_path / "notes.bin"
    p.write_bytes(b"nothing here")
    code = main(["scan", str(p), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == EXIT_ERROR
    assert out["scans"][0]["error"]["code"] == "UNSUPPORTED_FORMAT"


def test_scan_empty_folder(tmp_path: Path, capsys):
    code = main(["scan", str(tmp_path), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == EXIT_ERROR
    assert out["error"]["code"] == "NO_PROJECT_FOUND"


def test_detect_command(tmp_path: Path, capsys):
    write_als(tmp_path / "Song.als")
    assert main(["detect", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [d["format"] for d in out] == ["ableton_als"]


def test_scan_result_serializes_to_spec_shape():
    result = ScanResult(
        source=SourceInfo(path="x.als", format="ableton_als", daw_name="Ableton Live"),
        tracks=[TrackRef(id="t1", name="Bass", type=TrackType.INSTRUMENT, devices=["p1"])],
        plugins=[
            PluginRef(
                id="p1",
                track_id="t1",
                slot_index=0,
                role=PluginRole.INSTRUMENT,
                format=PluginFormat.VST3,
                name="Surge XT",
                vendor="Surge Synth Team",
                confidence=Confidence.CONFIRMED,
            )
        ],
    )
    data = json.loads(result.to_json())
    assert set(data) == {"source", "project", "tracks", "plugins", "media", "warnings"}
    plugin = data["plugins"][0]
    assert plugin["format"] == "vst3"
    assert plugin["confidence"] == "confirmed"
    assert plugin["identity"]["vst3_cid"] is None
    assert plugin["bypassed"] is None
    assert data["project"]["tempo_bpm"] is None
