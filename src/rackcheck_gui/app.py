"""Launches the pywebview window (SPEC-03 section 2). Entry point: ``rackcheck-gui``."""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

from .api import Api
from .storage import Storage

STATIC_DIR = Path(__file__).parent / "static"
MIN_SIZE = (900, 600)

_OPEN_FILTERS = ("All files (*.*)",)


class WebviewDialogs:
    """Native dialogs via the window; set ``window`` after it is created."""

    def __init__(self) -> None:
        self.window: Any = None

    def _fd(self, kind: str, **kwargs: Any) -> Any:
        import webview

        return self.window.create_file_dialog(getattr(webview.FileDialog, kind), **kwargs)

    def open_files(self) -> Any:
        return self._fd("OPEN", allow_multiple=True, file_types=_OPEN_FILTERS)

    def open_folder(self) -> Any:
        return self._fd("FOLDER")

    def save(self, filename: str, directory: str | None, ext: str) -> Any:
        return self._fd("SAVE", directory=directory or "", save_filename=filename)


def _setup_logging(logs_dir: Path) -> None:
    handler = logging.handlers.TimedRotatingFileHandler(
        logs_dir / "rackcheck.log", when="midnight", backupCount=7, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("rackcheck_gui")
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def make_emitter(window_ref: list[Any]):
    """Python -> JS events as ``window`` CustomEvents named ``rackcheck`` (SPEC-03 section 8)."""

    def emit(event: str, payload: dict[str, Any]) -> None:
        if not window_ref:
            return
        detail = json.dumps({"event": event, "payload": payload}, ensure_ascii=True)
        window_ref[0].evaluate_js(
            f"window.dispatchEvent(new CustomEvent('rackcheck', {{detail: {detail}}}))")

    return emit


def main(argv: list[str] | None = None) -> int:
    try:
        import webview
        from webview.dom import DOMEventHandler
    except ImportError:
        print("The GUI needs pywebview. Install it with: pip install -e .[gui]", file=sys.stderr)
        return 1

    store = Storage()
    _setup_logging(store.logs_dir)
    window_ref: list[Any] = []
    dialogs = WebviewDialogs()
    api = Api(store.root, emit=make_emitter(window_ref), dialogs=dialogs)

    window = webview.create_window(
        "Rackcheck", url=str(STATIC_DIR / "index.html"), js_api=api,
        width=1180, height=780, min_size=MIN_SIZE, text_select=True)
    window_ref.append(window)
    dialogs.window = window

    def on_drop(event: dict[str, Any]) -> None:
        paths = [f["pywebviewFullPath"] for f in event.get("dataTransfer", {}).get("files", [])
                 if f.get("pywebviewFullPath")]
        for p in paths:
            api._grant(p)  # a drop is an explicit user choice (SPEC-07)
        make_emitter(window_ref)("app.dropped", {"paths": paths})

    def bind() -> None:
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
        window.dom.document.events.dragover += DOMEventHandler(lambda e: None, True, True)

    # http_server=True so the page has a real http://127.0.0.1 origin for its CSP.
    webview.start(bind, http_server=True, private_mode=False,
                  storage_path=str(store.root / "webview"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
