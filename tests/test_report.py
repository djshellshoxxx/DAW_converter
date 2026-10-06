from __future__ import annotations

import json
import wave
from pathlib import Path

from helpers_report import CID, inst, make_kb, ref, scan
from rackcheck_engine.model import Confidence, MediaRef, PluginFormat
from rackcheck_engine.report import (
    ReportOptions,
    build_report,
    plugin_group_key,
    read_audio_header,
    redact_report,
)


def _codes(report, code=None):
    return [w for w in report["warnings"] if code is None or w["code"] == code]


def _build(plugins, inventory, kb=None, **kw):
    return build_report(scan(plugins, **kw), {"format": "reaper_rpp", "confidence": "confirmed",
                                              "reason": "test"},
                        inventory=inventory, kb=kb, options=ReportOptions(scan_folder=False))


def write_wav(path: Path, rate=44100, frames=4410, width=2, channels=2) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(b"\x00" * frames * width * channels)
    return path


# ---- warnings: one test per implemented code ------------------------------------------


def test_plugin_missing():
    r = _build([ref(), ref("p2")], [], make_kb())
    (w,) = _codes(r, "PLUGIN_MISSING")
    assert w["severity"] == "error" and w["related_ids"] == ["p1", "p2"]
    assert "Serum is not installed" in w["message"]
    assert r["summary"]["missing_plugins"] == 1 and r["summary"]["plugin_instances"] == 2
    assert r["summary"]["send_ready"]["score"] == "red"


def test_plugin_other_format():
    r = _build([ref(fmt=PluginFormat.VST2, name="Serum", vendor="Xfer")],
               [inst(vst3_cid=CID)], make_kb())
    (w,) = _codes(r, "PLUGIN_OTHER_FORMAT")
    assert w["severity"] == "warning" and "VST3" in w["message"] and "VST2" in w["message"]
    assert r["plugins"][0]["resolution"]["state"] == "installed_other_format"
    assert r["summary"]["send_ready"]["score"] == "yellow"


def test_plugin_unknown():
    r = _build([ref(name="Mystery", vendor=None)], [inst()], make_kb())
    assert _codes(r, "PLUGIN_UNKNOWN")
    # An installed plugin that the KB has never heard of is identified, so not "unknown".
    r2 = _build([ref(name="Other", vendor="Acme")], [inst(name="Other", vendor="Acme")], make_kb())
    assert not _codes(r2, "PLUGIN_UNKNOWN")


def test_plugin_version_older_and_newer_ok():
    r = _build([ref(version="2.0.1", vst3_cid=CID)], [inst(version="1.9", vst3_cid=CID)],
               make_kb())
    (w,) = _codes(r, "PLUGIN_VERSION_OLDER")
    assert "1.9" in w["message"] and "2.0.1" in w["message"]
    r = _build([ref(version="1.0", vst3_cid=CID)], [inst(version="1.9", vst3_cid=CID)], make_kb())
    assert not _codes(r, "PLUGIN_VERSION_OLDER")
    r = _build([ref(version="weird", vst3_cid=CID)], [inst(version="1.9", vst3_cid=CID)],
               make_kb())
    assert not _codes(r, "PLUGIN_VERSION_OLDER")


def _proq():
    return ref(name="Pro-Q 4", vendor="FabFilter", fmt=PluginFormat.VST2)


def test_kb_flag_warnings_vst2_only_mac_only_discontinued():
    r = _build([_proq()], [inst(name="Pro-Q 4", vendor="FabFilter", fmt=PluginFormat.VST2)],
               make_kb())
    codes = {w["code"] for w in r["warnings"]}
    assert {"PLUGIN_VST2_ONLY", "PLUGIN_MAC_ONLY", "PLUGIN_DISCONTINUED"} <= codes
    assert r["summary"]["opens_on"] == {"windows": False, "mac": True}


def test_win_only_and_ilok():
    kb = make_kb()
    kb.plugins["xfer-serum"].platforms = ["win"]
    r = _build([ref(vst3_cid=CID)], [inst(vst3_cid=CID)], kb)
    codes = {w["code"] for w in r["warnings"]}
    assert {"PLUGIN_WIN_ONLY", "PLUGIN_DRM_ILOK"} <= codes
    assert r["summary"]["opens_on"] == {"windows": True, "mac": False}


def test_unverified_kb_data_makes_no_claims():
    r = _build([_proq()], [inst(name="Pro-Q 4", vendor="FabFilter", fmt=PluginFormat.VST2)],
               make_kb(verified=False))
    codes = {w["code"] for w in r["warnings"]}
    assert not codes & {"PLUGIN_VST2_ONLY", "PLUGIN_MAC_ONLY", "PLUGIN_DISCONTINUED",
                        "PLUGIN_DRM_ILOK"}
    assert r["plugins"][0]["kb"]["apple_silicon_native"] is None
    assert r["plugins"][0]["kb"]["verified"] is False


