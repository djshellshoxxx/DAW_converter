"""Plugin identity resolution (SPEC-02 section 5).

Matches each :class:`PluginRef` from a project to installed plugins and to Knowledge
Base entries. Strongest key first (exact identity keys), then normalized name + vendor,
across formats. Every match records how it was made and how much to trust it; when a
match cannot be justified the plugin is left unresolved (SPEC-01 P4).
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .inventory.scan import InstalledPlugin
from .kb import KnowledgeBase, PluginRecord, VendorRecord
from .model import Confidence, PluginFormat, PluginIdentity, PluginRef

# Resolution states (report JSON `resolution.state`).
INSTALLED_SAME = "installed_same_format"
INSTALLED_OTHER = "installed_other_format"
NOT_INSTALLED = "not_installed"
STOCK = "stock"
UNKNOWN = "unknown"  # nothing usable to identify the plugin with
NOT_CHECKED = "inventory_unavailable"  # no installed-plugin inventory was provided

_STOCK_FORMATS = (PluginFormat.STOCK, PluginFormat.JS)
_CONF_ORDER = {Confidence.HEURISTIC: 0, Confidence.PROBABLE: 1, Confidence.CONFIRMED: 2}

_NOISE_TOKENS = {"x64", "x86", "64bit", "32bit", "vst", "vst3", "vsti", "au", "aax", "clap",
                 "stereo", "mono", "64", "32"}
_VENDOR_SUFFIXES = {"inc", "llc", "ltd", "gmbh", "co", "corp", "corporation", "limited", "ag",
                    "sa", "srl", "software", "audio", "plugins", "plugin"}
_VERSION_RE = re.compile(r"\bv\d+(\.\d+)*\b|\b\d+\.\d+(\.\d+)*\b")
_PAREN_NOISE_RE = re.compile(r"\((?:x64|x86|64-?bit|32-?bit|stereo|mono|vst3?|au|clap|aax)\)", re.I)
_PREFIX_RE = re.compile(r"^(?:vst3i?|vsti?|au|clap|aax|js)\s*:\s*", re.I)


def normalize_name(name: str | None) -> str:
    """Lowercase, strip accents, format/arch/channel noise and dotted version suffixes.

    Numbers that are part of a product name ("Pro-Q 4") are kept on purpose.
    """
    if not name:
        return ""
    s = _PREFIX_RE.sub("", name.strip())
    s = _PAREN_NOISE_RE.sub(" ", s)
    s = s.lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = s.replace("_", " ")
    s = _VERSION_RE.sub(" ", s)
    s = re.sub(r"[^a-z0-9\s]", "", s)
    tokens = [t for t in s.split() if t not in _NOISE_TOKENS]
    return " ".join(tokens)


def _strip_vendor_suffixes(norm: str) -> str:
    tokens = norm.split()
    while len(tokens) > 1 and tokens[-1] in _VENDOR_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def vst2_id_to_int(value: Any) -> int | None:
    """Accept an int, a decimal string or a 4-char ASCII id."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if len(value) == 4:
            try:
                return int.from_bytes(value.encode("ascii"), "big")
            except UnicodeEncodeError:
                return None
        if value.isdigit():
            return int(value)
    return None


def _key_tuples(identity: PluginIdentity) -> list[tuple[str, Any]]:
    """Identity keys of one plugin as comparable ``(kind, value)`` tuples."""
    keys: list[tuple[str, Any]] = []
    if identity.vst3_cid:
        keys.append(("vst3_cid", identity.vst3_cid.upper()))
    if identity.vst2_unique_id:
        keys.append(("vst2_unique_id", identity.vst2_unique_id))
    if identity.au_type and identity.au_subtype and identity.au_manufacturer:
        keys.append(("au_codes", (identity.au_type, identity.au_subtype, identity.au_manufacturer)))
    if identity.clap_id:
        keys.append(("clap_id", identity.clap_id))
    if identity.aax_ids:
        keys.append(("aax_ids", tuple(sorted(
            (str(k), str(v)) for k, v in identity.aax_ids.items()))))
    return keys


def _kb_key_tuples(plugin: PluginRecord) -> list[tuple[str, Any]]:
    keys: list[tuple[str, Any]] = []
    for cid in plugin.keys.vst3_cid:
        keys.append(("vst3_cid", str(cid).upper()))
    for v in plugin.keys.vst2_unique_id:
        n = vst2_id_to_int(v)
        if n:
            keys.append(("vst2_unique_id", n))
    for au in plugin.keys.au:
        t, s, m = au.get("type"), au.get("subtype"), au.get("manufacturer")
        if t and s and m:
            keys.append(("au_codes", (t, s, m)))
    for cid in plugin.keys.clap_id:
        keys.append(("clap_id", cid))
    for aax in plugin.keys.aax:
        if aax:
            keys.append(("aax_ids", tuple(sorted((str(k), str(v)) for k, v in aax.items()))))
    return keys


