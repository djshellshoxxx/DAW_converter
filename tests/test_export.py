from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from helpers_report import CID, inst, make_kb, ref, scan
from rackcheck_engine import export as E
from rackcheck_engine.model import PluginFormat
from rackcheck_engine.report import ReportOptions, build_report

SPEC_COLUMNS = """record_type, id, parent_id, name, report_generated_at, source_file, daw, daw_version,
project_title, project_artist, project_genre, project_tempo_bpm, project_tempo_changes, project_time_signatures, project_key, project_sample_rate, project_bit_depth, project_length_seconds, project_length_bars, project_markers, project_file_size_bytes, project_modified_at, project_folder_size_bytes, project_backup_count, project_unavailable_fields,
summary_tracks_audio, summary_tracks_midi, summary_tracks_instrument, summary_tracks_return, summary_tracks_group, summary_unique_plugins, summary_plugin_instances, summary_missing_plugins, summary_stock_devices, summary_heuristic_results, summary_media_files, summary_missing_media, summary_media_outside_folder, summary_opens_on_windows, summary_opens_on_mac, summary_send_ready_score, summary_send_ready_reasons,
warning_code, warning_severity, warning_message, warning_related_ids,
track_type, track_color, track_muted, track_solo, track_armed, track_frozen, track_volume_db, track_pan, track_output, track_sends, track_sidechain_sources, track_clip_count, track_midi_note_count, track_midi_range, track_automated_parameters, track_plugin_names,
plugin_track_name, plugin_slot, plugin_nested_in, plugin_role, plugin_format, plugin_vendor, plugin_identity, plugin_bypassed, plugin_version_in_project, plugin_preset_name, plugin_automated, plugin_state_size_bytes, plugin_confidence, plugin_resolution_state, plugin_installed_version, plugin_installed_path, plugin_installed_arch, plugin_other_formats_installed, plugin_category, plugin_licensing, plugin_price_model, plugin_platforms, plugin_formats_available, plugin_apple_silicon_native, plugin_status, plugin_free_alternatives, plugin_homepage, plugin_homepage_source, plugin_manual_url, plugin_support_url, plugin_flags, plugin_kb_last_verified,
ps_vendor, ps_instances, ps_bypassed_instances, ps_tracks, ps_resolution_state, ps_homepage,
media_path, media_type, media_referenced_by, media_exists, media_inside_project_folder, media_size_bytes, media_format, media_sample_rate, media_bit_depth, media_channels, media_duration_seconds, media_sample_rate_mismatch, media_duplicate_of, media_source_hint,
unused_path, unused_size_bytes,
special_type, special_track_name, special_plugin_id, special_path, special_confidence"""  # noqa: E501

EXTRA_COLUMNS = {"summary_most_used_plugin", "plugin_resolution_matched_by",
                 "plugin_resolution_confidence", "plugin_kb_id", "plugin_kb_matched_by",
                 "plugin_kb_confidence", "plugin_kb_verified"}


def _report():
    plugins = [ref(vst3_cid=CID), ref("p2", name="Pro-Q 4", vendor="FabFilter"),
               ref("p3", name="Gone", vendor=None)]
    return build_report(
        scan(plugins, warnings=["note, with comma"]), {"format": "reaper_rpp"},
        inventory=[inst(vst3_cid=CID, version="1.2")], kb=make_kb(),
        options=ReportOptions(scan_folder=False))


def _parse(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text, newline="")))


def test_columns_match_spec_exactly_plus_documented_extras():
    spec = [c.strip() for c in SPEC_COLUMNS.replace("\n", " ").split(",") if c.strip()]
    assert len(spec) == len(set(spec))
    assert [c for c in E.CSV_COLUMNS if c not in EXTRA_COLUMNS] == spec
    assert set(E.CSV_COLUMNS) - set(spec) == EXTRA_COLUMNS
    assert E.PLUGIN_LIST_COLUMNS == ["name", "vendor", "format", "instances", "tracks",
                                     "resolution_state", "homepage", "licensing", "price_model"]


