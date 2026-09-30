"""The js_api bridge (SPEC-03 sections 7 and 8, SPEC-07 bridge-abuse row).

Every public method returns JSON-serialisable data or ``{"error": {...}}``; nothing raises
into JavaScript. Long work runs on worker threads and reports through ``emit(event,
payload)``. Only the methods listed in SPEC-03 section 7 (plus the file dialogs and
``get_plugin_folders`` the screens need) are public; everything else starts with ``_`` so
pywebview does not expose it.

Paths coming from JavaScript are only honoured if the user chose them: through a native
dialog, a window drop, or a recent-report entry (SPEC-07). Tests grant paths with
``api._grant``.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import platform
import subprocess
import sys
import threading
import traceback
import uuid
import webbrowser
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from rackcheck_engine import ENGINE_VERSION, SCHEMA_VERSION
from rackcheck_engine.detect import DAW_NAMES, ProjectFormat
from rackcheck_engine.detect import detect as detect_format
from rackcheck_engine.errors import (
    BUSY,
    EXPORT_FAILED,
    INTERNAL_ERROR,
    INVALID_ARGUMENT,
    JOB_NOT_FOUND,
    MULTIPLE_PROJECTS,
    NO_PROJECT_FOUND,
    NOT_AVAILABLE,
    PATH_NOT_ALLOWED,
    PATH_NOT_FOUND,
    REPORT_INVALID,
    REPORT_NOT_FOUND,
    EngineError,
)
from rackcheck_engine.export import (
    default_filename,
    write_csv,
    write_json,
    write_plugin_list,
)
from rackcheck_engine.inputs import ProjectCandidate, resolve
from rackcheck_engine.inventory.scan import (
    InstalledPlugin,
    load_inventory,
    save_inventory,
    scan_installed,
)
from rackcheck_engine.inventory.scan import default_plugin_dirs as _default_plugin_dirs
from rackcheck_engine.kb import KnowledgeBase
from rackcheck_engine.model import PluginFormat
from rackcheck_engine.readers import reader_for
from rackcheck_engine.report import ReportOptions, plugin_group_key
from rackcheck_engine.service import STAGES, scan_candidate

from . import APP_VERSION
from .storage import DEFAULT_SETTINGS, Storage

log = logging.getLogger("rackcheck_gui")

EXPORT_FORMATS = {
    "json": "json", "csv_full": "csv", "csv_plugins": "csv", "csv_missing": "csv", "html": "html",
}
_REQUIRED_REPORT_KEYS = {
    "schema_version": str, "source": dict, "project": dict, "tracks": list, "plugins": list,
    "plugin_summary": list, "media": list, "summary": dict, "warnings": list,
}
_MAX_REPORT_BYTES = 64 * 1024 * 1024

# Shown on Home; the hint explains the route for formats we can't read directly yet.
_FORMAT_HINTS = {
    ProjectFormat.BITWIG_BWPROJECT:
        "Export as DAWproject (File > Export DAWproject) and drop that file instead.",
    ProjectFormat.PROTOOLS_PTX:
        "Pro Tools sessions need one extra step for now: File > Export > Session Info as "
        "Text, then drop the text file here.",
    ProjectFormat.PROTOOLS_TEXT:
        "Session Info as Text exports are recognised but can't be read in this version yet.",
}


class _Cancelled(Exception):
    pass


@dataclass
class _Job:
    id: str
    kind: str
    cancel: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    state: str = "running"  # running | done | failed | cancelled
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def check(self) -> None:
        if self.cancel.is_set():
            raise _Cancelled


def _norm(p: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(p))


def _mtime(path: str) -> float | None:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def _internal_error() -> dict[str, Any]:
    return EngineError(
        INTERNAL_ERROR,
        "Something went wrong on our side. Details were saved to the log.",
    ).to_dict()


def _api(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Map every failure to the SPEC-03 error format; never raise into JavaScript."""

    @functools.wraps(fn)
    def wrapper(self: Api, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(self, *args, **kwargs)
        except EngineError as exc:
            return exc.to_dict()
        except Exception:
            log.error("Unhandled error in %s\n%s", fn.__name__, traceback.format_exc())
            return _internal_error()

    return wrapper


def _s_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x for x in v)


