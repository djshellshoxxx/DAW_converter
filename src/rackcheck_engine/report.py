"""Full report builder (SPEC-02 sections 9 and 10.2, SPEC-01 section 8).

``build_report`` turns a reader's :class:`ScanResult` plus the installed-plugin inventory
and the Knowledge Base into the JSON-serializable report the CLI prints and the GUI
renders. It never touches the network and never guesses: values the reader does not
provide stay ``null`` and the field is listed in ``unavailable_fields`` (SPEC-02 10.1).
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import os
import platform
import re
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import ENGINE_VERSION, SCHEMA_VERSION
from .detect import DAW_NAMES, ProjectFormat
from .inventory.scan import InstalledPlugin
from .kb import KnowledgeBase
from .links import resolve_links
from .model import Confidence, PluginFormat, PluginRef, ScanResult
from .resolve import (
    INSTALLED_OTHER,
    INSTALLED_SAME,
    NOT_CHECKED,
    NOT_INSTALLED,
    STOCK,
    UNKNOWN,
    Resolution,
    Resolver,
    normalize_name,
    vst2_id_to_int,
)

AUDIO_EXTS = {".wav", ".wave", ".aif", ".aiff", ".aifc", ".flac", ".mp3", ".ogg", ".m4a",
              ".aac", ".wma", ".opus", ".caf", ".w64", ".rf64", ".wv"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".mpg", ".mpeg", ".wmv", ".webm"}
_BACKUP_DIR_NAMES = {"backup", "backups", "autosave", "autosaves", "history"}
_MAX_FOLDER_FILES = 200_000
_HASH_LIMIT_BYTES = 512 * 1024 * 1024

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
_STATE_BADNESS = [NOT_INSTALLED, INSTALLED_OTHER, UNKNOWN, NOT_CHECKED, INSTALLED_SAME, STOCK]

_PROJECT_NOT_READ = ["title", "artist", "genre", "comments", "tempo_changes_after_start",
                     "time_signature_changes_after_start", "bit_depth", "length_bars", "markers",
                     "loop", "alternatives"]
_OTHER_NOT_READ = [
    "tracks.parent_id", "tracks.color", "tracks.muted", "tracks.solo", "tracks.armed",
    "tracks.frozen", "tracks.volume_db", "tracks.pan", "tracks.output", "tracks.sends",
    "tracks.sidechain_sources", "tracks.clip_count", "tracks.midi",
    "tracks.automated_parameters", "plugins.preset_name", "plugins.automated",
    "plugins.state_size_bytes", "media.referenced_by",
]


@dataclass
class ReportOptions:
    redact_paths: bool = False  # applied on export via redact_report(), recorded here
    hash_media: bool = True
    scan_folder: bool = True


# ---- helpers ----------------------------------------------------------------------


def _v(x: Any) -> Any:
    """Enum -> its value; anything else unchanged."""
    return getattr(x, "value", x)


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


def _version_tuple(v: str | None) -> tuple[int, ...] | None:
    if not v:
        return None
    nums = re.findall(r"\d+", v)[:4]
    if not nums:
        return None
    t = tuple(int(n) for n in nums)
    return t + (0,) * (4 - len(t))


def plugin_group_key(plugin: dict[str, Any]) -> str:
    """Stable key grouping instances of the same plugin (across formats when the KB knows)."""
    kb = plugin.get("kb")
    if kb and kb.get("kb_id"):
        return str(kb["kb_id"])
    name = normalize_name(plugin.get("name")) or "unnamed"
    if plugin.get("format") in ("stock", "js"):
        return f"stock:{name}"
    vendor = normalize_name(plugin.get("vendor"))
    return f"unmatched:{name}|{vendor}" if vendor else f"unmatched:{name}"


def _is_loose_folder(folder: Path) -> bool:
    """Folders where 'everything in it' says nothing about the project (Desktop, home...)."""
    try:
        home = Path.home()
    except RuntimeError:
        return False
    try:
        if folder == home or folder.parent == folder:
            return True
        return folder.parent == home and folder.name.lower() in {
            "desktop", "documents", "downloads", "music"}
    except OSError:
        return False


def _norm_path(p: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


# ---- audio headers ----------------------------------------------------------------


def _wav_info(f) -> dict[str, Any] | None:
    hdr = f.read(12)
    if len(hdr) < 12 or hdr[:4] not in (b"RIFF", b"RF64") or hdr[8:12] != b"WAVE":
        return None
    rate = bits = chans = byte_rate = data_size = None
    for _ in range(64):
        ch = f.read(8)
        if len(ch) < 8:
            break
        cid, size = ch[:4], struct.unpack("<I", ch[4:])[0]
        if cid == b"fmt " and size >= 16:
            body = f.read(16)
            _tag, chans, rate, byte_rate, _align, bits = struct.unpack("<HHIIHH", body)
            f.seek(size - 16 + (size & 1), 1)
        elif cid == b"data":
            data_size = size
            break
        else:
            f.seek(size + (size & 1), 1)
    if not rate:
        return None
    dur = None
    if data_size is not None and byte_rate and data_size != 0xFFFFFFFF:
        dur = round(data_size / byte_rate, 3)
    return {"format": "wav", "sample_rate": rate, "bit_depth": bits, "channels": chans,
            "duration_seconds": dur}


def _flac_info(f) -> dict[str, Any] | None:
    if f.read(4) != b"fLaC":
        return None
    bh = f.read(4)
    if len(bh) < 4 or (bh[0] & 0x7F) != 0:
        return None
    data = f.read(34)
    if len(data) < 18:
        return None
    packed = int.from_bytes(data[10:18], "big")
    rate = packed >> 44
    chans = ((packed >> 41) & 0x7) + 1
    bits = ((packed >> 36) & 0x1F) + 1
    total = packed & 0xFFFFFFFFF
    dur = round(total / rate, 3) if rate and total else None
    return {"format": "flac", "sample_rate": rate or None, "bit_depth": bits,
            "channels": chans, "duration_seconds": dur}


def _aiff_info(f) -> dict[str, Any] | None:
    hdr = f.read(12)
    if len(hdr) < 12 or hdr[:4] != b"FORM" or hdr[8:12] not in (b"AIFF", b"AIFC"):
        return None
    for _ in range(64):
        ch = f.read(8)
        if len(ch) < 8:
            break
        cid, size = ch[:4], struct.unpack(">I", ch[4:])[0]
        if cid == b"COMM" and size >= 18:
            body = f.read(18)
            chans, frames, bits = struct.unpack(">HIH", body[:8])
            exp = struct.unpack(">H", body[8:10])[0] & 0x7FFF
            mant = int.from_bytes(body[10:18], "big")
            rate = int(round(mant * 2.0 ** (exp - 16383 - 63))) if exp else 0
            dur = round(frames / rate, 3) if rate else None
            return {"format": "aiff", "sample_rate": rate or None, "bit_depth": bits,
                    "channels": chans, "duration_seconds": dur}
        f.seek(size + (size & 1), 1)
    return None


def read_audio_header(path: Path) -> dict[str, Any] | None:
    """Header info read from the audio file itself. Only header bytes are read."""
    ext = path.suffix.lower()
    parsers = {".wav": _wav_info, ".wave": _wav_info, ".flac": _flac_info,
               ".aif": _aiff_info, ".aiff": _aiff_info, ".aifc": _aiff_info}
    parser = parsers.get(ext)
    if parser is None:
        return None
    try:
        with open(path, "rb") as f:
            return parser(f)
    except (OSError, struct.error, ValueError, OverflowError):
        return None


def _sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _source_hint(path: str, project_folder: Path | None) -> dict[str, Any] | None:
    p = path.replace("\\", "/").lower()
    for needle, value in (("splice", "splice"), ("loopcloud", "loopcloud"),
                          ("/downloads/", "downloads"), ("/desktop/", "desktop")):
        if needle in p:
            return {"value": value, "confidence": "heuristic"}
    if p.startswith("/volumes/") or re.match(r"^[d-z]:/", p):
        return {"value": "external_volume", "confidence": "heuristic"}
    return None


# ---- filesystem facts -------------------------------------------------------------


def _folder_facts(folder: Path | None, do_scan: bool
                  ) -> tuple[dict[str, Any], list[tuple[Path, int]] | None]:
    facts: dict[str, Any] = {"path": str(folder) if folder else None, "total_size_bytes": None,
                             "file_count": None, "backup_count": None, "newest_backup_at": None}
    if folder is None or not do_scan or _is_loose_folder(folder) or not folder.is_dir():
        return facts, None
    files: list[tuple[Path, int]] = []
    total = 0
    backups = 0
    newest = None
    truncated = False
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = [d for d in dirnames if not (Path(dirpath) / d).is_symlink()]
        in_backup_dir = any(
            part.lower() in _BACKUP_DIR_NAMES
            for part in Path(dirpath).relative_to(folder).parts)
        for name in filenames:
            fp = Path(dirpath) / name
            try:
                if fp.is_symlink():
                    continue
                st = fp.stat()
            except OSError:
                continue
            files.append((fp, st.st_size))
            total += st.st_size
            low = name.lower()
            if in_backup_dir or low.endswith((".rpp-bak", ".bak")) or "autosave" in low:
                backups += 1
                newest = st.st_mtime if newest is None else max(newest, st.st_mtime)
            if len(files) > _MAX_FOLDER_FILES:
                truncated = True
                break
        if truncated:
            break
    if truncated:
        return facts, None
    facts.update(total_size_bytes=total, file_count=len(files), backup_count=backups,
                 newest_backup_at=_iso(newest))
    return facts, files


# ---- plugins ----------------------------------------------------------------------


def _identity_block(ref: PluginRef) -> dict[str, Any]:
    i = ref.identity
    au = None
    if i.au_type or i.au_subtype or i.au_manufacturer:
        au = {"type": i.au_type, "subtype": i.au_subtype, "manufacturer": i.au_manufacturer}
    ascii_id = None
    n = vst2_id_to_int(i.vst2_unique_id)
    if n:
        try:
            ascii_id = n.to_bytes(4, "big").decode("ascii")
            if not ascii_id.isprintable():
                ascii_id = None
        except (OverflowError, UnicodeDecodeError):
            ascii_id = None
    return {"vst3_cid": i.vst3_cid, "vst2_unique_id": i.vst2_unique_id, "vst2_ascii": ascii_id,
            "au": au, "clap_id": i.clap_id, "aax": i.aax_ids, "file_hint": i.file_hint}


def _arch_string(inst: InstalledPlugin) -> str | None:
    return "/".join(inst.architectures) if inst.architectures else None


def _kb_block(res: Resolution) -> dict[str, Any] | None:
    p = res.kb_plugin
    if p is None:
        return None
    return {
        "kb_id": p.id, "category": p.category, "licensing": p.licensing or [],
        "price_model": p.price_model, "platforms": p.platforms or [],
        "formats_available": p.formats or [],
        # The KB dataclass defaults this to False, which is indistinguishable from
        # "unknown", so only a verified record may state it.
        "apple_silicon_native": p.apple_silicon_native if p.verified else None,
        "status": p.status, "successor_id": p.successor_id,
        "free_alternatives": p.free_alternatives or [], "last_verified": p.last_verified,
        "matched_by": res.kb_matched_by,
        "confidence": _v(res.kb_confidence) if res.kb_confidence else None,
        "verified": bool(p.verified), "provenance": p.provenance,
    }


def _plugin_flags(ref: PluginRef, res: Resolution) -> list[str]:
    flags: list[str] = []
    p = res.kb_plugin
    verified = bool(p and p.verified)
    if p is not None and verified:
        fmts = [f.lower() for f in (p.formats or [])]
        if fmts and set(fmts) == {"vst2"}:
            flags.append("vst2_only")
        if any(x.lower() == "ilok" for x in (p.licensing or [])):
            flags.append("ilok")
        plats = {x.lower() for x in (p.platforms or [])}
        if plats == {"mac"}:
            flags.append("mac_only")
        elif plats == {"win"}:
            flags.append("win_only")
        if (p.status or "").lower() == "discontinued":
            flags.append("discontinued")
    inst = res.installed
    if inst is not None and inst.architectures:
        archs = set(inst.architectures)
        if "x86_64" in archs and not archs & {"arm64", "arm64e"} and inst.path.startswith("/"):
            flags.append("intel_only")
        if "i386" in archs and "x86_64" not in archs:
            flags.append("32_bit")
    if res.state == STOCK:
        flags.append("stock")
    if ref.confidence == Confidence.HEURISTIC or res.confidence == Confidence.HEURISTIC:
        flags.append("heuristic")
    return flags


def _build_plugin(ref: PluginRef, res: Resolution, tracks_by_id: dict[str, str]) -> dict[str, Any]:
    inst = res.installed
    is_stock = res.state == STOCK
    links = resolve_links(
        name=ref.name, vendor_name=ref.vendor, kb_plugin=res.kb_plugin, kb_vendor=res.vendor,
        installed=inst, is_stock=is_stock)
    return {
        "id": ref.id, "track_id": ref.track_id, "slot_index": ref.slot_index,
        "nested_in": ref.nested_in, "role": _v(ref.role), "format": _v(ref.format),
        "name": ref.name, "vendor": ref.vendor or (inst.vendor if inst else None),
        "identity": _identity_block(ref), "bypassed": ref.bypassed,
        "version_in_project": ref.version_in_project, "preset_name": None,
        "automated": None, "state_size_bytes": None, "confidence": _v(ref.confidence),
        "resolution": {
            "state": res.state, "matched_by": res.matched_by,
            "confidence": _v(res.confidence) if res.confidence else None,
            "installed": ({"version": inst.version, "path": inst.path,
                           "arch": _arch_string(inst)} if inst else None),
            "other_formats_installed": res.other_formats_installed,
        },
        "kb": _kb_block(res), "links": links, "flags": _plugin_flags(ref, res),
    }


# ---- media ------------------------------------------------------------------------


def _build_media(scan: ScanResult, folder: Path | None, project_sr: int | None,
                 folder_files: list[tuple[Path, int]] | None, opts: ReportOptions
                 ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    media: list[dict[str, Any]] = []
    by_hash: dict[str, str] = {}
    referenced: set[str] = set()
    folder_norm = _norm_path(folder) if folder else None
    for i, m in enumerate(scan.media, start=1):
        raw = m.path
        p = Path(raw)
        if not p.is_absolute() and folder is not None:
            p = folder / p
        referenced.add(_norm_path(p))
        try:
            exists = m.exists if m.exists is not None else p.is_file()
        except OSError:
            exists = None
        size = m.size_bytes
        if size is None and exists:
            try:
                size = p.stat().st_size
            except OSError:
                size = None
        inside = m.inside_project_folder
        if inside is None and folder_norm is not None:
            n = _norm_path(p)
            inside = n == folder_norm or n.startswith(folder_norm + os.sep)
        ext = p.suffix.lower()
        mtype = "audio" if ext in AUDIO_EXTS else "video" if ext in VIDEO_EXTS else "other"
        audio = None
        sha = None
        if exists:
            if mtype == "audio":
                audio = read_audio_header(p)
                if audio is None and ext:
                    audio = {"format": ext.lstrip("."), "sample_rate": None, "bit_depth": None,
                             "channels": None, "duration_seconds": None}
            if opts.hash_media and (size is None or size <= _HASH_LIMIT_BYTES):
                sha = _sha256(p)
        dup = None
        if sha:
            if sha in by_hash:
                dup = by_hash[sha]
            else:
                by_hash[sha] = f"m{i}"
        mismatch = None
        if audio and audio.get("sample_rate") and project_sr:
            mismatch = audio["sample_rate"] != project_sr
        media.append({
            "id": f"m{i}", "path": raw, "type": mtype, "referenced_by": [],
            "exists": exists, "inside_project_folder": inside, "size_bytes": size,
            "sha256": sha, "audio": audio, "sample_rate_mismatch": mismatch,
            "duplicate_of": dup, "source_hint": _source_hint(raw, folder),
        })
    unused: list[dict[str, Any]] = []
    if folder_files is not None:
        for fp, size in folder_files:
            if fp.suffix.lower() in AUDIO_EXTS and _norm_path(fp) not in referenced:
                unused.append({"path": str(fp), "size_bytes": size})
        unused.sort(key=lambda u: u["path"])
    return media, unused


# ---- warnings and summary ---------------------------------------------------------


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _fmt_size(n: int) -> str:
    size = float(n)
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} bytes" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} bytes"


def _plugin_warnings(plugins: list[dict[str, Any]], daw_name: str | None,
                     ) -> list[dict[str, Any]]:
    """Per unique plugin (grouped instances) warnings."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for p in plugins:
        groups.setdefault(plugin_group_key(p), []).append(p)
    out: list[dict[str, Any]] = []

    def add(code: str, sev: str, msg: str, ids: list[str]) -> None:
        out.append({"code": code, "severity": sev, "message": msg, "related_ids": ids})

    stock_ids: list[str] = []
    for members in groups.values():
        first = members[0]
        name = first["name"] or "An unnamed plugin"
        ids = [m["id"] for m in members]
        state = first["resolution"]["state"]
        for m in members:  # worst state wins for the group
            if _STATE_BADNESS.index(m["resolution"]["state"]) < _STATE_BADNESS.index(state):
                state = m["resolution"]["state"]
        if state == STOCK:
            stock_ids.extend(ids)
            continue
        flags = {f for m in members for f in m["flags"]}
        fmts = "/".join(sorted({m["format"].upper() for m in members}))
        if state == NOT_INSTALLED:
            add("PLUGIN_MISSING", "error", f"{name} is not installed on this computer", ids)
        elif state == INSTALLED_OTHER:
            other = first["resolution"]["other_formats_installed"]
            add("PLUGIN_OTHER_FORMAT", "warning",
                f"{name} is installed as {'/'.join(o.upper() for o in other)}, "
                f"but this project uses {fmts}", ids)
        if first["kb"] is None and first["resolution"]["installed"] is None:
            add("PLUGIN_UNKNOWN", "warning",
                f"We couldn't identify {name}; treat its details as unknown", ids)
        for m in members:
            inst_v = (m["resolution"]["installed"] or {}).get("version")
            a, b = _version_tuple(inst_v), _version_tuple(m["version_in_project"])
            if a and b and a < b:
                add("PLUGIN_VERSION_OLDER", "warning",
                    f"{name}: installed version {inst_v} is older than the version "
                    f"saved in the project ({m['version_in_project']})", [m["id"]])
        simple = (
            ("vst2_only", "PLUGIN_VST2_ONLY", "info",
             f"{name} is only available as VST2, a format some DAWs are dropping"),
            ("mac_only", "PLUGIN_MAC_ONLY", "warning",
             f"{name} only runs on macOS, so this project can't fully open on Windows"),
            ("win_only", "PLUGIN_WIN_ONLY", "warning",
             f"{name} only runs on Windows, so this project can't fully open on a Mac"),
            ("intel_only", "PLUGIN_INTEL_ONLY", "warning",
             f"{name} is Intel-only and needs Rosetta on Apple Silicon Macs"),
            ("32_bit", "PLUGIN_32BIT", "warning",
             f"{name} is a 32-bit plugin and won't load in most modern DAWs"),
            ("discontinued", "PLUGIN_DISCONTINUED", "info",
             f"{name} has been discontinued"),
            ("ilok", "PLUGIN_DRM_ILOK", "info",
             f"{name} uses iLok; your collaborator needs a license for it"),
        )
        for flag, code, sev, msg in simple:
            if flag in flags:
                add(code, sev, msg, ids)
    if stock_ids:
        who = daw_name or "the original DAW"
        add("STOCK_DEVICE_DAW", "info",
            f"{_plural(len(stock_ids), 'built-in device', 'built-in devices')} from {who}; "
            f"your collaborator needs the same DAW", stock_ids)
    return out


