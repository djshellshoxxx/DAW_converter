"""Homepage link resolution chain (SPEC-01 section 7, Phase 2). Never touches the network.

First hit wins:
1. Knowledge base entry for the exact plugin           source ``kb_plugin``
2. VST3 moduleinfo Factory URL / CLAP descriptor url   source ``moduleinfo`` / ``clap_descriptor``
3. Knowledge base vendor homepage                      source ``kb_vendor``
4. Reverse-domain from a macOS bundle id (heuristic)   source ``bundle_id_heuristic``
5. A KVR Audio search link                             source ``search``
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus, urlparse

from .inventory.scan import InstalledPlugin
from .kb import PluginRecord, VendorRecord
from .model import PluginFormat

SRC_KB_PLUGIN = "kb_plugin"
SRC_MODULEINFO = "moduleinfo"
SRC_CLAP = "clap_descriptor"
SRC_KB_VENDOR = "kb_vendor"
SRC_BUNDLE_ID = "bundle_id_heuristic"
SRC_SEARCH = "search"

KVR_SEARCH_URL = "https://www.kvraudio.com/plugins/search?q="

_TLDS = {"com", "net", "org", "io", "co", "de", "fr", "se", "nl", "it", "uk", "jp", "ca", "ch",
         "dk", "fi", "no", "es", "eu", "me", "us", "info", "audio", "music", "studio", "app",
         "dev", "ai", "fm"}
# Bundle id prefixes that say nothing about the vendor's website.
_GENERIC_DOMAINS = {"apple", "yourcompany", "example", "yourdomain", "juce", "developer"}


def safe_http_url(url: str | None) -> str | None:
    """Only http/https URLs with a host are ever put in a report (SPEC-03 open_url)."""
    if not url or not isinstance(url, str):
        return None
    try:
        parts = urlparse(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    return url.strip()


def domain_from_bundle_id(bundle_id: str | None) -> str | None:
    """``com.fabfilter.Pro-Q`` -> ``fabfilter.com``; None when it can't be justified."""
    if not bundle_id:
        return None
    parts = bundle_id.strip().lower().split(".")
    if len(parts) < 3 or parts[0] not in _TLDS:
        return None
    label = parts[1]
    if not label or label in _GENERIC_DOMAINS:
        return None
    if not all(c.isalnum() or c == "-" for c in label):
        return None
    return f"{label}.{parts[0]}"


def kvr_search_url(name: str | None, vendor: str | None = None) -> str | None:
    query = " ".join(x for x in (name, vendor) if x).strip()
    return f"{KVR_SEARCH_URL}{quote_plus(query)}" if query else None


def _link(url: str | None, source: str | None) -> dict[str, Any]:
    return {"url": url, "source": source if url else None}


def resolve_links(
    *,
    name: str | None,
    vendor_name: str | None,
    kb_plugin: PluginRecord | None,
    kb_vendor: VendorRecord | None,
    installed: InstalledPlugin | None,
    is_stock: bool = False,
) -> dict[str, dict[str, Any]]:
    """Return ``{"homepage": {url, source}, "manual": {...}, "support": {...}}``."""
    empty = _link(None, None)
    if is_stock:
        return {"homepage": dict(empty), "manual": dict(empty), "support": dict(empty)}

    homepage: dict[str, Any] = dict(empty)
    candidates: list[tuple[str | None, str]] = []
    if kb_plugin is not None:
        candidates.append((kb_plugin.homepage, SRC_KB_PLUGIN))
    if installed is not None:
        src = SRC_CLAP if installed.format == PluginFormat.CLAP else SRC_MODULEINFO
        candidates.append((installed.url, src))
    if kb_vendor is not None:
        candidates.append((kb_vendor.homepage, SRC_KB_VENDOR))
    if installed is not None:
        domain = domain_from_bundle_id(installed.bundle_id)
        candidates.append((f"https://{domain}" if domain else None, SRC_BUNDLE_ID))
    candidates.append((kvr_search_url(name or (installed.name if installed else None),
                                      vendor_name), SRC_SEARCH))
    for url, source in candidates:
        safe = safe_http_url(url)
        if safe:
            homepage = _link(safe, source)
            break

    manual = _link(safe_http_url(kb_plugin.manual_url) if kb_plugin else None, SRC_KB_PLUGIN)
    support = _link(safe_http_url(kb_vendor.support_url) if kb_vendor else None, SRC_KB_VENDOR)
    return {"homepage": homepage, "manual": manual, "support": support}