def test_intel_only_needs_mac_binary_and_32bit():
    r = _build([ref(vst3_cid=CID)],
               [inst(vst3_cid=CID, archs=["x86_64"], path="/Library/Audio/Plug-Ins/VST3/S.vst3")],
               make_kb())
    assert _codes(r, "PLUGIN_INTEL_ONLY")
    # x86_64-only on Windows is normal, not a warning.
    r = _build([ref(vst3_cid=CID)], [inst(vst3_cid=CID, archs=["x86_64"])], make_kb())
    assert not _codes(r, "PLUGIN_INTEL_ONLY")
    r = _build([ref(vst3_cid=CID)], [inst(vst3_cid=CID, archs=["i386"])], make_kb())
    assert _codes(r, "PLUGIN_32BIT")
    r = _build([ref(vst3_cid=CID)], [inst(vst3_cid=CID, archs=["arm64", "x86_64"],
                                          path="/Library/x.vst3")], make_kb())
    assert not _codes(r, "PLUGIN_INTEL_ONLY")


def test_stock_device_daw_and_no_missing_for_stock():
    r = _build([ref("p1", name="EQ Eight", vendor=None, fmt=PluginFormat.STOCK),
                ref("p2", name="ReaEQ", vendor=None, fmt=PluginFormat.JS)], [], make_kb())
    (w,) = _codes(r, "STOCK_DEVICE_DAW")
    assert w["related_ids"] == ["p1", "p2"] and "REAPER" in w["message"]
    assert r["summary"]["stock_devices"] == 2 and r["summary"]["missing_plugins"] == 0
    assert r["summary"]["unique_plugins"] == 0
    assert not _codes(r, "PLUGIN_MISSING")
    assert r["plugins"][0]["links"]["homepage"]["url"] is None


def test_heuristic_results_warning_and_count():
    r = _build([ref(conf=Confidence.HEURISTIC, vst3_cid=CID)], [inst(vst3_cid=CID)], make_kb())
    assert _codes(r, "HEURISTIC_RESULTS")
    assert r["summary"]["heuristic_results"] == 1
    assert "heuristic" in r["plugins"][0]["flags"]


def test_inventory_unavailable_never_claims_missing():
    r = _build([ref()], None, make_kb())
    assert r["plugins"][0]["resolution"]["state"] == "inventory_unavailable"
    assert not _codes(r, "PLUGIN_MISSING")
    assert _codes(r, "INVENTORY_UNAVAILABLE")
    assert r["summary"]["missing_plugins"] == 0
    assert r["summary"]["send_ready"]["score"] == "yellow"


def test_reader_warnings_pass_through():
    r = build_report(scan([], warnings=["odd thing"]), None, inventory=[],
                     options=ReportOptions(scan_folder=False))
    (w,) = _codes(r, "READER_NOTE")
    assert w["message"] == "odd thing" and w["severity"] == "info"


def test_external_hardware_warning_uses_track_ids():
    r = _build([], [], make_kb(), fmt="ableton_als",
               external_hardware_tracks=["t1", "t1", "t2"])
    (warning,) = _codes(r, "EXTERNAL_HARDWARE")
    assert warning["severity"] == "warning"
    assert warning["related_ids"] == ["t1", "t2"]
    assert "external audio hardware" in warning["message"]


def test_green_when_clean():
    r = _build([ref(vst3_cid=CID)], [inst(vst3_cid=CID)], make_kb())
    assert r["summary"]["send_ready"] == {"score": "green", "reasons": []}


# ---- media (9.6) and folder facts ---------------------------------------------------------


def _project_with_media(tmp_path: Path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "Song.rpp").write_text("x", encoding="utf-8")
    a = write_wav(proj / "Audio" / "a.wav", rate=44100)
    dup = proj / "Audio" / "a_copy.wav"
    dup.write_bytes(a.read_bytes())
    outside = write_wav(tmp_path / "Downloads" / "loop.wav", rate=48000)
    unused = write_wav(proj / "Audio" / "unused.wav", rate=48000, frames=100)
    (proj / "Backup").mkdir()
    (proj / "Backup" / "Song-1.rpp-bak").write_text("x", encoding="utf-8")
    media = [MediaRef(path=str(a)), MediaRef(path=str(dup)), MediaRef(path=str(outside)),
             MediaRef(path=str(proj / "gone.wav")), MediaRef(path="Audio/a.wav")]
    return proj, media, unused, a, outside