def _media_warnings(media: list[dict[str, Any]], unused: list[dict[str, Any]],
                    have_folder_scan: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    missing = [m["id"] for m in media if m["exists"] is False]
    if missing:
        out.append({"code": "MEDIA_MISSING", "severity": "error",
                    "message": f"{_plural(len(missing), 'referenced file was',
                                          'referenced files were')} not found",
                    "related_ids": missing})
    outside = [m["id"] for m in media if m["inside_project_folder"] is False]
    if outside:
        out.append({"code": "MEDIA_OUTSIDE_FOLDER", "severity": "warning",
                    "message": f"{_plural(len(outside), 'audio file is', 'audio files are')} "
                               "outside the project folder and won't be included if you send "
                               "the folder", "related_ids": outside})
    mism = [m["id"] for m in media if m["sample_rate_mismatch"]]
    if mism:
        out.append({"code": "MEDIA_SR_MISMATCH", "severity": "info",
                    "message": f"{_plural(len(mism), 'file has', 'files have')} a sample rate "
                               "different from the project", "related_ids": mism})
    if unused:
        total = sum(u["size_bytes"] for u in unused)
        out.append({"code": "MEDIA_UNUSED", "severity": "info",
                    "message": f"{_plural(len(unused), 'audio file', 'audio files')} in the "
                               f"project folder ({_fmt_size(total)}) aren't used by the project",
                    "related_ids": []})
    return out


