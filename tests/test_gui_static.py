"""Static asset checks: local-only, no remote code, no HTML injection, no dummy bridge calls."""

from __future__ import annotations

import re
from pathlib import Path

import rackcheck_gui
from rackcheck_gui.api import Api

STATIC = Path(rackcheck_gui.__file__).parent / "static"
FILES = sorted(p for p in STATIC.iterdir() if p.is_file())


def test_static_assets_exist():
    names = {p.name for p in FILES}
    assert {"index.html", "app.js", "style.css"} <= names


def test_no_remote_urls_in_assets():
    pattern = re.compile(r"(https?:)?//[A-Za-z0-9][A-Za-z0-9.-]*\.[a-z]{2,}", re.I)
    for f in FILES:
        text = f.read_text(encoding="utf-8")
        for m in pattern.finditer(text):
            line = text[: m.start()].count("\n") + 1
            # The one allowed literal is the KVR search URL built for a "free alternative" click,
            # which is opened in the system browser through the bridge, never loaded by the page.
            near = text[m.start(): m.start() + 60]
            assert f.name == "app.js" and "kvraudio.com/plugins/search" in near, (
                f"{f.name}:{line} references a remote URL: {m.group(0)}")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "src=\"http" not in html and "href=\"http" not in html
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert "@import" not in css and "url(" not in css


def test_csp_forbids_remote_and_inline_scripts():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "default-src 'self'" in csp and "script-src 'self'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)  # no inline scripts
    assert not re.search(r"\son[a-z]+=", html)  # no inline handlers


def test_js_never_injects_html_or_evals():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(",
                   "new Function", "setTimeout('", 'setTimeout("', "XMLHttpRequest", "fetch(",
                   "WebSocket", "window.open", "target=\"_blank\"", "localStorage"):
        assert banned not in js, banned


def test_every_bridge_call_exists_in_the_api():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    called = set(re.findall(r"call\('([a-z_]+)'", js))
    public = {n for n in dir(Api) if not n.startswith("_") and callable(getattr(Api, n))}
    assert called, "front end makes no bridge calls?"
    assert called <= public, called - public


def test_every_public_api_method_is_used_by_the_ui_or_in_spec():
    """No dummy controls: methods the UI doesn't call must be deliberate (SPEC-03 contract)."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    called = set(re.findall(r"call\('([a-z_]+)'", js))
    unused = {n for n in dir(Api) if not n.startswith("_") and callable(getattr(Api, n))} - called
    assert unused <= {"update_kb"}, unused