def test_csv_file_rules_bom_crlf_header_and_row_order(tmp_path: Path):
    rep = _report()
    path = E.write_csv(rep, tmp_path / "r.csv")
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    assert "\r\n" in text and text.count("\n") == text.count("\r\n")
    rows = _parse(text)
    assert rows[0] == E.CSV_COLUMNS
    assert all(len(r) == len(E.CSV_COLUMNS) for r in rows)
    types = [r[0] for r in rows[1:]]
    order = ["project", "summary", "warning", "track", "plugin", "plugin_summary"]
    assert [t for i, t in enumerate(types) if i == 0 or types[i - 1] != t] == order
    assert types.count("plugin") == 3 and types.count("plugin_summary") == 3
    assert types.count("project") == 1 and types.count("summary") == 1


def test_csv_values_booleans_empty_and_multivalue():
    rep = _report()
    rows = [dict(zip(E.CSV_COLUMNS, r, strict=True)) for r in _parse(E.report_to_csv(rep))[1:]]
    by = {(r["record_type"], r["id"]): r for r in rows}
    p1 = by[("plugin", "p1")]
    assert p1["plugin_bypassed"] == "FALSE" and p1["plugin_resolution_state"] == \
        "installed_same_format"
    assert p1["plugin_licensing"] == "ilok" and p1["plugin_formats_available"] == "vst2; vst3"
    assert p1["plugin_identity"] == f"vst3_cid={CID}"
    assert p1["plugin_preset_name"] == ""  # unknown -> empty, never guessed
    assert p1["plugin_homepage_source"] == "kb_plugin"
    assert p1["plugin_track_name"] == "Bass" and p1["parent_id"] == "t1"
    assert p1["daw"] == "REAPER" and p1["source_file"].endswith("Song.rpp")
    proj = by[("project", "project")]
    assert proj["project_tempo_bpm"] == "120.0" and proj["project_key"] == ""
    assert "key" in proj["project_unavailable_fields"].split("; ")
    summ = by[("summary", "summary")]
    assert summ["summary_missing_plugins"] == "2"
    assert summ["summary_opens_on_windows"] == "FALSE"  # Pro-Q is Mac-only
    assert summ["summary_send_ready_score"] == "red"
    ps = by[("plugin_summary", "xfer-serum")]
    assert ps["ps_tracks"] == "Bass" and ps["ps_homepage"] == "https://xferrecords.example/serum"
    w = [r for r in rows if r["record_type"] == "warning" and r["warning_code"] == "READER_NOTE"]
    assert w[0]["warning_message"] == "note, with comma"  # RFC 4180 quoting round trip


def test_csv_escaping_of_quotes_commas_newlines_and_unicode(tmp_path: Path):
    tricky = 'He said "hi", ok\nnext line é中'
    rep = build_report(scan([ref(name=tricky, vst3_cid=CID)]), None,
                       inventory=[inst(vst3_cid=CID)], options=ReportOptions(scan_folder=False))
    path = E.write_csv(rep, tmp_path / "t.csv")
    rows = _parse(path.read_bytes().decode("utf-8-sig"))
    idx = E.CSV_COLUMNS.index("name")
    assert [r[idx] for r in rows if r[0] == "plugin"] == [tricky]


def test_csv_formula_injection_is_neutralised_but_numbers_are_untouched():
    assert E.csv_safe("=1+1") == "'=1+1"
    assert E.csv_safe("+SUM(A1)") == "'+SUM(A1)"
    assert E.csv_safe("-2+3") == "'-2+3"
    assert E.csv_safe("@cmd") == "'@cmd"
    assert E.csv_safe("\tx") == "'\tx"
    assert E.csv_safe(["=evil", "ok"]) == "'=evil; ok"
    assert E.csv_safe(-3.5) == "-3.5" and E.csv_safe(-2) == "-2"
    assert E.csv_safe(True) == "TRUE" and E.csv_safe(False) == "FALSE"
    assert E.csv_safe(None) == "" and E.csv_safe("plain") == "plain"
    rep = build_report(scan([ref(name="=HYPERLINK(\"http://evil\")", vst3_cid=CID)]), None,
                       inventory=[inst(vst3_cid=CID)], options=ReportOptions(scan_folder=False))
    rows = _parse(E.report_to_csv(rep))
    idx = E.CSV_COLUMNS.index("name")
    assert all(not r[idx].startswith("=") for r in rows)
    plist = _parse(E.plugin_list_csv(rep))
    assert plist[1][0].startswith("'=")


