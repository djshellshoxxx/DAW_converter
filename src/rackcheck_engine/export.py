"""Report exports (SPEC-02 section 10): full JSON, full CSV, plugin list CSVs.

CSV follows 10.1/10.3: RFC 4180 quoting, UTF-8 with BOM, CRLF, one header row, multi-value
cells joined with "; ", booleans TRUE/FALSE, unknown = empty cell. Text cells that a
spreadsheet could read as a formula are neutralised (see ``csv_safe``).
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

from .report import plugin_group_key, redact_report

COMMON = ["record_type", "id", "parent_id", "name", "report_generated_at", "source_file",
          "daw", "daw_version"]
PROJECT = ["project_title", "project_artist", "project_genre", "project_tempo_bpm",
           "project_tempo_changes", "project_time_signatures", "project_key",
           "project_sample_rate", "project_bit_depth", "project_length_seconds",
           "project_length_bars", "project_markers", "project_file_size_bytes",
           "project_modified_at", "project_folder_size_bytes", "project_backup_count",
           "project_unavailable_fields"]
SUMMARY = ["summary_tracks_audio", "summary_tracks_midi", "summary_tracks_instrument",
           "summary_tracks_return", "summary_tracks_group", "summary_unique_plugins",
           "summary_plugin_instances", "summary_missing_plugins", "summary_stock_devices",
           "summary_heuristic_results", "summary_media_files", "summary_missing_media",
           "summary_media_outside_folder", "summary_opens_on_windows", "summary_opens_on_mac",
           "summary_send_ready_score", "summary_send_ready_reasons",
           "summary_most_used_plugin"]  # last one: SPEC-02 9.8 derived fact, see DECISIONS.md
WARNING = ["warning_code", "warning_severity", "warning_message", "warning_related_ids"]
TRACK = ["track_type", "track_color", "track_muted", "track_solo", "track_armed",
         "track_frozen", "track_volume_db", "track_pan", "track_output", "track_sends",
         "track_sidechain_sources", "track_clip_count", "track_midi_note_count",
         "track_midi_range", "track_automated_parameters", "track_plugin_names"]
PLUGIN = ["plugin_track_name", "plugin_slot", "plugin_nested_in", "plugin_role",
          "plugin_format", "plugin_vendor", "plugin_identity", "plugin_bypassed",
          "plugin_version_in_project", "plugin_preset_name", "plugin_automated",
          "plugin_state_size_bytes", "plugin_confidence", "plugin_resolution_state",
          "plugin_installed_version", "plugin_installed_path", "plugin_installed_arch",
          "plugin_other_formats_installed", "plugin_category", "plugin_licensing",
          "plugin_price_model", "plugin_platforms", "plugin_formats_available",
          "plugin_apple_silicon_native", "plugin_status", "plugin_free_alternatives",
          "plugin_homepage", "plugin_homepage_source", "plugin_manual_url",
          "plugin_support_url", "plugin_flags", "plugin_kb_last_verified",
          # match provenance fields that the JSON carries (10.3 parity rule)
          "plugin_resolution_matched_by", "plugin_resolution_confidence", "plugin_kb_id",
          "plugin_kb_matched_by", "plugin_kb_confidence", "plugin_kb_verified"]
PLUGIN_SUMMARY = ["ps_vendor", "ps_instances", "ps_bypassed_instances", "ps_tracks",
                  "ps_resolution_state", "ps_homepage"]
MEDIA = ["media_path", "media_type", "media_referenced_by", "media_exists",
         "media_inside_project_folder", "media_size_bytes", "media_format",
         "media_sample_rate", "media_bit_depth", "media_channels", "media_duration_seconds",
         "media_sample_rate_mismatch", "media_duplicate_of", "media_source_hint"]
UNUSED = ["unused_path", "unused_size_bytes"]
SPECIAL = ["special_type", "special_track_name", "special_plugin_id", "special_path",
           "special_confidence"]

CSV_COLUMNS = (COMMON + PROJECT + SUMMARY + WARNING + TRACK + PLUGIN + PLUGIN_SUMMARY
               + MEDIA + UNUSED + SPECIAL)

PLUGIN_LIST_COLUMNS = ["name", "vendor", "format", "instances", "tracks", "resolution_state",
                       "homepage", "licensing", "price_model"]

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: Any) -> str:
    """Render one CSV cell.

    None -> empty; bool -> TRUE/FALSE; numbers as-is (a negative number is a number, not
    a formula); lists joined with "; ". Strings starting with a formula trigger
    (``= + - @`` tab CR) get a leading apostrophe so Excel/Sheets show them as text.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    if isinstance(value, (list, tuple)):
        text = "; ".join(csv_safe_item(v) for v in value)
    elif isinstance(value, dict):
        text = "; ".join(f"{k}={csv_safe_item(v)}" for k, v in value.items())
    else:
        text = str(value)
    if text.startswith(_FORMULA_START):
        return "'" + text
    return text