_REASON_TEXT = {
    "PLUGIN_MISSING": ("plugin missing", "plugins missing"),
    "PLUGIN_OTHER_FORMAT": ("plugin installed in a different format",
                            "plugins installed in a different format"),
    "PLUGIN_UNKNOWN": ("unidentified plugin", "unidentified plugins"),
    "PLUGIN_VERSION_OLDER": ("plugin older than the project's", "plugins older than the project's"),
    "PLUGIN_MAC_ONLY": ("Mac-only plugin", "Mac-only plugins"),
    "PLUGIN_WIN_ONLY": ("Windows-only plugin", "Windows-only plugins"),
    "PLUGIN_INTEL_ONLY": ("Intel-only plugin", "Intel-only plugins"),
    "PLUGIN_32BIT": ("32-bit plugin", "32-bit plugins"),
    "MEDIA_MISSING": ("missing audio file", "missing audio files"),
    "MEDIA_OUTSIDE_FOLDER": ("audio file outside the project folder",
                             "audio files outside the project folder"),
}


def _send_ready(warnings: list[dict[str, Any]], inventory_available: bool
                ) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for w in warnings:
        if w["severity"] == "info" or w["code"] not in _REASON_TEXT:
            continue
        counts[w["code"]] = counts.get(w["code"], 0) + (
            len(w["related_ids"]) if w["code"].startswith("MEDIA") else 1)
    reasons = [f"{n} {_REASON_TEXT[c][0 if n == 1 else 1]}" for c, n in counts.items()]
    if not inventory_available:
        reasons.append("installed plugins were not checked")
    has_error = any(w["severity"] == "error" for w in warnings)
    has_warning = any(w["severity"] == "warning" for w in warnings)
    if has_error:
        score = "red"
    elif has_warning or not inventory_available:
        score = "yellow"
    else:
        score = "green"
    return {"score": score, "reasons": reasons}