def test_plugin_list_and_missing_only(tmp_path: Path):
    rep = _report()
    rows = _parse(E.plugin_list_csv(rep))
    assert rows[0] == E.PLUGIN_LIST_COLUMNS
    body = {r[0]: r for r in rows[1:]}
    assert set(body) == {"Serum", "Pro-Q 4", "Gone"}
    assert body["Serum"][2] == "vst3" and body["Serum"][3] == "1" and body["Serum"][4] == "Bass"
    assert body["Serum"][7] == "ilok" and body["Serum"][8] == "paid"
    assert body["Gone"][6].startswith("https://www.kvraudio.com/")  # search fallback
    missing = _parse(E.plugin_list_csv(rep, missing_only=True))
    assert {r[0] for r in missing[1:]} == {"Pro-Q 4", "Gone"}
    path = E.write_plugin_list(rep, tmp_path / "pl.csv", missing_only=True)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_json_export_roundtrip_and_redaction(tmp_path: Path):
    rep = _report()
    path = E.write_json(rep, tmp_path / "r.json")
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert json.loads(raw.decode("utf-8")) == rep
    red = json.loads(E.report_to_json(rep, redact_paths=True))
    assert red["options"]["redact_paths"] is True
    assert red["plugins"][0]["resolution"]["installed"]["path"] is None
    assert rep["plugins"][0]["resolution"]["installed"]["path"]  # source untouched
    unicode_rep = json.loads(E.report_to_json(
        build_report(scan([ref(name="Élan", vst3_cid=CID)]), None, inventory=[])))
    assert unicode_rep["plugins"][0]["name"] == "Élan"


def test_json_and_csv_stay_in_step():
    """SPEC-02 10.3: every JSON plugin field has a CSV column (documented mapping)."""
    rep = _report()
    p = rep["plugins"][0]
    mapped = {"id": "id", "track_id": "parent_id", "slot_index": "plugin_slot",
              "nested_in": "plugin_nested_in", "role": "plugin_role",
              "format": "plugin_format", "name": "name", "vendor": "plugin_vendor",
              "identity": "plugin_identity", "bypassed": "plugin_bypassed",
              "version_in_project": "plugin_version_in_project",
              "preset_name": "plugin_preset_name", "automated": "plugin_automated",
              "state_size_bytes": "plugin_state_size_bytes", "confidence": "plugin_confidence",
              "resolution": "plugin_resolution_state", "kb": "plugin_kb_id",
              "links": "plugin_homepage", "flags": "plugin_flags"}
    assert set(p) == set(mapped)
    assert set(mapped.values()) <= set(E.CSV_COLUMNS)
    for key in rep["summary"]:
        if key in ("track_counts", "opens_on", "send_ready", "most_used_plugin"):
            continue
        assert f"summary_{key}" in E.CSV_COLUMNS


def test_default_filename():
    rep = _report()
    rep["project"]["name"] = 'My: Song/Final?'
    rep["generated_at"] = "2026-09-25T14:32:00-07:00"
    assert E.default_filename(rep, "json") == "My_ Song_Final__rackcheck_2026-09-25_1432.json"
    assert E.default_filename(rep, ".csv").endswith("_1432.csv")


def test_stock_plugin_row_has_no_links_and_unknown_format_fields_blank():
    rep = build_report(scan([ref(name="EQ Eight", vendor=None, fmt=PluginFormat.STOCK)]), None,
                       inventory=[], options=ReportOptions(scan_folder=False))
    rows = [dict(zip(E.CSV_COLUMNS, r, strict=True)) for r in _parse(E.report_to_csv(rep))[1:]]
    p = next(r for r in rows if r["record_type"] == "plugin")
    assert p["plugin_homepage"] == "" and p["plugin_resolution_state"] == "stock"
    assert p["plugin_flags"] == "stock"