def csv_safe_item(v: Any) -> str:
    """Element inside a multi-value cell: no per-item guard, the whole cell is guarded."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, dict):
        return ", ".join(f"{k}={csv_safe_item(x)}" for k, x in v.items())
    return str(v)


def _prepare(report: dict[str, Any], redact: bool) -> dict[str, Any]:
    return redact_report(report) if redact else report


# ---- JSON -------------------------------------------------------------------------


def report_to_json(report: dict[str, Any], *, redact_paths: bool = False) -> str:
    return json.dumps(_prepare(report, redact_paths), indent=2, ensure_ascii=False) + "\n"


def write_json(report: dict[str, Any], path: str | Path, *, redact_paths: bool = False) -> Path:
    p = Path(path)
    p.write_text(report_to_json(report, redact_paths=redact_paths), encoding="utf-8",
                 newline="\n")
    return p


# ---- CSV (full) -------------------------------------------------------------------


def _join_pairs(items: list[dict[str, Any]], a: str, b: str) -> str:
    return "; ".join(f"{i.get(a)}:{i.get(b)}" for i in items)


def _identity_text(identity: dict[str, Any]) -> str:
    parts = []
    if identity.get("vst3_cid"):
        parts.append(f"vst3_cid={identity['vst3_cid']}")
    if identity.get("vst2_unique_id"):
        asc = identity.get("vst2_ascii")
        parts.append(f"vst2={identity['vst2_unique_id']}" + (f" ({asc})" if asc else ""))
    au = identity.get("au")
    if au:
        parts.append(f"au={au.get('type')}/{au.get('subtype')}/{au.get('manufacturer')}")
    if identity.get("clap_id"):
        parts.append(f"clap={identity['clap_id']}")
    if identity.get("aax"):
        parts.append("aax=" + ",".join(f"{k}:{v}" for k, v in identity["aax"].items()))
    if identity.get("file_hint"):
        parts.append(f"file={identity['file_hint']}")
    return "; ".join(parts)


def csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows in the SPEC-02 10.3 order as dicts keyed by column (values still raw)."""
    src, prj, summ = report["source"], report["project"], report["summary"]
    common = {"report_generated_at": report["generated_at"], "source_file": src["path"],
              "daw": src["daw_name"], "daw_version": src["daw_version"]}
    track_name = {t["id"]: t["name"] for t in report["tracks"]}
    rows: list[dict[str, Any]] = []

    def row(rtype: str, id_: Any = None, parent: Any = None, name: Any = None, **cols: Any):
        rows.append({"record_type": rtype, "id": id_, "parent_id": parent, "name": name,
                     **common, **cols})

    row("project", "project", None, prj["name"],
        project_title=prj["title"], project_artist=prj["artist"], project_genre=prj["genre"],
        project_tempo_bpm=prj["tempo_bpm"],
        project_tempo_changes=_join_pairs(prj["tempo_changes"], "position_beats", "bpm"),
        project_time_signatures=_join_pairs(prj["time_signatures"], "position_beats", "value"),
        project_key=prj["key"], project_sample_rate=prj["sample_rate"],
        project_bit_depth=prj["bit_depth"], project_length_seconds=prj["length_seconds"],
        project_length_bars=prj["length_bars"],
        project_markers=_join_pairs(prj["markers"], "position_beats", "name"),
        project_file_size_bytes=src["file_size_bytes"], project_modified_at=src["modified_at"],
        project_folder_size_bytes=prj["folder"]["total_size_bytes"],
        project_backup_count=prj["folder"]["backup_count"],
        project_unavailable_fields=prj["unavailable_fields"])
    tc = summ["track_counts"]
    mu = summ["most_used_plugin"]
    row("summary", "summary", None, None,
        summary_tracks_audio=tc.get("audio"), summary_tracks_midi=tc.get("midi"),
        summary_tracks_instrument=tc.get("instrument"), summary_tracks_return=tc.get("return"),
        summary_tracks_group=tc.get("group"), summary_unique_plugins=summ["unique_plugins"],
        summary_plugin_instances=summ["plugin_instances"],
        summary_missing_plugins=summ["missing_plugins"],
        summary_stock_devices=summ["stock_devices"],
        summary_heuristic_results=summ["heuristic_results"],
        summary_media_files=summ["media_files"], summary_missing_media=summ["missing_media"],
        summary_media_outside_folder=summ["media_outside_folder"],
        summary_opens_on_windows=summ["opens_on"]["windows"],
        summary_opens_on_mac=summ["opens_on"]["mac"],
        summary_send_ready_score=summ["send_ready"]["score"],
        summary_send_ready_reasons=summ["send_ready"]["reasons"],
        summary_most_used_plugin=(f"{mu['name']} ({mu['instances']})" if mu else None))
    for i, w in enumerate(report["warnings"], start=1):
        row("warning", f"w{i}", None, None, warning_code=w["code"],
            warning_severity=w["severity"], warning_message=w["message"],
            warning_related_ids=w["related_ids"])
    plugin_names_by_track: dict[str, list[str]] = {}
    for p in report["plugins"]:
        if p["track_id"]:
            plugin_names_by_track.setdefault(p["track_id"], []).append(p["name"] or "")
    for t in report["tracks"]:
        midi = t["midi"] or {}
        rng = f"{midi.get('lowest')}-{midi.get('highest')}" if midi.get("lowest") else None
        row("track", t["id"], t["parent_id"], t["name"], track_type=t["type"],
            track_color=t["color"], track_muted=t["muted"], track_solo=t["solo"],
            track_armed=t["armed"], track_frozen=t["frozen"], track_volume_db=t["volume_db"],
            track_pan=t["pan"], track_output=t["output"],
            track_sends=[f"{s.get('target_id')}@{s.get('level_db')}" for s in t["sends"]],
            track_sidechain_sources=t["sidechain_sources"], track_clip_count=t["clip_count"],
            track_midi_note_count=midi.get("note_count"), track_midi_range=rng,
            track_automated_parameters=t["automated_parameters"],
            track_plugin_names=plugin_names_by_track.get(t["id"], []))
    for p in report["plugins"]:
        res, kb, links = p["resolution"], p["kb"] or {}, p["links"]
        inst = res["installed"] or {}
        row("plugin", p["id"], p["track_id"], p["name"],
            plugin_track_name=track_name.get(p["track_id"]), plugin_slot=p["slot_index"],
            plugin_nested_in=p["nested_in"], plugin_role=p["role"], plugin_format=p["format"],
            plugin_vendor=p["vendor"], plugin_identity=_identity_text(p["identity"]),
            plugin_bypassed=p["bypassed"], plugin_version_in_project=p["version_in_project"],
            plugin_preset_name=p["preset_name"], plugin_automated=p["automated"],
            plugin_state_size_bytes=p["state_size_bytes"], plugin_confidence=p["confidence"],
            plugin_resolution_state=res["state"], plugin_installed_version=inst.get("version"),
            plugin_installed_path=inst.get("path"), plugin_installed_arch=inst.get("arch"),
            plugin_other_formats_installed=res["other_formats_installed"],
            plugin_category=kb.get("category"), plugin_licensing=kb.get("licensing"),
            plugin_price_model=kb.get("price_model"), plugin_platforms=kb.get("platforms"),
            plugin_formats_available=kb.get("formats_available"),
            plugin_apple_silicon_native=kb.get("apple_silicon_native"),
            plugin_status=kb.get("status"), plugin_free_alternatives=kb.get("free_alternatives"),
            plugin_homepage=links["homepage"]["url"],
            plugin_homepage_source=links["homepage"]["source"],
            plugin_manual_url=links["manual"]["url"], plugin_support_url=links["support"]["url"],
            plugin_flags=p["flags"], plugin_kb_last_verified=kb.get("last_verified"),
            plugin_resolution_matched_by=res["matched_by"],
            plugin_resolution_confidence=res["confidence"], plugin_kb_id=kb.get("kb_id"),
            plugin_kb_matched_by=kb.get("matched_by"), plugin_kb_confidence=kb.get("confidence"),
            plugin_kb_verified=kb.get("verified"))
    for s in report["plugin_summary"]:
        home = next((p["links"]["homepage"]["url"] for p in report["plugins"]
                     if plugin_group_key(p) == s["key"]), None)
        row("plugin_summary", s["key"], None, s["name"], ps_vendor=s["vendor"],
            ps_instances=s["instances"], ps_bypassed_instances=s["bypassed_instances"],
            ps_tracks=[track_name.get(t) or t for t in s["track_ids"]],
            ps_resolution_state=s["resolution_state"], ps_homepage=home)
    for m in report["media"]:
        a = m["audio"] or {}
        hint = m["source_hint"]
        row("media", m["id"], None, Path(m["path"].replace("\\", "/")).name,
            media_path=m["path"], media_type=m["type"], media_referenced_by=m["referenced_by"],
            media_exists=m["exists"], media_inside_project_folder=m["inside_project_folder"],
            media_size_bytes=m["size_bytes"], media_format=a.get("format"),
            media_sample_rate=a.get("sample_rate"), media_bit_depth=a.get("bit_depth"),
            media_channels=a.get("channels"), media_duration_seconds=a.get("duration_seconds"),
            media_sample_rate_mismatch=m["sample_rate_mismatch"],
            media_duplicate_of=m["duplicate_of"],
            media_source_hint=f"{hint['value']} ({hint['confidence']})" if hint else None)
    for i, u in enumerate(report["unused_media"], start=1):
        row("unused_media", f"u{i}", None, Path(u["path"].replace("\\", "/")).name,
            unused_path=u["path"], unused_size_bytes=u["size_bytes"])
    for i, sc in enumerate(report["special_content"], start=1):
        row("special_content", f"s{i}", None, sc["name"], special_type=sc["type"],
            special_track_name=track_name.get(sc["track_id"]), special_plugin_id=sc["plugin_id"],
            special_path=sc["path"], special_confidence=sc["confidence"])
    return rows


