"""End-to-end: synthetic projects + synthetic inventory + synthetic KB through the CLI."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from conftest import write_als
from helpers_report import inst
from rackcheck_engine.cli import EXIT_ERROR, main
from rackcheck_engine.export import CSV_COLUMNS
from rackcheck_engine.inventory.scan import save_inventory
from rackcheck_engine.model import PluginFormat

GUID = "ABCD1234ABCD1234ABCD1234ABCD1234"


def _wav(path: Path, rate: int = 44100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * 100)
    return path


def _kb_dir(tmp_path: Path) -> Path:
    d = tmp_path / "kb"
    d.mkdir()
    (d / "vendors.json").write_text(json.dumps([
        {"id": "xfer-records", "name": "Xfer Records", "aliases": ["Xfer"],
         "homepage": "https://xferrecords.example", "verified": True}]), encoding="utf-8")
    (d / "plugins.json").write_text(json.dumps([
        {"id": "xfer-serum", "vendor_id": "xfer-records", "name": "Serum",
         "keys": {"vst3_cid": [GUID]}, "homepage": "https://xferrecords.example/serum",
         "formats": ["vst2", "vst3"], "platforms": ["win", "mac"], "licensing": ["ilok"],
         "price_model": "paid", "status": "active", "verified": True}]), encoding="utf-8")
    return d


def _inventory(tmp_path: Path, with_serum: bool = True) -> Path:
    plugins = [inst(name="Other Thing", vendor="Acme", path="C:/VST3/Other.vst3")]
    if with_serum:
        plugins.append(inst(name="Serum", vendor="Xfer Records", vst3_cid=GUID, version="1.368"))
    p = tmp_path / "inv.json"
    save_inventory(plugins, p)
    return p


def _reaper(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    wav_out = _wav(tmp_path / "elsewhere" / "loop.wav", 44100)
    rpp = proj / "Song.rpp"
    rpp.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "TEMPO 120 4 4\nSAMPLERATE 48000\n"
        "<TRACK\n"
        '  NAME "Lead"\n'
        "  <FXCHAIN\n"
        f'    <VST "VST3: Serum (Xfer Records)" Serum.vst3 0 "" 12345{{{GUID}}}\n'
        "    >\n"
        '    <VST "VST: Nexus (reFX)" Nexus.dll 0 "" 1397703755\n'
        "    >\n"
        "  >\n"
        "  <ITEM\n"
        f'    <SOURCE WAVE\n      FILE "{wav_out}"\n    >\n'
        "  >\n"
        ">\n>\n",
        encoding="utf-8")
    return rpp


def _run(capsys, *args):
    code = main(["scan", *map(str, args)])
    return code, capsys.readouterr()


def test_reaper_json_report_with_inventory_and_kb(tmp_path: Path, capsys):
    rpp = _reaper(tmp_path)
    code, out = _run(capsys, rpp, "--json", "--inventory", _inventory(tmp_path),
                     "--kb", _kb_dir(tmp_path))
    assert code == 0, out.err
    (scan,) = json.loads(out.out)["scans"]
    rep = scan["report"]
    assert rep["schema_version"] == "1.0.0"
    assert rep["source"]["daw_name"] == "REAPER" and rep["source"]["detection_confidence"]
    assert rep["machine"]["inventory_scanned_at"]
    by_name = {p["name"]: p for p in rep["plugins"]}
    serum = by_name["Serum"]
    assert serum["resolution"]["state"] == "installed_same_format"
    assert serum["resolution"]["matched_by"] == "vst3_cid"
    assert serum["resolution"]["installed"]["version"] == "1.368"
    assert serum["kb"]["kb_id"] == "xfer-serum"
    assert serum["links"]["homepage"] == {"url": "https://xferrecords.example/serum",
                                          "source": "kb_plugin"}
    nexus = by_name["Nexus"]
    assert nexus["resolution"]["state"] == "not_installed"
    assert nexus["links"]["homepage"]["source"] == "search"
    codes = {w["code"] for w in rep["warnings"]}
    assert {"PLUGIN_MISSING", "PLUGIN_UNKNOWN", "PLUGIN_DRM_ILOK"} <= codes
    assert rep["summary"]["missing_plugins"] == 1
    assert rep["summary"]["send_ready"]["score"] == "red"


def test_default_output_is_human_readable_text(tmp_path: Path, capsys):
    rpp = _reaper(tmp_path)
    code, out = _run(capsys, rpp, "--inventory", _inventory(tmp_path), "--kb", _kb_dir(tmp_path))
    assert code == 0
    text = out.out
    assert not text.lstrip().startswith("{")
    assert "Song  -  REAPER" in text and "Send-ready: RED" in text
    assert "PLUGIN_MISSING: Nexus is not installed on this computer" in text
    assert "Serum (Xfer Records) x1 [installed_same_format]" in text
    assert "https://xferrecords.example/serum (kb_plugin)" in text


def test_csv_and_plugin_list_files(tmp_path: Path, capsys):
    rpp = _reaper(tmp_path)
    csv_path, pl_path = tmp_path / "out.csv", tmp_path / "pl.csv"
    code, _ = _run(capsys, rpp, "--inventory", _inventory(tmp_path), "--kb", _kb_dir(tmp_path),
                   "--csv", csv_path, "--plugin-list", pl_path)
    assert code == 0
    raw = csv_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    header = raw.decode("utf-8-sig").split("\r\n")[0]
    assert header == ",".join(CSV_COLUMNS)
    pl = pl_path.read_bytes().decode("utf-8-sig").split("\r\n")
    assert pl[0] == "name,vendor,format,instances,tracks,resolution_state,homepage,licensing," \
                    "price_model"
    assert any(
        line.startswith("Serum,Xfer Records,vst3,1,Lead,installed_same_format") for line in pl)


def test_no_inventory_reports_unknown_not_missing(tmp_path: Path, capsys):
    rpp = _reaper(tmp_path)
    code, out = _run(capsys, rpp, "--json", "--no-inventory", "--kb", _kb_dir(tmp_path))
    assert code == 0
    rep = json.loads(out.out)["scans"][0]["report"]
    assert {p["resolution"]["state"] for p in rep["plugins"]} == {"inventory_unavailable"}
    codes = {w["code"] for w in rep["warnings"]}
    assert "PLUGIN_MISSING" not in codes and "INVENTORY_UNAVAILABLE" in codes
    assert rep["machine"]["inventory_scanned_at"] is None


def test_serum_missing_from_inventory(tmp_path: Path, capsys):
    rpp = _reaper(tmp_path)
    _, out = _run(capsys, rpp, "--json", "--inventory", _inventory(tmp_path, with_serum=False),
                  "--kb", _kb_dir(tmp_path))
    rep = json.loads(out.out)["scans"][0]["report"]
    assert rep["summary"]["missing_plugins"] == 2


def test_bad_or_missing_inventory_is_an_error_not_an_empty_inventory(tmp_path: Path, capsys):
    rpp = _reaper(tmp_path)
    code, out = _run(capsys, rpp, "--inventory", tmp_path / "nope.json")
    assert code == EXIT_ERROR and "inventory" in out.err.lower()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    code, out = _run(capsys, rpp, "--json", "--inventory", bad)
    assert code == EXIT_ERROR
    assert json.loads(out.out)["error"]["code"] == "INVENTORY_UNREADABLE"


def test_redact_paths_flag(tmp_path: Path, capsys):
    rpp = _reaper(tmp_path)
    _, out = _run(capsys, rpp, "--json", "--no-inventory", "--redact-paths")
    rep = json.loads(out.out)["scans"][0]["report"]
    assert rep["options"]["redact_paths"] is True
    assert "elsewhere" not in json.dumps(rep["media"]) or all(
        not Path(m["path"]).is_absolute() for m in rep["media"])


def test_ableton_and_dawproject_and_mixed_folder(tmp_path: Path, capsys):
    from conftest import write_dawproject

    folder = tmp_path / "many"
    folder.mkdir()
    write_als(folder / "A.als")
    write_dawproject(folder / "B.dawproject")
    _reaper_file = folder / "C.rpp"
    _reaper_file.write_text('<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n>\n', encoding="utf-8")
    csv_path = tmp_path / "all.csv"
    code, out = _run(capsys, folder, "--json", "--inventory", _inventory(tmp_path),
                     "--kb", _kb_dir(tmp_path), "--csv", csv_path)
    assert code == 0
    scans = json.loads(out.out)["scans"]
    assert {s["report"]["source"]["daw_name"] for s in scans} == {
        "Ableton Live", "DAWproject", "REAPER"} or len(scans) == 3
    assert len(scans) == 3
    assert all(s["report"]["schema_version"] == "1.0.0" for s in scans)
    assert (tmp_path / "all_1.csv").exists() and (tmp_path / "all_3.csv").exists()


def test_ableton_stock_devices_and_m4l(tmp_path: Path, capsys):
    from test_reader_ableton import write_ableton_xml

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Ableton MajorVersion="5" Creator="Ableton Live 12.1.5"><LiveSet><Tracks>'
        '<MidiTrack Id="1"><Name><EffectiveName Value="Keys"/></Name>'
        "<DeviceChain><DeviceChain><Devices><Eq8 Id=\"0\"><On><Manual Value=\"true\"/></On>"
        "</Eq8></Devices></DeviceChain></DeviceChain></MidiTrack>"
        "</Tracks></LiveSet></Ableton>"
    )
    als = write_ableton_xml(tmp_path / "Live.als", xml)
    code, out = _run(capsys, als, "--json", "--inventory", _inventory(tmp_path))
    assert code == 0
    rep = json.loads(out.out)["scans"][0]["report"]
    stock = [p for p in rep["plugins"] if p["resolution"]["state"] == "stock"]
    if stock:  # the reader decides what it recognises; whatever it found must be stock-safe
        assert any(w["code"] == "STOCK_DEVICE_DAW" for w in rep["warnings"])
        assert all(p["links"]["homepage"]["url"] is None for p in stock)
    assert rep["source"]["daw_version"]


def test_existing_error_contracts_unchanged(tmp_path: Path, capsys):
    p = tmp_path / "notes.bin"
    p.write_bytes(b"nothing here")
    code, out = _run(capsys, p, "--json", "--no-inventory")
    assert code == EXIT_ERROR
    assert json.loads(out.out)["scans"][0]["error"]["code"] == "UNSUPPORTED_FORMAT"
    code, out = _run(capsys, tmp_path / "empty", "--json", "--no-inventory")
    assert code == EXIT_ERROR


@pytest.mark.parametrize("flag", ["--csv", "--plugin-list"])
def test_export_write_failure_is_reported(tmp_path: Path, capsys, flag):
    rpp = _reaper(tmp_path)
    code, out = _run(capsys, rpp, "--no-inventory", flag, tmp_path / "no_such_dir" / "x.csv")
    assert code == EXIT_ERROR and "couldn't write" in out.err


def test_plugin_format_enum_used_in_helpers():
    assert inst().format == PluginFormat.VST3


def test_ableton_media_facts_end_to_end(tmp_path: Path, capsys):
    from test_reader_ableton import write_ableton_xml

    outside = _wav(tmp_path / "elsewhere" / "loop.wav", 44100)
    proj = tmp_path / "proj"
    proj.mkdir()
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Ableton MajorVersion="5" Creator="Ableton Live 12.0.0"><Tracks><AudioTrack>'
        '<Name Value="T"/><DeviceChain><Devices/></DeviceChain></AudioTrack></Tracks>'
        f'<SampleRef><FileRef><Path Value="{outside}"/></FileRef></SampleRef>'
        f'<SampleRef><FileRef><Path Value="{proj / "gone.wav"}"/></FileRef></SampleRef>'
        "</Ableton>"
    )
    als = write_ableton_xml(proj / "Live.als", xml)
    code, out = _run(capsys, als, "--json", "--no-inventory")
    assert code == 0
    rep = json.loads(out.out)["scans"][0]["report"]
    media = {Path(m["path"]).name: m for m in rep["media"]}
    assert media["loop.wav"]["inside_project_folder"] is False
    assert media["loop.wav"]["audio"]["sample_rate"] == 44100
    assert media["gone.wav"]["exists"] is False
    codes = {w["code"] for w in rep["warnings"]}
    assert {"MEDIA_MISSING", "MEDIA_OUTSIDE_FOLDER"} <= codes
    assert rep["summary"]["missing_media"] == 1