def test_media_facts_and_warnings(tmp_path: Path):
    proj, media, unused, a, outside = _project_with_media(tmp_path)
    s = scan([], media=media, path=str(proj / "Song.rpp"))
    r = build_report(s, None, inventory=[], options=ReportOptions())
    m = {x["path"]: x for x in r["media"]}
    first = m[str(a)]
    assert first["exists"] is True and first["inside_project_folder"] is True
    assert first["audio"] == {"format": "wav", "sample_rate": 44100, "bit_depth": 16,
                              "channels": 2, "duration_seconds": 0.1}
    assert first["sample_rate_mismatch"] is True and len(first["sha256"]) == 64
    assert m[str(proj / "Audio" / "a_copy.wav")]["duplicate_of"] == first["id"]
    assert m[str(outside)]["inside_project_folder"] is False
    assert m[str(outside)]["source_hint"] == {"value": "downloads", "confidence": "heuristic"}
    assert m[str(proj / "gone.wav")]["exists"] is False
    assert m["Audio/a.wav"]["exists"] is True  # relative paths resolve against the project
    (miss,) = _codes(r, "MEDIA_MISSING")
    assert miss["severity"] == "error" and len(miss["related_ids"]) == 1
    (out,) = _codes(r, "MEDIA_OUTSIDE_FOLDER")
    assert out["related_ids"] == [m[str(outside)]["id"]]
    assert _codes(r, "MEDIA_SR_MISMATCH")
    (un,) = _codes(r, "MEDIA_UNUSED")
    assert "1 audio file" in un["message"]
    assert [u["path"] for u in r["unused_media"]] == [str(unused)]
    f = r["project"]["folder"]
    assert f["file_count"] >= 5 and f["backup_count"] == 1 and f["newest_backup_at"]
    assert r["summary"]["missing_media"] == 1 and r["summary"]["media_outside_folder"] == 1
    assert r["source"]["file_size_bytes"] == 1


def test_read_audio_header_wav_flac_aiff(tmp_path: Path):
    w = write_wav(tmp_path / "x.wav", rate=96000, frames=96000, width=3, channels=1)
    assert read_audio_header(w) == {"format": "wav", "sample_rate": 96000, "bit_depth": 24,
                                    "channels": 1, "duration_seconds": 1.0}
    # FLAC: STREAMINFO with 44.1 kHz, 2 ch, 16 bit, 44100 samples
    packed = (44100 << 44) | (1 << 41) | (15 << 36) | 44100
    body = b"\x00" * 10 + packed.to_bytes(8, "big") + b"\x00" * 16
    flac = tmp_path / "x.flac"
    flac.write_bytes(b"fLaC" + bytes([0x00, 0, 0, 34]) + body)
    assert read_audio_header(flac) == {"format": "flac", "sample_rate": 44100, "bit_depth": 16,
                                       "channels": 2, "duration_seconds": 1.0}
    # AIFF with an 80-bit extended 44100 Hz rate
    ext = (16383 + 15).to_bytes(2, "big") + (44100 << 48).to_bytes(8, "big")
    comm = (2).to_bytes(2, "big") + (44100).to_bytes(4, "big") + (16).to_bytes(2, "big") + ext
    aiff = tmp_path / "x.aiff"
    aiff.write_bytes(b"FORM" + (4 + 8 + 18).to_bytes(4, "big") + b"AIFF" + b"COMM"
                     + (18).to_bytes(4, "big") + comm)
    info = read_audio_header(aiff)
    assert (info["sample_rate"], info["channels"], info["duration_seconds"]) == (44100, 2, 1.0)
    (tmp_path / "bad.wav").write_bytes(b"RIFF\x00")
    assert read_audio_header(tmp_path / "bad.wav") is None
    assert read_audio_header(tmp_path / "missing.wav") is None


def test_loose_folder_skips_folder_scan(tmp_path: Path, monkeypatch):
    import rackcheck_engine.report as rep

    (tmp_path / "Song.rpp").write_text("x", encoding="utf-8")
    write_wav(tmp_path / "other.wav")
    monkeypatch.setattr(rep, "_is_loose_folder", lambda f: True)
    r = build_report(scan([], path=str(tmp_path / "Song.rpp")), None, inventory=[])
    assert r["unused_media"] == []
    assert r["project"]["folder"]["file_count"] is None
    assert not _codes(r, "MEDIA_UNUSED")


# ---- structure / redaction -------------------------------------------------------------------