def _write_csv(columns: list[str], rows: list[dict[str, Any]], delimiter: str = ",") -> str:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, delimiter=delimiter, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(columns)
    for r in rows:
        w.writerow([csv_safe(r.get(c)) for c in columns])
    return buf.getvalue()


def report_to_csv(report: dict[str, Any], *, redact_paths: bool = False,
                  delimiter: str = ",") -> str:
    """Full report CSV text (without BOM; :func:`write_csv` adds it)."""
    return _write_csv(CSV_COLUMNS, csv_rows(_prepare(report, redact_paths)), delimiter)


def _write_text_bom(path: str | Path, text: str) -> Path:
    p = Path(path)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        f.write(text)
    return p


def write_csv(report: dict[str, Any], path: str | Path, *, redact_paths: bool = False,
              delimiter: str = ",") -> Path:
    return _write_text_bom(path, report_to_csv(report, redact_paths=redact_paths,
                                               delimiter=delimiter))


# ---- quick exports (10.4) ---------------------------------------------------------


def plugin_list_rows(report: dict[str, Any], missing_only: bool = False) -> list[dict[str, Any]]:
    track_name = {t["id"]: t["name"] for t in report["tracks"]}
    by_key: dict[str, list[dict[str, Any]]] = {}
    for p in report["plugins"]:
        by_key.setdefault(plugin_group_key(p), []).append(p)
    rows = []
    for s in report["plugin_summary"]:
        members = by_key.get(s["key"], [])
        if missing_only and s["resolution_state"] != "not_installed":
            continue
        first = members[0] if members else {}
        kb = first.get("kb") or {}
        rows.append({
            "name": s["name"], "vendor": s["vendor"],
            "format": sorted({m["format"] for m in members}),
            "instances": s["instances"],
            "tracks": [track_name.get(t) or t for t in s["track_ids"]],
            "resolution_state": s["resolution_state"],
            "homepage": (first.get("links") or {}).get("homepage", {}).get("url"),
            "licensing": kb.get("licensing"), "price_model": kb.get("price_model"),
        })
    return rows


def plugin_list_csv(report: dict[str, Any], *, missing_only: bool = False,
                    redact_paths: bool = False, delimiter: str = ",") -> str:
    return _write_csv(PLUGIN_LIST_COLUMNS,
                      plugin_list_rows(_prepare(report, redact_paths), missing_only), delimiter)


def write_plugin_list(report: dict[str, Any], path: str | Path, *, missing_only: bool = False,
                      redact_paths: bool = False, delimiter: str = ",") -> Path:
    return _write_text_bom(path, plugin_list_csv(
        report, missing_only=missing_only, redact_paths=redact_paths, delimiter=delimiter))


def default_filename(report: dict[str, Any], ext: str) -> str:
    """``<ProjectName>_rackcheck_<YYYY-MM-DD_HHMM>.<ext>`` (SPEC-02 10.1)."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", report["project"]["name"] or "project").strip(" .")
    stamp = report["generated_at"][:16].replace("T", "_").replace(":", "")
    return f"{name or 'project'}_rackcheck_{stamp}.{ext.lstrip('.')}"
