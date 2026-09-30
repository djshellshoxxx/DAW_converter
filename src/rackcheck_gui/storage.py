"""Local storage for the GUI: settings, recent reports, inventory cache (SPEC-03 section 9).

Everything lives under one app-data folder. Nothing here touches the network.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

MAX_RECENT = 50

DEFAULT_SETTINGS: dict[str, Any] = {
    "first_run_done": False,
    "plugin_folders_disabled": [],
    "plugin_folders_extra": [],
    "redact_paths": False,
    "csv_delimiter": ",",
    "default_export_dir": None,
    "appearance": "system",
}


def default_data_dir() -> Path:
    override = os.environ.get("RACKCHECK_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Rackcheck"


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


class Storage:
    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.root = Path(data_dir) if data_dir else default_data_dir()
        self.reports_dir = self.root / "reports"
        self.logs_dir = self.root / "logs"
        self._lock = threading.RLock()
        for d in (self.root, self.reports_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)

    # settings -------------------------------------------------------------------
    def load_settings(self) -> dict[str, Any]:
        with self._lock:
            saved = _read_json(self.root / "settings.json", {})
            out = dict(DEFAULT_SETTINGS)
            if isinstance(saved, dict):
                for k, v in saved.items():
                    if k in DEFAULT_SETTINGS:
                        out[k] = v
            return out

    def save_settings(self, settings: dict[str, Any]) -> None:
        with self._lock:
            _write_json_atomic(self.root / "settings.json", settings)

    # reports --------------------------------------------------------------------
    def _index(self) -> list[dict[str, Any]]:
        idx = _read_json(self.root / "recent.json", [])
        return idx if isinstance(idx, list) else []

    def save_report(self, report: dict[str, Any], meta: dict[str, Any]) -> str:
        report_id = uuid.uuid4().hex[:16]
        with self._lock:
            _write_json_atomic(self.reports_dir / f"{report_id}.json",
                               {"meta": meta, "report": report})
            idx = self._index()
            summary = report.get("summary") or {}
            idx.append({
                "report_id": report_id,
                "project_name": (report.get("project") or {}).get("name"),
                "daw": (report.get("source") or {}).get("daw_name"),
                "scanned_at": report.get("generated_at"),
                "send_ready": (summary.get("send_ready") or {}).get("score"),
                "imported": bool(meta.get("imported")),
            })
            for old in idx[:-MAX_RECENT]:
                with contextlib.suppress(OSError):
                    (self.reports_dir / f"{old['report_id']}.json").unlink()
            _write_json_atomic(self.root / "recent.json", idx[-MAX_RECENT:])
        return report_id

    def load_report(self, report_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if not report_id.isalnum():
            return None
        data = _read_json(self.reports_dir / f"{report_id}.json", None)
        if not isinstance(data, dict) or "report" not in data:
            return None
        return data["report"], data.get("meta") or {}

    def list_recent(self) -> list[dict[str, Any]]:
        with self._lock:
            live = [e for e in self._index() if isinstance(e, dict)
                    and (self.reports_dir / f"{e.get('report_id')}.json").exists()]
        return list(reversed(live))

    def clear_recent(self) -> int:
        with self._lock:
            idx = self._index()
            for e in idx:
                with contextlib.suppress(OSError):
                    (self.reports_dir / f"{e.get('report_id')}.json").unlink()
            _write_json_atomic(self.root / "recent.json", [])
            return len(idx)

    # inventory ------------------------------------------------------------------
    @property
    def inventory_path(self) -> Path:
        return self.root / "inventory.json"

    def load_inventory_meta(self) -> dict[str, Any] | None:
        meta = _read_json(self.root / "inventory_meta.json", None)
        return meta if isinstance(meta, dict) and self.inventory_path.exists() else None

    def save_inventory_meta(self, meta: dict[str, Any]) -> None:
        _write_json_atomic(self.root / "inventory_meta.json", meta)