_SETTING_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "first_run_done": lambda v: isinstance(v, bool),
    "plugin_folders_disabled": _s_list,
    "plugin_folders_extra": _s_list,
    "redact_paths": lambda v: isinstance(v, bool),
    "csv_delimiter": lambda v: v in (",", ";"),
    "default_export_dir": lambda v: v is None or (isinstance(v, str) and bool(v)),
    "appearance": lambda v: v in ("system", "light", "dark"),
}


def _reveal_in_file_manager(path: str) -> None:
    p = Path(path)
    if sys.platform == "win32":
        if p.is_dir():
            subprocess.Popen(["explorer", os.path.normpath(path)])
        else:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", str(p if p.is_dir() else p.parent)])


class Api:
    def __init__(
        self,
        data_dir: Path | str | None = None,
        *,
        emit: Callable[[str, dict[str, Any]], None] | None = None,
        dialogs: Any = None,
        kb_path: str | None = None,
        opener: Callable[[str], object] | None = None,
        revealer: Callable[[str], None] | None = None,
        plugin_dirs: Callable[[], dict[PluginFormat, list[Path]]] | None = None,
    ) -> None:
        self._store = Storage(data_dir)
        self._emit_fn = emit
        self._dialogs = dialogs
        self._kb_path = kb_path
        self._kb: KnowledgeBase | None = None
        self._opener = opener or webbrowser.open
        self._revealer = revealer or _reveal_in_file_manager
        self._plugin_dirs = plugin_dirs or _default_plugin_dirs
        self._lock = threading.RLock()
        self._jobs: dict[str, _Job] = {}
        self._reports: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        self._granted: set[str] = {_norm(self._store.logs_dir)}
        saved = self._store.load_settings()  # folders the user chose in earlier sessions
        for d in [*saved["plugin_folders_extra"], saved["default_export_dir"]]:
            if isinstance(d, str) and d:
                self._grant(d)

    # ------------------------------------------------------------------ internals
    def _grant(self, path: str | os.PathLike[str]) -> None:
        with self._lock:
            self._granted.add(_norm(path))

    def _allowed(self, path: str) -> bool:
        n = _norm(path)
        with self._lock:
            return any(n == g or n.startswith(g.rstrip(os.sep) + os.sep) for g in self._granted)

    def _check_path(self, path: Any, *, must_exist: bool = True) -> str:
        if not isinstance(path, str) or not path.strip() or "\x00" in path:
            raise EngineError(INVALID_ARGUMENT, "That path isn't valid.")
        if not self._allowed(path):
            raise EngineError(
                PATH_NOT_ALLOWED,
                "Choose or drop that file or folder in the app first.",
                {"path": path},
            )
        if must_exist and not Path(path).exists():
            raise EngineError(
                PATH_NOT_FOUND, "That file or folder no longer exists.", {"path": path})
        return path

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._emit_fn is None:
            return
        try:
            self._emit_fn(event, payload)
        except Exception:
            log.warning("Event %s could not be delivered\n%s", event, traceback.format_exc())

    def _get_kb(self) -> KnowledgeBase:
        if self._kb is None:
            self._kb = KnowledgeBase.load(self._kb_path)
        return self._kb

    def _spawn(self, kind: str, work: Callable[[_Job], dict[str, Any]]) -> str:
        with self._lock:
            if any(j.kind == kind and j.state == "running" for j in self._jobs.values()):
                what = "A scan" if kind == "scan" else "A plugin scan"
                raise EngineError(BUSY, f"{what} is already running. Wait for it or cancel it.")
            job = _Job(id=uuid.uuid4().hex[:12], kind=kind)
            self._jobs[job.id] = job

        def runner() -> None:
            try:
                result = work(job)
                job.result = result
                job.state = "done"
                self._emit("job.done", {"job_id": job.id, "kind": kind, **result})
            except _Cancelled:
                job.state = "cancelled"
                self._emit("job.cancelled", {"job_id": job.id, "kind": kind})
            except EngineError as exc:
                job.state = "failed"
                job.error = exc.to_dict()["error"]
                self._emit("job.failed", {"job_id": job.id, "kind": kind, "error": job.error})
            except Exception:
                log.error("Job %s (%s) crashed\n%s", job.id, kind, traceback.format_exc())
                job.state = "failed"
                job.error = _internal_error()["error"]
                self._emit("job.failed", {"job_id": job.id, "kind": kind, "error": job.error})
            finally:
                job.done.set()

        threading.Thread(target=runner, name=f"rackcheck-{kind}", daemon=True).start()
        return job.id

    def _wait(self, job_id: str, timeout: float = 30.0) -> _Job:
        """Test helper: block until a job finishes."""
        job = self._jobs[job_id]
        job.done.wait(timeout)
        return job

    def _progress(self, job: _Job, stage: str, message: str, percent: float | None = None,
                  ) -> None:
        job.check()
        self._emit("job.progress", {
            "job_id": job.id, "kind": job.kind, "stage": stage, "stage_index": STAGES.index(stage),
            "stage_count": len(STAGES), "percent": percent, "message": message,
        })

    def _load_cached_inventory(self) -> tuple[list[InstalledPlugin] | None, str | None]:
        meta = self._store.load_inventory_meta()
        if not meta:
            return None, None
        try:
            return load_inventory(self._store.inventory_path), meta.get("scanned_at")
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            log.warning("Saved plugin inventory could not be read\n%s", traceback.format_exc())
            return None, None

    def _remember(self, report: dict[str, Any], meta: dict[str, Any]) -> str:
        report_id = self._store.save_report(report, meta)
        with self._lock:
            self._reports[report_id] = (report, meta)
        return report_id

    def _lookup(self, ident: Any) -> tuple[str, dict[str, Any], dict[str, Any]]:
        if not isinstance(ident, str) or not ident:
            raise EngineError(INVALID_ARGUMENT, "A report id is required.")
        with self._lock:
            job = self._jobs.get(ident)
        if job is not None:
            if job.state != "done" or not job.result or not job.result.get("report_id"):
                raise EngineError(REPORT_NOT_FOUND, "That scan has no report.")
            ident = job.result["report_id"]
        with self._lock:
            cached = self._reports.get(ident)
        if cached is None:
            loaded = self._store.load_report(ident)
            if loaded is None:
                raise EngineError(REPORT_NOT_FOUND, "That report isn't available any more.")
            cached = loaded
            with self._lock:
                self._reports[ident] = cached
        return ident, cached[0], cached[1]

    def _known_paths(self) -> set[str]:
        out: set[str] = set()
        with self._lock:
            reports = [r for r, _ in self._reports.values()]

        def add(value: Any) -> None:
            if isinstance(value, str) and value:
                out.add(_norm(value))

        for r in reports:
            add((r.get("source") or {}).get("path"))
            add(((r.get("project") or {}).get("folder") or {}).get("path"))
            for m in [*(r.get("media") or []), *(r.get("unused_media") or [])]:
                if isinstance(m, dict):
                    add(m.get("path"))
            for p in r.get("plugins") or []:
                add((((p or {}).get("resolution") or {}).get("installed") or {}).get("path"))
        return out

    # ---------------------------------------------------------------- app + dialogs
    @_api
    def get_app_info(self) -> dict[str, Any]:
        seen: dict[str, dict[str, Any]] = {}
        for fmt, name in DAW_NAMES.items():
            entry = seen.setdefault(
                name, {"daw_name": name, "readable": False, "hint": None, "formats": []})
            entry["formats"].append(fmt.value)
            if reader_for(fmt) is not None:
                entry["readable"] = True
            entry["hint"] = entry["hint"] or _FORMAT_HINTS.get(fmt)
        kb = self._get_kb()
        return {
            "app_version": APP_VERSION, "engine_version": ENGINE_VERSION,
            "kb_version": kb.version, "schema_version": SCHEMA_VERSION,
            "supported_formats": sorted(
                seen.values(), key=lambda e: (not e["readable"], e["daw_name"])),
            "platform": platform.system(), "data_dir": str(self._store.root),
        }

    def _dialog(self, kind: str, **kwargs: Any) -> list[str] | None:
        if self._dialogs is None:
            raise EngineError(NOT_AVAILABLE, "File dialogs aren't available here.")
        result = getattr(self._dialogs, kind)(**kwargs)
        if not result:
            return None
        paths = [str(p) for p in ([result] if isinstance(result, str) else result)]
        for p in paths:
            self._grant(p)
        return paths

    @_api
    def choose_files(self) -> dict[str, Any]:
        paths = self._dialog("open_files")
        return {"cancelled": True} if paths is None else {"paths": paths}

    @_api
    def choose_folder(self) -> dict[str, Any]:
        paths = self._dialog("open_folder")
        return {"cancelled": True} if paths is None else {"paths": paths}

    @_api
    def choose_export_path(self, report_id: str, format: str) -> dict[str, Any]:  # noqa: A002
        if format not in EXPORT_FORMATS:
            raise EngineError(INVALID_ARGUMENT, "Unknown export format.", {"format": format})
        _, report, _ = self._lookup(report_id)
        ext = EXPORT_FORMATS[format]
        name = default_filename(report, ext)
        if format == "csv_plugins":
            name = name.replace("_rackcheck_", "_plugins_", 1)
        elif format == "csv_missing":
            name = name.replace("_rackcheck_", "_missing_plugins_", 1)
        paths = self._dialog(
            "save", filename=name, directory=self._settings()["default_export_dir"], ext=ext)
        return {"cancelled": True} if paths is None else {"path": paths[0]}

    @_api
    def choose_bundle_path(self) -> dict[str, Any]:
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        paths = self._dialog(
            "save", filename=f"rackcheck_support_{stamp}.zip",
            directory=self._settings()["default_export_dir"], ext="zip")
        return {"cancelled": True} if paths is None else {"path": paths[0]}

    # -------------------------------------------------------------------- detection
    @_api
    def detect(self, paths: list[str]) -> Any:
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            raise EngineError(INVALID_ARGUMENT, "A list of paths is required.")
        return [self._detect_one(p) for p in paths]

    def _detect_one(self, path: str) -> dict[str, Any]:
        try:
            self._check_path(path)
            top = detect_format(Path(path))
            with resolve(path) as resolved:
                found = [self._describe_candidate(c, path, resolved.temp_dirs)
                         for c in resolved.candidates]
        except EngineError as exc:
            return {"path": path, "format": None, "confidence": None, "reason": None,
                    "projects_found": [], **exc.to_dict()}
        return {
            "path": path, "format": top.format.value,
            "confidence": top.confidence.value if top.confidence else None,
            "reason": top.reason, "daw_name": DAW_NAMES.get(top.format),
            "projects_found": found,
        }

    @staticmethod
    def _rel(candidate: ProjectCandidate, root: str, temp_dirs: list[Path]) -> str:
        p = Path(candidate.detection.path)
        bases = [Path(root), *temp_dirs] if Path(root).is_dir() else temp_dirs
        for base in bases:
            try:
                return p.relative_to(base).as_posix()
            except ValueError:
                continue
        return p.name

    def _describe_candidate(self, c: ProjectCandidate, root: str, temp_dirs: list[Path]
                            ) -> dict[str, Any]:
        det = c.detection
        return {
            "name": Path(det.path).name, "rel_path": self._rel(c, root, temp_dirs),
            "format": det.format.value, "daw_name": DAW_NAMES.get(det.format),
            "confidence": det.confidence.value if det.confidence else None,
            "reason": det.reason, "is_backup": c.is_backup, "from_archive": c.from_archive,
            "is_report": det.format == ProjectFormat.REPORT_JSON,
            "readable": det.format == ProjectFormat.REPORT_JSON
            or reader_for(det.format) is not None,
        }

    # ------------------------------------------------------------------------ scans
    @_api
    def start_scan(self, path: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        self._check_path(path)
        opts = options if options is not None else {}
        if not isinstance(opts, dict):
            raise EngineError(INVALID_ARGUMENT, "Options must be an object.")
        projects = opts.get("projects")
        if projects is not None and not (
                isinstance(projects, list) and all(isinstance(p, str) for p in projects)):
            raise EngineError(INVALID_ARGUMENT, "Options.projects must be a list of paths.")
        use_inventory = bool(opts.get("use_inventory", True))
        return {"job_id": self._spawn(
            "scan", lambda job: self._do_scan(job, path, use_inventory, projects))}

    def _do_scan(self, job: _Job, path: str, use_inventory: bool, projects: list[str] | None,
                 ) -> dict[str, Any]:
        self._progress(job, "detect", "Detecting the project type")
        inventory, inv_at = self._load_cached_inventory() if use_inventory else (None, None)
        kb = self._get_kb()
        options = ReportOptions(redact_paths=False)  # cache is unredacted; export redacts
        report_ids: list[str] = []
        errors: list[dict[str, Any]] = []
        with resolve(path) as resolved:
            job.check()
            cands = resolved.candidates
            if projects:
                wanted = set(projects)
                cands = [c for c in cands if self._rel(c, path, resolved.temp_dirs) in wanted]
            if not cands:
                is_zip = Path(path).suffix.lower() == ".zip"
                raise EngineError(
                    NO_PROJECT_FOUND,
                    "No project files found in this zip." if is_zip
                    else "No project files found here.", {"path": path})
            if len(cands) > 1 and not projects:
                raise EngineError(
                    MULTIPLE_PROJECTS, "More than one project was found. Pick which to scan.",
                    {"projects": [self._describe_candidate(c, path, resolved.temp_dirs)
                                  for c in cands]})
            for i, cand in enumerate(cands, start=1):
                label = Path(cand.detection.path).name
                prefix = f"{label}: " if len(cands) > 1 else ""

                def on_stage(stage: str, prefix: str = prefix, i: int = i,
                             n: int = len(cands)) -> None:
                    msg = ("Reading the project" if stage == "read"
                           else "Matching plugins and building the report")
                    self._progress(job, stage, prefix + msg, None if n == 1 else (i - 1) / n)

                entry = scan_candidate(cand, inventory, inv_at, kb, options, on_stage)
                job.check()
                if "report" in entry:
                    src = cand.from_archive or entry["report"]["source"]["path"]
                    meta = {
                        "imported": False, "source_path": src, "input_path": path,
                        "rel_path": self._rel(cand, path, resolved.temp_dirs),
                        "from_archive": cand.from_archive, "source_mtime": _mtime(src),
                    }
                    report_ids.append(self._remember(entry["report"], meta))
                else:
                    err = entry["error"]
                    errors.append({**err, "details": {
                        **err.get("details", {}), "detection": entry["detection"]}})
        if not report_ids:
            raise EngineError(errors[0]["code"], errors[0]["message"], errors[0]["details"])
        return {"report_id": report_ids[0], "report_ids": report_ids, "errors": errors}

    @_api
    def cancel_job(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get(job_id) if isinstance(job_id, str) else None
        if job is None:
            raise EngineError(JOB_NOT_FOUND, "That job doesn't exist.")
        if job.state == "running":
            job.cancel.set()
        return {"ok": True}

    @_api
    def get_report(self, id: str) -> dict[str, Any]:  # noqa: A002
        report_id, report, meta = self._lookup(id)
        imported = bool(meta.get("imported"))
        src = None if imported else meta.get("source_path")
        stale = False
        if src and meta.get("source_mtime") is not None:
            now = _mtime(src)
            stale = now is not None and now != meta["source_mtime"]
        if src:
            self._grant(src)  # reopening one of the user's own recent scans
            if meta.get("input_path"):
                self._grant(meta["input_path"])
        keys: dict[str, str] = {}
        for p in report.get("plugins") or []:
            try:
                keys[p["id"]] = plugin_group_key(p)
            except (KeyError, TypeError, AttributeError):
                continue
        return {"report_id": report_id, "report": report, "imported": imported, "stale": stale,
                "plugin_keys": keys,
                "source_path": src, "input_path": None if imported else meta.get("input_path"),
                "rel_path": meta.get("rel_path")}

    @_api
    def list_recent(self) -> Any:
        return self._store.list_recent()

    @_api
    def clear_recent(self) -> dict[str, Any]:
        with self._lock:
            self._reports.clear()
        return {"ok": True, "removed": self._store.clear_recent()}

    @_api
    def open_report_file(self, path: str) -> dict[str, Any]:
        self._check_path(path)
        p = Path(path)
        try:
            if p.stat().st_size > _MAX_REPORT_BYTES:
                raise EngineError(REPORT_INVALID, "That file is too large to be a report.")
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise EngineError(REPORT_INVALID, "That file isn't a readable Rackcheck report.",
                              {"reason": str(exc)}) from exc
        bad = [k for k, t in _REQUIRED_REPORT_KEYS.items()
               if not isinstance(data, dict) or not isinstance(data.get(k), t)]
        if bad or not isinstance((data["summary"]).get("send_ready"), dict):
            raise EngineError(REPORT_INVALID, "That file isn't a Rackcheck report.",
                              {"missing_or_wrong": bad})
        report_id = self._remember(
            data, {"imported": True, "source_path": None, "opened_from": p.name})
        return {"report_id": report_id}

    # ---------------------------------------------------------------------- exports
    @_api
    def export_report(self, report_id: str, format: str, dest_path: str,  # noqa: A002
                      options: dict[str, Any] | None = None) -> dict[str, Any]:
        if format not in EXPORT_FORMATS:
            raise EngineError(INVALID_ARGUMENT, "Unknown export format.", {"format": format})
        if format == "html":
            raise EngineError(NOT_AVAILABLE, "The HTML report isn't available yet.")
        self._check_path(dest_path, must_exist=False)
        _, report, _ = self._lookup(report_id)
        settings = self._settings()
        opts = options if isinstance(options, dict) else {}
        redact = bool(opts.get("redact_paths", settings["redact_paths"]))
        delim = opts.get("csv_delimiter", settings["csv_delimiter"])
        if delim not in (",", ";"):
            raise EngineError(INVALID_ARGUMENT, "The CSV delimiter must be a comma or semicolon.")
        try:
            if format == "json":
                out = write_json(report, dest_path, redact_paths=redact)
            elif format == "csv_full":
                out = write_csv(report, dest_path, redact_paths=redact, delimiter=delim)
            else:
                out = write_plugin_list(report, dest_path, missing_only=format == "csv_missing",
                                        redact_paths=redact, delimiter=delim)
        except OSError as exc:
            raise EngineError(
                EXPORT_FAILED,
                "We couldn't save that file. Check the folder is writable and try again.",
                {"reason": str(exc)}) from exc
        return {"path": str(out)}

    # -------------------------------------------------------------------- inventory
    def _folder_table(self) -> list[dict[str, Any]]:
        s = self._settings()
        disabled = {_norm(p) for p in s["plugin_folders_disabled"]}
        rows: dict[str, dict[str, Any]] = {}
        for fmt, dirs in self._plugin_dirs().items():
            for d in dirs:
                key = _norm(d)
                row = rows.setdefault(key, {
                    "path": str(d), "formats": [], "custom": False,
                    "exists": Path(d).is_dir(), "enabled": key not in disabled})
                row["formats"].append(fmt.value)
        for d in s["plugin_folders_extra"]:
            rows.setdefault(_norm(d), {
                "path": d, "formats": [], "custom": True, "exists": Path(d).is_dir(),
                "enabled": _norm(d) not in disabled})
        return list(rows.values())

    @_api
    def get_plugin_folders(self) -> dict[str, Any]:
        return {"folders": self._folder_table()}

    @_api
    def start_inventory_scan(self, folders: list[str] | None = None) -> dict[str, Any]:
        tasks: list[tuple[PluginFormat, Path]] = []
        if folders is None:
            s = self._settings()
            disabled = {_norm(p) for p in s["plugin_folders_disabled"]}
            for fmt, dirs in self._plugin_dirs().items():
                tasks += [(fmt, Path(d)) for d in dirs if _norm(d) not in disabled]
            for d in s["plugin_folders_extra"]:
                if _norm(d) not in disabled:
                    tasks += [(fmt, Path(d)) for fmt in PluginFormat]
        else:
            if not isinstance(folders, list) or not all(isinstance(f, str) for f in folders):
                raise EngineError(INVALID_ARGUMENT, "Folders must be a list of paths.")
            defaults = {_norm(d) for ds in self._plugin_dirs().values() for d in ds}
            for f in folders:
                if _norm(f) not in defaults:
                    self._check_path(f)
                tasks += [(fmt, Path(f)) for fmt in PluginFormat]
        tasks = [(f, d) for f, d in tasks if d.is_dir()]
        return {"job_id": self._spawn("inventory", lambda job: self._do_inventory(job, tasks))}

    def _do_inventory(self, job: _Job, tasks: list[tuple[PluginFormat, Path]]) -> dict[str, Any]:
        found: dict[tuple[str, str, str], InstalledPlugin] = {}
        failed = 0
        for i, (fmt, folder) in enumerate(tasks):
            self._progress(job, "read", f"Scanning {folder}", i / max(len(tasks), 1))
            try:
                for p in scan_installed({fmt: [folder]}):
                    found.setdefault((_norm(p.path), p.format.value, p.name), p)
            except Exception:
                failed += 1  # one bad folder must not stop the rest (SPEC-03 section 5)
                log.warning("Plugin folder %s could not be scanned\n%s", folder,
                            traceback.format_exc())
        job.check()
        plugins = sorted(found.values(), key=lambda p: (p.name.lower(), p.format.value))
        scanned_at = datetime.now().astimezone().isoformat(timespec="seconds")
        save_inventory(plugins, self._store.inventory_path)
        self._store.save_inventory_meta({"scanned_at": scanned_at, "count": len(plugins)})
        self._emit("inventory.updated", {"scanned_at": scanned_at, "count": len(plugins)})
        return {"report_id": None, "count": len(plugins), "scanned_at": scanned_at,
                "folders_failed": failed}

    @_api
    def get_inventory(self) -> dict[str, Any]:
        meta = self._store.load_inventory_meta()
        if not meta:
            return {"scanned_at": None, "plugins": []}
        plugins, _ = self._load_cached_inventory()
        return {"scanned_at": meta.get("scanned_at"),
                "plugins": [p.to_dict() for p in plugins or []]}

    # --------------------------------------------------------------------- settings
    def _settings(self) -> dict[str, Any]:
        return self._store.load_settings()

    @_api
    def get_settings(self) -> dict[str, Any]:
        return self._settings()

    @_api
    def set_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise EngineError(INVALID_ARGUMENT, "Settings must be an object.")
        current = self._settings()
        for key, value in patch.items():
            if key not in DEFAULT_SETTINGS:
                raise EngineError(INVALID_ARGUMENT, f"Unknown setting: {key}.", {"key": key})
            if not _SETTING_VALIDATORS[key](value):
                raise EngineError(INVALID_ARGUMENT, f"That value isn't valid for {key}.",
                                  {"key": key})
        # Folders must have been chosen by the user; ones already saved are re-granted at start.
        for d in patch.get("plugin_folders_extra", []):
            if d not in current["plugin_folders_extra"]:
                self._check_path(d, must_exist=False)
        if patch.get("default_export_dir"):
            self._check_path(patch["default_export_dir"], must_exist=False)
        current.update(patch)
        self._store.save_settings(current)
        return current

    @_api
    def update_kb(self) -> dict[str, Any]:
        raise EngineError(NOT_AVAILABLE,
                          "Knowledge base updates aren't available in this version.")

    # ---------------------------------------------------------------- OS integration
    @_api
    def open_url(self, url: str) -> dict[str, Any]:
        parsed = urlparse(url) if isinstance(url, str) else None
        if not parsed or parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise EngineError(INVALID_ARGUMENT, "Only web links (http or https) can be opened.")
        self._opener(url)
        return {"ok": True}

    @_api
    def reveal_path(self, path: str) -> dict[str, Any]:
        if not isinstance(path, str) or not path.strip() or "\x00" in path:
            raise EngineError(INVALID_ARGUMENT, "That path isn't valid.")
        if not (self._allowed(path) or _norm(path) in self._known_paths()):
            raise EngineError(PATH_NOT_ALLOWED,
                              "That location isn't part of anything you've opened.")
        target = Path(path)
        if not target.exists():
            target = target.parent
            if not target.exists():
                raise EngineError(PATH_NOT_FOUND, "That location no longer exists.",
                                  {"path": path})
        self._revealer(str(target))
        return {"ok": True}

    @_api
    def create_support_bundle(self, dest_path: str) -> dict[str, Any]:
        self._check_path(dest_path, must_exist=False)
        kb = self._get_kb()
        versions = {"app_version": APP_VERSION, "engine_version": ENGINE_VERSION,
                    "kb_version": kb.version, "schema_version": SCHEMA_VERSION,
                    "python": sys.version.split()[0], "os": platform.platform()}
        try:
            with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("versions.json", json.dumps(versions, indent=2))
                for lf in sorted(self._store.logs_dir.glob("*.log*")):
                    zf.write(lf, f"logs/{lf.name}")
        except OSError as exc:
            raise EngineError(EXPORT_FAILED, "We couldn't save the support bundle.",
                              {"reason": str(exc)}) from exc
        return {"path": dest_path}

    @_api
    def get_log_folder(self) -> dict[str, Any]:
        return {"path": str(self._store.logs_dir)}