def _min_conf(a: Confidence, b: Confidence) -> Confidence:
    return a if _CONF_ORDER[a] <= _CONF_ORDER[b] else b


def _conf(value: str | Confidence) -> Confidence:
    try:
        return Confidence(value)
    except ValueError:
        return Confidence.HEURISTIC


@dataclass
class Resolution:
    state: str
    matched_by: str | None = None
    confidence: Confidence | None = None
    installed: InstalledPlugin | None = None
    other_formats_installed: list[str] = field(default_factory=list)
    kb_plugin: PluginRecord | None = None
    kb_matched_by: str | None = None
    kb_confidence: Confidence | None = None
    vendor: VendorRecord | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class _Match:
    plugin: InstalledPlugin
    method: str
    confidence: Confidence
    rank: int  # lower is stronger


class Resolver:
    """Builds lookup indexes once, then resolves any number of plugin references."""

    def __init__(self, inventory: list[InstalledPlugin] | None, kb: KnowledgeBase | None):
        self.inventory = inventory
        self.kb = kb
        self._inst_by_key: dict[tuple[str, Any], list[InstalledPlugin]] = {}
        self._inst_by_name: dict[str, list[InstalledPlugin]] = {}
        for inst in inventory or []:
            for key in _key_tuples(inst.identity):
                self._inst_by_key.setdefault(key, []).append(inst)
            n = normalize_name(inst.name)
            if n:
                self._inst_by_name.setdefault(n, []).append(inst)
        self._kb_by_key: dict[tuple[str, Any], PluginRecord] = {}
        self._kb_by_vendor_name: dict[tuple[str, str], list[PluginRecord]] = {}
        self._kb_by_name: dict[str, list[PluginRecord]] = {}
        if kb is not None:
            for rec in kb.plugins.values():
                for key in _kb_key_tuples(rec):
                    self._kb_by_key.setdefault(key, rec)
                n = normalize_name(rec.name)
                if n:
                    self._kb_by_vendor_name.setdefault((rec.vendor_id, n), []).append(rec)
                    self._kb_by_name.setdefault(n, []).append(rec)

    # -- vendors -------------------------------------------------------------------

    def vendor_id(self, name: str | None) -> str | None:
        """Canonical vendor id (KB id when known, else a normalized string)."""
        if not name:
            return None
        if self.kb is not None:
            rec = self.kb.vendor_by_name(name)
            if rec is not None:
                return rec.id
        n = _strip_vendor_suffixes(normalize_name(name))
        return n or None

    # -- KB ------------------------------------------------------------------------

    def match_kb(
        self, identity: PluginIdentity, name: str | None, vendor: str | None
    ) -> tuple[PluginRecord | None, str | None, Confidence | None]:
        if self.kb is None:
            return None, None, None
        for kind, value in _key_tuples(identity):
            rec = self._kb_by_key.get((kind, value))
            if rec is not None:
                return rec, kind, Confidence.CONFIRMED
        n = normalize_name(name)
        if not n:
            return None, None, None
        vid = self.vendor_id(vendor)
        if vid:
            cands = self._kb_by_vendor_name.get((vid, n), [])
            if len(cands) == 1:
                return cands[0], "name_and_vendor", Confidence.PROBABLE
            return None, None, None
        # No vendor known: accept only an unambiguous name (weak).
        cands = self._kb_by_name.get(n, [])
        if len(cands) == 1:
            return cands[0], "name_only", Confidence.HEURISTIC
        return None, None, None

    # -- installed -----------------------------------------------------------------

    def _installed_matches(
        self,
        ref: PluginRef,
        kb_plugin: PluginRecord | None,
        kb_conf: Confidence | None,
    ) -> list[_Match]:
        found: dict[int, _Match] = {}

        def add(inst: InstalledPlugin, method: str, conf: Confidence, rank: int) -> None:
            cur = found.get(id(inst))
            if cur is None or rank < cur.rank:
                found[id(inst)] = _Match(inst, method, conf, rank)

        ref_conf = ref.confidence
        # 1. exact key, same format (keys are format specific, so the format is implied)
        for kind, value in _key_tuples(ref.identity):
            for inst in self._inst_by_key.get((kind, value), []):
                add(inst, kind, _min_conf(Confidence.CONFIRMED, ref_conf), 0)
        # 1b. file hint equals the installed file name, same format
        hint = ref.identity.file_hint
        if hint:
            hint_name = os.path.basename(hint.replace("\\", "/")).lower()
            for inst in self.inventory or []:
                if inst.format == ref.format and hint_name and (
                    os.path.basename(inst.path.replace("\\", "/")).lower() == hint_name
                ):
                    add(inst, "file_hint", _min_conf(Confidence.PROBABLE, ref_conf), 1)
        # 2. via the KB entry: installed plugin whose own keys belong to the same KB plugin
        if kb_plugin is not None and kb_conf is not None:
            for kind, value in _kb_key_tuples(kb_plugin):
                for inst in self._inst_by_key.get((kind, value), []):
                    add(inst, "kb_alias:" + kind, _min_conf(kb_conf, ref_conf), 2)
        # 3. normalized name + vendor
        n = normalize_name(ref.name)
        vid = self.vendor_id(ref.vendor)
        if n:
            cands = self._inst_by_name.get(n, [])
            if vid:
                with_vendor = [c for c in cands if self.vendor_id(c.vendor) == vid]
                for inst in with_vendor:
                    add(inst, "name_and_vendor", _min_conf(Confidence.PROBABLE, ref_conf), 3)
                # Vendor unknown on the installed side (e.g. VST2 by filename): weak name match
                if not with_vendor:
                    unvendored = [c for c in cands if not c.vendor]
                    if unvendored and len({c.name for c in unvendored}) == 1:
                        for inst in unvendored:
                            add(inst, "name_only", Confidence.HEURISTIC, 4)
            else:
                vendors = {self.vendor_id(c.vendor) for c in cands}
                if cands and len(vendors) == 1:  # unambiguous across vendors
                    for inst in cands:
                        add(inst, "name_only", Confidence.HEURISTIC, 4)
        return sorted(found.values(), key=lambda m: m.rank)

    # -- main ----------------------------------------------------------------------

    def resolve(self, ref: PluginRef) -> Resolution:
        kb_plugin, kb_method, kb_conf = self.match_kb(ref.identity, ref.name, ref.vendor)
        matches: list[_Match] = []
        if ref.format not in _STOCK_FORMATS and self.inventory is not None:
            matches = self._installed_matches(ref, kb_plugin, kb_conf)
            if kb_plugin is None and matches:
                # Learn the KB entry from the installed copy (it may carry stronger keys).
                inst = matches[0].plugin
                kb_plugin, kb_method, kb_conf = self.match_kb(inst.identity, inst.name, inst.vendor)
        vendor_rec = None
        if self.kb is not None:
            if kb_plugin is not None:
                vendor_rec = self.kb.vendors.get(kb_plugin.vendor_id)
            if vendor_rec is None:
                vname = ref.vendor or (matches[0].plugin.vendor if matches else None)
                if vname:
                    vendor_rec = self.kb.vendor_by_name(vname)

        res = Resolution(
            state=UNKNOWN,
            kb_plugin=kb_plugin,
            kb_matched_by=kb_method,
            kb_confidence=kb_conf,
            vendor=vendor_rec,
        )
        if ref.format in _STOCK_FORMATS:
            res.state = STOCK
            return res
        if self.inventory is None:
            res.state = NOT_CHECKED
            return res
        if matches:
            same = [m for m in matches if m.plugin.format == ref.format]
            same_ok = bool(same) or ref.format == PluginFormat.UNKNOWN
            primary = min(
                same or matches, key=lambda m: (m.rank, -_CONF_ORDER[m.confidence])
            )
            res.state = INSTALLED_SAME if same_ok else INSTALLED_OTHER
            res.installed = primary.plugin
            res.matched_by = primary.method
            res.confidence = primary.confidence
            fmts = {m.plugin.format.value for m in matches if m.plugin.format != ref.format}
            res.other_formats_installed = sorted(fmts)
            return res
        if not ref.name and not _key_tuples(ref.identity):
            res.state = UNKNOWN
            return res
        res.state = NOT_INSTALLED
        return res


def resolve_plugins(
    refs: list[PluginRef], inventory: list[InstalledPlugin] | None, kb: KnowledgeBase | None
) -> list[Resolution]:
    resolver = Resolver(inventory, kb)
    return [resolver.resolve(r) for r in refs]
