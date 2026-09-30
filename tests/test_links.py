from __future__ import annotations

from helpers_report import inst, make_kb
from rackcheck_engine import links as L
from rackcheck_engine.model import PluginFormat


def _chain(**kw):
    base = {"name": "Serum", "vendor_name": "Xfer", "kb_plugin": None, "kb_vendor": None,
            "installed": None}
    base.update(kw)
    return L.resolve_links(**base)


def test_chain_order_kb_plugin_first():
    kb = make_kb()
    out = _chain(kb_plugin=kb.plugins["xfer-serum"], kb_vendor=kb.vendors["xfer-records"],
                 installed=inst(url="https://factory.example", bundle_id="com.xfer.serum"))
    assert out["homepage"] == {"url": "https://xferrecords.example/serum", "source": "kb_plugin"}
    assert out["manual"]["source"] == "kb_plugin"
    assert out["support"] == {"url": "https://xferrecords.example/help", "source": "kb_vendor"}


def test_chain_moduleinfo_before_vendor():
    kb = make_kb()
    out = _chain(kb_vendor=kb.vendors["xfer-records"], installed=inst(url="https://f.example/"))
    assert out["homepage"]["source"] == "moduleinfo"


def test_chain_clap_descriptor_source():
    out = _chain(installed=inst(fmt=PluginFormat.CLAP, url="https://c.example"))
    assert out["homepage"]["source"] == "clap_descriptor"


def test_chain_vendor_before_bundle_id():
    kb = make_kb()
    out = _chain(kb_vendor=kb.vendors["fabfilter"],
                 installed=inst(url=None, bundle_id="com.other.thing"))
    assert out["homepage"] == {"url": "https://fabfilter.example", "source": "kb_vendor"}


def test_chain_bundle_id_marked_heuristic():
    out = _chain(installed=inst(bundle_id="com.fabfilter.Pro-Q.AU"))
    assert out["homepage"] == {"url": "https://fabfilter.com", "source": "bundle_id_heuristic"}


def test_chain_search_last_resort():
    out = _chain(name="Odd Plugin & Co", vendor_name=None)
    assert out["homepage"]["source"] == "search"
    assert out["homepage"]["url"].startswith(L.KVR_SEARCH_URL)
    assert "Odd+Plugin+%26+Co" in out["homepage"]["url"]


def test_no_link_when_nothing_to_search_and_stock_has_none():
    assert _chain(name=None, vendor_name=None)["homepage"] == {"url": None, "source": None}
    assert _chain(is_stock=True)["homepage"]["url"] is None


def test_bad_urls_and_generic_bundle_ids_rejected():
    kb = make_kb()
    kb.plugins["xfer-serum"].homepage = "javascript:alert(1)"
    out = _chain(kb_plugin=kb.plugins["xfer-serum"])
    assert out["homepage"]["source"] == "search"
    assert L.domain_from_bundle_id("com.apple.audio.units") is None
    assert L.domain_from_bundle_id("nonsense") is None
    assert L.domain_from_bundle_id("com.fab.filter") == "fab.com"
    assert L.safe_http_url("ftp://x.example") is None
    assert L.safe_http_url("https://") is None