def test_json_schema_shape_and_serializable():
    r = _build([ref(vst3_cid=CID), ref("p2", vst3_cid=CID, bypassed=True)],
               [inst(vst3_cid=CID, archs=["arm64"])], make_kb())
    json.dumps(r)
    assert list(r) == ["schema_version", "generated_at", "app", "machine", "options", "source",
                       "project", "tracks", "plugins", "plugin_summary", "media",
                       "unused_media", "special_content", "summary", "warnings"]
    assert r["schema_version"] == "1.0.0"
    assert r["app"]["name"] == "Rackcheck" and r["app"]["kb_version"] == "test-kb"
    assert {"path", "file_size_bytes", "created_at", "modified_at", "format",
            "detection_confidence", "detection_reason", "daw_name", "daw_version",
            "reader_version"} == set(r["source"])
    assert {"name", "title", "artist", "genre", "comments", "tempo_bpm", "tempo_changes",
            "time_signatures", "key", "sample_rate", "bit_depth", "length_seconds",
            "length_bars", "markers", "loop", "alternatives", "folder",
            "unavailable_fields"} == set(r["project"])
    assert r["project"]["tempo_changes"] == [{"position_beats": 0, "bpm": 120.0}]
    assert {"key", "bit_depth"} <= set(r["project"]["unavailable_fields"])
    assert {"id", "name", "type", "parent_id", "color", "muted", "solo", "armed", "frozen",
            "volume_db", "pan", "output", "sends", "sidechain_sources", "clip_count", "midi",
            "automated_parameters", "device_ids"} == set(r["tracks"][0])
    p = r["plugins"][0]
    assert {"id", "track_id", "slot_index", "nested_in", "role", "format", "name", "vendor",
            "identity", "bypassed", "version_in_project", "preset_name", "automated",
            "state_size_bytes", "confidence", "resolution", "kb", "links", "flags"} == set(p)
    assert {"state", "matched_by", "installed", "other_formats_installed"} <= set(p["resolution"])
    assert p["resolution"]["installed"] == {"version": "1.0", "path": "C:/VST3/Serum.vst3",
                                            "arch": "arm64"}
    assert {"homepage", "manual", "support"} == set(p["links"])
    assert {"kb_id", "category", "licensing", "price_model", "platforms", "formats_available",
            "apple_silicon_native", "status", "successor_id", "free_alternatives",
            "last_verified"} <= set(p["kb"])
    assert {"vst3_cid", "vst2_unique_id", "au", "clap_id", "aax", "file_hint"} <= set(p["identity"])
    (ps,) = r["plugin_summary"]
    assert ps == {"key": "xfer-serum", "name": "Serum", "vendor": "Xfer Records",
                  "instances": 2, "track_ids": ["t1"], "bypassed_instances": 1,
                  "resolution_state": "installed_same_format"}
    s = r["summary"]
    assert {"track_counts", "unique_plugins", "plugin_instances", "missing_plugins",
            "stock_devices", "heuristic_results", "media_files", "missing_media",
            "media_outside_folder", "opens_on", "send_ready", "most_used_plugin"} == set(s)
    assert s["most_used_plugin"] == {"key": "xfer-serum", "name": "Serum", "instances": 2}
    assert s["track_counts"]["instrument"] == 1
    assert {"code", "severity", "message", "related_ids"} == set(r["warnings"][0]) or not r[
        "warnings"]


def test_group_key_merges_formats_via_kb_and_falls_back():
    r = _build([ref("p1", vst3_cid=CID), ref("p2", fmt=PluginFormat.VST2, name="Serum",
                                             vendor="Xfer")], [], make_kb())
    assert len(r["plugin_summary"]) == 1 and r["plugin_summary"][0]["instances"] == 2
    assert plugin_group_key({"name": "Foo (x64)", "vendor": "Bar", "format": "vst3",
                             "kb": None}) == "unmatched:foo|bar"


def test_max_for_live_special_content():
    m4l = ref("p1", name="MyDevice", vendor=None, fmt=PluginFormat.STOCK, file_hint="MyDevice.amxd")
    r = _build([m4l], [], None)
    assert r["special_content"] == [{"type": "max_for_live", "name": "MyDevice",
                                     "track_id": "t1", "plugin_id": "p1",
                                     "path": "MyDevice.amxd", "confidence": "confirmed"}]


def test_redact_paths(tmp_path: Path):
    home = tmp_path / "home" / "me"
    proj = home / "Music" / "proj"
    (proj / "Audio").mkdir(parents=True)
    (proj / "Song.rpp").write_text("x", encoding="utf-8")
    inside = write_wav(proj / "Audio" / "in.wav")
    outside = write_wav(home / "Downloads" / "out.wav")
    r = build_report(scan([ref(vst3_cid=CID)], media=[MediaRef(path=str(inside)),
                                                       MediaRef(path=str(outside))],
                          path=str(proj / "Song.rpp")),
                     None, inventory=[inst(vst3_cid=CID)], kb=make_kb())
    red = redact_report(r, home=str(home))
    assert red["source"]["path"] == "~/Music/proj/Song.rpp"
    assert red["project"]["folder"]["path"] == "~/Music/proj"
    assert [m["path"] for m in red["media"]] == ["Audio/in.wav", "out.wav"]
    assert red["plugins"][0]["resolution"]["installed"]["path"] is None
    assert red["options"]["redact_paths"] is True
    assert r["options"]["redact_paths"] is False  # original untouched
    assert str(home) not in json.dumps(red)
