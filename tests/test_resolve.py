from __future__ import annotations

from helpers_report import CID, inst, make_kb, ref
from rackcheck_engine import resolve as R
from rackcheck_engine.model import Confidence, PluginFormat


def test_normalize_name():
    assert R.normalize_name("VST3: Serum (x64)") == "serum"
    assert R.normalize_name("Serum_x64 v1.2.3") == "serum"
    assert R.normalize_name("Pro-Q 4") == "proq 4"  # product numbers are kept
    assert R.normalize_name("Kontakt Stereo") == "kontakt"
    assert R.normalize_name(None) == ""


def test_vst2_id_to_int():
    assert R.vst2_id_to_int("XfsX") == int.from_bytes(b"XfsX", "big")
    assert R.vst2_id_to_int(123) == 123
    assert R.vst2_id_to_int("123") == 123
    assert R.vst2_id_to_int("toolong") is None


def _res(r, inventory, kb=None):
    return R.Resolver(inventory, kb).resolve(r)


def test_match_vst3_cid_same_format():
    res = _res(ref(name="Different Name", vst3_cid=CID.lower()),
               [inst(name="Serum", vst3_cid=CID)], make_kb())
    assert res.state == R.INSTALLED_SAME
    assert res.matched_by == "vst3_cid"
    assert res.confidence == Confidence.CONFIRMED
    assert res.kb_plugin.id == "xfer-serum" and res.kb_matched_by == "vst3_cid"


def test_match_vst2_id():
    vid = int.from_bytes(b"XfsX", "big")
    res = _res(ref(fmt=PluginFormat.VST2, name="x", vendor=None, vst2_unique_id=vid),
               [inst(fmt=PluginFormat.VST2, name="Serum", vst2_unique_id=vid)], make_kb())
    assert res.state == R.INSTALLED_SAME and res.matched_by == "vst2_unique_id"
    assert res.kb_matched_by == "vst2_unique_id"  # KB stores the 4-char form


def test_match_au_codes():
    codes = {"au_type": "aumu", "au_subtype": "XfsX", "au_manufacturer": "XFER"}
    res = _res(ref(fmt=PluginFormat.AU, name="zzz", **codes),
               [inst(fmt=PluginFormat.AU, name="Serum AU", **codes)], make_kb())
    assert res.state == R.INSTALLED_SAME and res.matched_by == "au_codes"


def test_match_clap_id():
    res = _res(ref(fmt=PluginFormat.CLAP, name="zzz", clap_id="com.xfer.serum"),
               [inst(fmt=PluginFormat.CLAP, name="S", clap_id="com.xfer.serum")], None)
    assert res.state == R.INSTALLED_SAME and res.matched_by == "clap_id"


def test_match_aax_ids():
    ids = {"manufacturer": "Xfer", "product": "S"}
    res = _res(ref(fmt=PluginFormat.AAX, name="zzz", aax_ids=ids),
               [inst(fmt=PluginFormat.AAX, name="S", aax_ids=dict(ids))], None)
    assert res.state == R.INSTALLED_SAME and res.matched_by == "aax_ids"


def test_match_file_hint_is_probable():
    res = _res(ref(fmt=PluginFormat.VST2, name="Nexus", vendor=None, file_hint="Nexus.dll"),
               [inst(fmt=PluginFormat.VST2, name="Other", vendor=None, path="C:/v/nexus.dll")])
    assert res.matched_by == "file_hint" and res.confidence == Confidence.PROBABLE


def test_cross_format_by_kb_alias_keys():
    # Project uses VST2 Serum (id known to the KB); the user only has the VST3.
    vid = int.from_bytes(b"XfsX", "big")
    res = _res(ref(fmt=PluginFormat.VST2, name="Serum", vst2_unique_id=vid),
               [inst(fmt=PluginFormat.VST3, name="Serum", vst3_cid=CID)], make_kb())
    assert res.state == R.INSTALLED_OTHER
    assert res.matched_by == "kb_alias:vst3_cid"
    assert res.other_formats_installed == ["vst3"]


def test_cross_format_by_name_and_vendor_is_probable():
    res = _res(ref(fmt=PluginFormat.VST2, name="Serum (x64)", vendor="Xfer"),
               [inst(fmt=PluginFormat.VST3, name="Serum", vendor="Xfer Records")],
               make_kb())  # KB alias links "Xfer" to "Xfer Records"
    assert res.state == R.INSTALLED_OTHER
    assert res.matched_by == "name_and_vendor" and res.confidence == Confidence.PROBABLE


def test_same_format_preferred_and_other_formats_listed():
    res = _res(ref(name="Serum"),
               [inst(fmt=PluginFormat.VST2, name="Serum", path="a"),
                inst(fmt=PluginFormat.VST3, name="Serum", path="b")], None)
    assert res.state == R.INSTALLED_SAME and res.installed.path == "b"
    assert res.other_formats_installed == ["vst2"]


def test_name_only_is_heuristic_and_needs_unambiguous():
    res = _res(ref(name="Serum", vendor=None), [inst(name="Serum", vendor="Xfer Records")])
    assert res.matched_by == "name_only" and res.confidence == Confidence.HEURISTIC
    amb = _res(ref(name="Serum", vendor=None),
               [inst(name="Serum", vendor="A"), inst(name="Serum", vendor="B", path="z")])
    assert amb.state == R.NOT_INSTALLED


def test_different_vendor_same_name_is_not_a_match():
    res = _res(ref(name="Serum", vendor="Xfer Records"), [inst(name="Serum", vendor="Other Co")])
    assert res.state == R.NOT_INSTALLED and res.installed is None


def test_vendor_alias_and_suffix_normalisation():
    res = _res(ref(name="Serum", vendor="Xfer"), [inst(name="Serum", vendor="XFER RECORDS")],
               make_kb())
    assert res.matched_by == "name_and_vendor"


def test_ref_confidence_caps_match_confidence():
    res = _res(ref(conf=Confidence.HEURISTIC, vst3_cid=CID), [inst(vst3_cid=CID)])
    assert res.confidence == Confidence.HEURISTIC


def test_kb_name_and_vendor_and_no_claim_when_unknown():
    kb = make_kb()
    rec, method, conf = R.Resolver(None, kb).match_kb(ref().identity, "Serum", "Xfer")
    assert rec.id == "xfer-serum" and method == "name_and_vendor"
    assert conf == Confidence.PROBABLE
    rec, method, _ = R.Resolver(None, kb).match_kb(ref().identity, "Nothing", "Xfer")
    assert rec is None and method is None


def test_states_stock_notinstalled_unknown_and_unchecked():
    assert _res(ref(fmt=PluginFormat.STOCK, name="EQ Eight", vendor=None), []).state == R.STOCK
    assert _res(ref(fmt=PluginFormat.JS, name="ReaEQ"), []).state == R.STOCK
    assert _res(ref(name="Nope"), []).state == R.NOT_INSTALLED
    assert _res(ref(name=None, vendor=None), []).state == R.UNKNOWN
    unchecked = _res(ref(name="Serum"), None, make_kb())
    assert unchecked.state == R.NOT_CHECKED and unchecked.installed is None