def _opens_on(plugins: list[dict[str, Any]], fmt: str | None) -> dict[str, bool]:
    windows = mac = True
    if fmt == ProjectFormat.LOGIC_BUNDLE.value:
        windows = False
    for p in plugins:
        if p["format"] == "au":
            windows = False
        flags = p["flags"]
        if "mac_only" in flags:
            windows = False
        if "win_only" in flags:
            mac = False
    return {"windows": windows, "mac": mac}


# ---- main entry -------------------------------------------------------------------


def build_report(
    scan: ScanResult,
    detection: dict[str, Any] | None = None,
    *,
    inventory: list[InstalledPlugin] | None = None,
    inventory_scanned_at: str | None = None,
    kb: KnowledgeBase | None = None,
    options: ReportOptions | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the full report dict (SPEC-02 10.2). ``inventory=None`` means "not checked"."""
    opts = options or ReportOptions()
    now = now or datetime.now().astimezone()
    src_path = Path(scan.source.path)
    det = detection or {}
    fmt = det.get("format") or scan.source.format
    daw_name = scan.source.daw_name
    if not daw_name:
        try:
            daw_name = DAW_NAMES.get(ProjectFormat(fmt))
        except ValueError:
            daw_name = None

    # source (filesystem facts, 9.6)
    st = None
    with contextlib.suppress(OSError):
        st = src_path.stat()
    is_file = st is not None and src_path.is_file()
    created = None
    if st is not None:
        created = getattr(st, "st_birthtime", None)
        if created is None and os.name == "nt":
            created = st.st_ctime
    source = {
        "path": str(src_path), "file_size_bytes": st.st_size if is_file else None,
        "created_at": _iso(created), "modified_at": _iso(st.st_mtime) if st else None,
        "format": fmt, "detection_confidence": _v(det.get("confidence")),
        "detection_reason": det.get("reason"), "daw_name": daw_name,
        "daw_version": scan.source.daw_version, "reader_version": scan.source.reader_version,
    }

    folder = (src_path if src_path.is_dir() else src_path.parent) if st is not None else None
    folder_facts, folder_files = _folder_facts(folder, opts.scan_folder)

    pj = scan.project
    unavailable = list(_PROJECT_NOT_READ)
    unavailable += [k for k in ("tempo_bpm", "key", "sample_rate", "length_seconds")
                    if getattr(pj, k) is None]
    unavailable += _OTHER_NOT_READ
    project = {
        "name": src_path.stem or src_path.name, "title": None, "artist": None, "genre": None,
        "comments": None, "tempo_bpm": pj.tempo_bpm,
        "tempo_changes": ([{"position_beats": 0, "bpm": pj.tempo_bpm}]
                          if pj.tempo_bpm is not None else []),
        "time_signatures": ([{"position_beats": 0, "value": pj.time_signature}]
                            if pj.time_signature else []), "key": pj.key,
        "sample_rate": pj.sample_rate, "bit_depth": None,
        "length_seconds": pj.length_seconds, "length_bars": None, "markers": [],
        "loop": {"start_beats": None, "end_beats": None}, "alternatives": [],
        "folder": folder_facts, "unavailable_fields": unavailable,
    }

    tracks = [{
        "id": t.id, "name": t.name, "type": _v(t.type), "parent_id": None, "color": None,
        "muted": None, "solo": None, "armed": None, "frozen": None, "volume_db": None,
        "pan": None, "output": None, "sends": [], "sidechain_sources": [], "clip_count": None,
        "midi": None, "automated_parameters": [], "device_ids": list(t.devices),
    } for t in scan.tracks]
    track_names = {t.id: t.name for t in scan.tracks}

    resolver = Resolver(inventory, kb)
    resolutions = [resolver.resolve(ref) for ref in scan.plugins]
    plugins = [_build_plugin(ref, res, track_names)
               for ref, res in zip(scan.plugins, resolutions, strict=True)]

    # plugin_summary (unique plugins)
    groups: dict[str, list[dict[str, Any]]] = {}
    for p in plugins:
        groups.setdefault(plugin_group_key(p), []).append(p)
    plugin_summary = []
    for key, members in groups.items():
        first = members[0]
        state = min((m["resolution"]["state"] for m in members),
                    key=_STATE_BADNESS.index)
        tids = []
        for m in members:
            if m["track_id"] and m["track_id"] not in tids:
                tids.append(m["track_id"])
        plugin_summary.append({
            "key": key, "name": first["name"], "vendor": first["vendor"],
            "instances": len(members), "track_ids": tids,
            "bypassed_instances": sum(1 for m in members if m["bypassed"]),
            "resolution_state": state,
        })
    plugin_summary.sort(key=lambda s: (-s["instances"], s["name"] or "", s["key"]))

    media, unused = _build_media(scan, folder, pj.sample_rate, folder_files, opts)

    special = []
    for ref in scan.plugins:
        hint = ref.identity.file_hint
        if ref.format == PluginFormat.STOCK and hint and hint.lower().endswith(".amxd"):
            special.append({"type": "max_for_live", "name": ref.name, "track_id": ref.track_id,
                            "plugin_id": ref.id, "path": hint, "confidence": _v(ref.confidence)})

    # warnings
    warnings = _plugin_warnings(plugins, daw_name)
    warnings += _media_warnings(media, unused, folder_files is not None)
    if scan.external_hardware_tracks:
        track_ids = list(dict.fromkeys(scan.external_hardware_tracks))
        warnings.append({
            "code": "EXTERNAL_HARDWARE", "severity": "warning",
            "message": "This project uses external audio hardware; collaborators need access "
                       "to the same hardware",
            "related_ids": track_ids,
        })
    if any("heuristic" in p["flags"] for p in plugins):
        n = sum(1 for p in plugins if "heuristic" in p["flags"])
        warnings.append({
            "code": "HEURISTIC_RESULTS", "severity": "info",
            "message": f"{_plural(n, 'plugin result comes', 'plugin results come')} from "
                       "string scanning or weak matching and may be wrong",
            "related_ids": [p["id"] for p in plugins if "heuristic" in p["flags"]]})
    if inventory is None:
        warnings.append({"code": "INVENTORY_UNAVAILABLE", "severity": "info",
                         "message": "Installed plugins were not checked, so install status "
                                    "is unknown", "related_ids": []})
    for text in scan.warnings:
        warnings.append({"code": "READER_NOTE", "severity": "info", "message": str(text),
                         "related_ids": []})
    warnings.sort(key=lambda w: _SEVERITY_ORDER[w["severity"]])  # stable within severity

    counts: dict[str, int] = {k: 0 for k in ("audio", "midi", "instrument", "return", "group",
                                             "master")}
    for t in tracks:
        counts[t["type"]] = counts.get(t["type"], 0) + 1
    non_stock = [p for p in plugins if p["resolution"]["state"] != STOCK]
    unique_non_stock = [s for s in plugin_summary if s["resolution_state"] != STOCK]
    most_used = None
    if unique_non_stock:
        top = unique_non_stock[0]
        most_used = {"key": top["key"], "name": top["name"], "instances": top["instances"]}
    summary = {
        "track_counts": counts,
        "unique_plugins": len(unique_non_stock), "plugin_instances": len(non_stock),
        "missing_plugins": sum(
            1 for s in unique_non_stock if s["resolution_state"] == NOT_INSTALLED),
        "stock_devices": len(plugins) - len(non_stock),
        "heuristic_results": sum(1 for p in plugins if "heuristic" in p["flags"]),
        "most_used_plugin": most_used,
        "media_files": len(media),
        "missing_media": sum(1 for m in media if m["exists"] is False),
        "media_outside_folder": sum(1 for m in media if m["inside_project_folder"] is False),
        "opens_on": _opens_on(plugins, fmt),
        "send_ready": _send_ready(warnings, inventory is not None),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "app": {"name": "Rackcheck", "version": ENGINE_VERSION,
                "kb_version": getattr(kb, "version", None) if kb else None},
        "machine": {"os": f"{platform.system()} {platform.release()}".strip(),
                    "arch": platform.machine() or None,
                    "inventory_scanned_at": inventory_scanned_at},
        "options": {"redact_paths": opts.redact_paths},
        "source": source, "project": project, "tracks": tracks, "plugins": plugins,
        "plugin_summary": plugin_summary, "media": media, "unused_media": unused,
        "special_content": special, "summary": summary, "warnings": warnings,
    }


# ---- path redaction (SPEC-02 10.1) --------------------------------------------------


def redact_report(report: dict[str, Any], home: str | None = None) -> dict[str, Any]:
    """Copy of ``report`` safe to share: home folder becomes ``~``; absolute paths outside
    the project folder are dropped (media keep only their file name)."""
    r = copy.deepcopy(report)
    home_s = home if home is not None else str(Path.home())
    folder = (r["project"]["folder"] or {}).get("path")

    def tilde(p: str | None) -> str | None:
        if not p:
            return p
        pn = _norm_path(p)
        hn = _norm_path(home_s)
        if pn == hn:
            return "~"
        if pn.startswith(hn + os.sep):
            rest = p[len(home_s):].lstrip("/\\")
            return "~/" + rest.replace("\\", "/")
        return p

    def inside_folder(p: str) -> bool:
        return bool(folder) and (
            _norm_path(p) == _norm_path(folder) or _norm_path(p).startswith(
                _norm_path(folder) + os.sep))

    def rel(p: str) -> str:
        try:
            return Path(os.path.relpath(p, folder)).as_posix()
        except ValueError:
            return p

    def is_abs(p: str) -> bool:
        return os.path.isabs(p) or bool(re.match(r"^[A-Za-z]:[\\/]", p)) or p.startswith("/")

    def scrub(p: str | None) -> str | None:
        """Absolute path outside the project folder -> dropped (None)."""
        if not p:
            return p
        if not is_abs(p):
            return p
        if inside_folder(p):
            return rel(p)
        return None

    r["source"]["path"] = tilde(r["source"]["path"])
    if folder:
        r["project"]["folder"]["path"] = tilde(folder)
    for p in r["plugins"]:
        inst = p["resolution"]["installed"]
        if inst:
            inst["path"] = None
        hint = p["identity"].get("file_hint")
        if hint and is_abs(hint):
            p["identity"]["file_hint"] = os.path.basename(hint.replace("\\", "/"))
    for m in r["media"]:
        new = scrub(m["path"])
        m["path"] = new if new is not None else os.path.basename(m["path"].replace("\\", "/"))
    for u in r["unused_media"]:
        u["path"] = scrub(u["path"]) or os.path.basename(u["path"].replace("\\", "/"))
    for s in r["special_content"]:
        if s.get("path") and is_abs(s["path"]):
            s["path"] = scrub(s["path"]) or os.path.basename(s["path"].replace("\\", "/"))
    r["options"]["redact_paths"] = True
    return r
