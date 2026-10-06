"""Shared builders for resolver/report/export tests (synthetic data only)."""

from __future__ import annotations

from rackcheck_engine.inventory.scan import InstalledPlugin
from rackcheck_engine.kb import KnowledgeBase, PluginRecord, VendorRecord
from rackcheck_engine.model import (
    Confidence,
    PluginFormat,
    PluginIdentity,
    PluginRef,
    PluginRole,
    ProjectInfo,
    ScanResult,
    SourceInfo,
    TrackRef,
    TrackType,
)

CID = "A1B2C3D4E5F60718293A4B5C6D7E8F90"


def ref(pid="p1", name="Serum", vendor="Xfer Records", fmt=PluginFormat.VST3, track="t1",
        conf=Confidence.CONFIRMED, version=None, bypassed=False, **identity) -> PluginRef:
    return PluginRef(
        id=pid, track_id=track, slot_index=0, role=PluginRole.EFFECT, format=fmt, name=name,
        vendor=vendor, confidence=conf, version_in_project=version, bypassed=bypassed,
        identity=PluginIdentity(**identity),
    )


def inst(name="Serum", vendor="Xfer Records", fmt=PluginFormat.VST3, version="1.0",
         path="C:/VST3/Serum.vst3", archs=None, url=None, bundle_id=None, **identity):
    return InstalledPlugin(
        name=name, vendor=vendor, format=fmt, version=version, path=path,
        identity=PluginIdentity(**identity), url=url, architectures=archs or [],
        bundle_id=bundle_id,
    )


def make_kb(verified=True) -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.version = "test-kb"
    kb.vendors["xfer-records"] = VendorRecord(
        id="xfer-records", name="Xfer Records", aliases=["Xfer"],
        homepage="https://xferrecords.example", support_url="https://xferrecords.example/help",
        bundle_id_prefixes=["com.xferrecords"])
    kb.vendors["fabfilter"] = VendorRecord(
        id="fabfilter", name="FabFilter", homepage="https://fabfilter.example")
    for v in kb.vendors.values():
        kb._update_vendor_caches(v)
    serum = PluginRecord.from_dict({
        "id": "xfer-serum", "vendor_id": "xfer-records", "name": "Serum",
        "keys": {"vst3_cid": [CID], "vst2_unique_id": ["XfsX"],
                 "au": [{"type": "aumu", "subtype": "XfsX", "manufacturer": "XFER"}],
                 "clap_id": ["com.xfer.serum"], "aax": [{"manufacturer": "Xfer", "product": "S"}]},
        "homepage": "https://xferrecords.example/serum", "manual_url": "https://x.example/man",
        "category": "instrument/synth", "formats": ["vst2", "vst3"], "platforms": ["win", "mac"],
        "price_model": "paid", "licensing": ["ilok"], "status": "active",
        "free_alternatives": ["vital"], "last_verified": "2026-09-01", "verified": verified})
    proq = PluginRecord.from_dict({
        "id": "fabfilter-pro-q-4", "vendor_id": "fabfilter", "name": "Pro-Q 4",
        "keys": {}, "homepage": None, "formats": ["vst2"], "platforms": ["mac"],
        "status": "discontinued", "verified": verified})
    for p in (serum, proq):
        kb.plugins[p.id] = p
    return kb


def scan(plugins, tracks=None, media=None, warnings=None, path="C:/proj/Song.rpp",
         fmt="reaper_rpp", sr=48000, tempo=120.0, external_hardware_tracks=None) -> ScanResult:
    return ScanResult(
        source=SourceInfo(path=path, format=fmt, daw_name="REAPER", daw_version="7.22"),
        project=ProjectInfo(tempo_bpm=tempo, time_signature="4/4", sample_rate=sr),
        tracks=tracks if tracks is not None else [
            TrackRef(id="t1", name="Bass", type=TrackType.INSTRUMENT,
                     devices=[p.id for p in plugins])],
        plugins=plugins, media=media or [], warnings=warnings or [],
        external_hardware_tracks=external_hardware_tracks or [],
    )
