"""Knowledge Base loader and operations for plugin/vendor data."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class VendorRecord:
    """Vendor entry from KB."""
    id: str
    name: str
    aliases: list[str] | None = None
    homepage: str | None = None
    support_url: str | None = None
    bundle_id_prefixes: list[str] | None = None
    vst3_factory_vendor_strings: list[str] | None = None
    au_manufacturer_codes: list[str] | None = None
    licensing: list[str] | None = None
    notes: str | None = None
    last_verified: str | None = None
    provenance: str | None = None
    verified: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VendorRecord:
        """Create from dictionary, validating required fields."""
        if not data.get("id") or not data.get("name"):
            raise ValueError("Vendor must have id and name")
        return cls(
            id=data["id"],
            name=data["name"],
            aliases=data.get("aliases"),
            homepage=data.get("homepage"),
            support_url=data.get("support_url"),
            bundle_id_prefixes=data.get("bundle_id_prefixes"),
            vst3_factory_vendor_strings=data.get("vst3_factory_vendor_strings"),
            au_manufacturer_codes=data.get("au_manufacturer_codes"),
            licensing=data.get("licensing"),
            notes=data.get("notes"),
            last_verified=data.get("last_verified"),
            provenance=data.get("provenance"),
            verified=data.get("verified", False),
        )


@dataclass
class PluginIdentityKeys:
    """Plugin identity keys across formats."""
    vst3_cid: list[str] = field(default_factory=list)
    vst2_unique_id: list[int | str] = field(default_factory=list)
    au: list[dict[str, str]] = field(default_factory=list)
    clap_id: list[str] = field(default_factory=list)
    aax: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginIdentityKeys:
        """Create from dictionary."""
        return cls(
            vst3_cid=data.get("vst3_cid", []) or [],
            vst2_unique_id=data.get("vst2_unique_id", []) or [],
            au=data.get("au", []) or [],
            clap_id=data.get("clap_id", []) or [],
            aax=data.get("aax", []) or [],
        )


@dataclass
class PluginRecord:
    """Plugin entry from KB."""
    id: str
    vendor_id: str
    name: str
    keys: PluginIdentityKeys = field(default_factory=PluginIdentityKeys)
    homepage: str | None = None
    manual_url: str | None = None
    category: str | None = None
    formats: list[str] | None = None
    platforms: list[str] | None = None
    apple_silicon_native: bool = False
    price_model: str | None = None
    licensing: list[str] | None = None
    status: str | None = None
    successor_id: str | None = None
    free_alternatives: list[str] | None = None
    last_verified: str | None = None
    provenance: str | None = None
    verified: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginRecord:
        """Create from dictionary, validating required fields."""
        if not data.get("id") or not data.get("vendor_id") or not data.get("name"):
            raise ValueError("Plugin must have id, vendor_id, and name")
        keys_data = data.get("keys", {})
        return cls(
            id=data["id"],
            vendor_id=data["vendor_id"],
            name=data["name"],
            keys=PluginIdentityKeys.from_dict(keys_data),
            homepage=data.get("homepage"),
            manual_url=data.get("manual_url"),
            category=data.get("category"),
            formats=data.get("formats"),
            platforms=data.get("platforms"),
            apple_silicon_native=data.get("apple_silicon_native", False),
            price_model=data.get("price_model"),
            licensing=data.get("licensing"),
            status=data.get("status"),
            successor_id=data.get("successor_id"),
            free_alternatives=data.get("free_alternatives"),
            last_verified=data.get("last_verified"),
            provenance=data.get("provenance"),
            verified=data.get("verified", False),
        )


class KnowledgeBase:
    """Knowledge Base loader and query interface."""

    def __init__(self) -> None:
        """Initialize empty KB."""
        self.vendors: dict[str, VendorRecord] = {}
        self.plugins: dict[str, PluginRecord] = {}
        self.version: str | None = None
        self.schema_version: str | None = None
        self._vendor_by_name_cache: dict[str, str] = {}
        self._vendor_by_au_code_cache: dict[str, str] = {}
        self._plugins_by_vst3_cid: dict[str, str] = {}
        self._plugins_by_clap_id: dict[str, str] = {}
        self._load_warnings: list[str] = []

    @staticmethod
    def load(path: str | Path | None = None) -> KnowledgeBase:
        """Load KB from a directory containing vendors.json and plugins.json.

        Args:
            path: Path to KB directory. If None, uses bundled kb/ relative to package root.

        Returns:
            Loaded KnowledgeBase instance.
        """
        kb = KnowledgeBase()
        if path is None:
            # Use bundled KB relative to package root
            package_root = Path(__file__).parent.parent.parent.parent
            path = package_root / "kb"
        else:
            path = Path(path)

        vendors_file = path / "vendors.json"
        plugins_file = path / "plugins.json"

        if vendors_file.exists():
            kb._load_vendors(vendors_file)
        if plugins_file.exists():
            kb._load_plugins(plugins_file)

        return kb

    def _load_vendors(self, path: Path) -> None:
        """Load vendors from JSON file."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            self._load_warnings.append(f"Failed to load vendors.json: {e}")
            return

        if not isinstance(data, list):
            self._load_warnings.append("vendors.json root must be an array")
            return

        vendor_ids = set()
        for item in data:
            if not isinstance(item, dict):
                self._load_warnings.append("Vendor entry is not a dict")
                continue
            try:
                vendor = VendorRecord.from_dict(item)
                if vendor.id in vendor_ids:
                    self._load_warnings.append(f"Duplicate vendor id: {vendor.id}")
                    continue
                self.vendors[vendor.id] = vendor
                vendor_ids.add(vendor.id)
                self._update_vendor_caches(vendor)
            except ValueError as e:
                self._load_warnings.append(f"Invalid vendor record: {e}")

    def _load_plugins(self, path: Path) -> None:
        """Load plugins from JSON file."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            self._load_warnings.append(f"Failed to load plugins.json: {e}")
            return

        if not isinstance(data, list):
            self._load_warnings.append("plugins.json root must be an array")
            return

        plugin_ids = set()
        vst3_cids = set()
        clap_ids = set()

        for item in data:
            if not isinstance(item, dict):
                self._load_warnings.append("Plugin entry is not a dict")
                continue
            try:
                plugin = PluginRecord.from_dict(item)

                # Validate vendor exists
                if plugin.vendor_id not in self.vendors:
                    self._load_warnings.append(
                        f"Plugin {plugin.id}: vendor_id {plugin.vendor_id} not found"
                    )
                    continue

                if plugin.id in plugin_ids:
                    self._load_warnings.append(f"Duplicate plugin id: {plugin.id}")
                    continue

                self.plugins[plugin.id] = plugin
                plugin_ids.add(plugin.id)

                # Index identity keys
                for cid in plugin.keys.vst3_cid:
                    if cid in vst3_cids:
                        self._load_warnings.append(
                            f"Duplicate VST3 CID {cid} in plugin {plugin.id}"
                        )
                    else:
                        self._plugins_by_vst3_cid[cid] = plugin.id
                        vst3_cids.add(cid)

                for clap_id in plugin.keys.clap_id:
                    if clap_id in clap_ids:
                        self._load_warnings.append(
                            f"Duplicate CLAP id {clap_id} in plugin {plugin.id}"
                        )
                    else:
                        self._plugins_by_clap_id[clap_id] = plugin.id
                        clap_ids.add(clap_id)

            except ValueError as e:
                self._load_warnings.append(f"Invalid plugin record: {e}")

    def _update_vendor_caches(self, vendor: VendorRecord) -> None:
        """Update vendor lookup caches."""
        # Normalize and add vendor name
        norm_name = self._normalize_name(vendor.name)
        if norm_name not in self._vendor_by_name_cache:
            self._vendor_by_name_cache[norm_name] = vendor.id

        # Add aliases
        if vendor.aliases:
            for alias in vendor.aliases:
                norm_alias = self._normalize_name(alias)
                if norm_alias not in self._vendor_by_name_cache:
                    self._vendor_by_name_cache[norm_alias] = vendor.id

        # Index AU manufacturer codes
        if vendor.au_manufacturer_codes:
            for code in vendor.au_manufacturer_codes:
                if code not in self._vendor_by_au_code_cache:
                    self._vendor_by_au_code_cache[code] = vendor.id

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize name for case-insensitive, punctuation-insensitive matching."""
        # Convert to lowercase
        s = name.lower()
        # Remove accents
        s = "".join(
            c for c in unicodedata.normalize("NFD", s)
            if unicodedata.category(c) != "Mn"
        )
        # Remove punctuation and extra spaces
        s = re.sub(r"[^a-z0-9\s]", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def vendor_by_name(self, name: str) -> VendorRecord | None:
        """Look up vendor by name, case and punctuation insensitive.

        Args:
            name: Vendor name or alias.

        Returns:
            VendorRecord if found, None otherwise.
        """
        norm_name = self._normalize_name(name)
        vendor_id = self._vendor_by_name_cache.get(norm_name)
        if vendor_id:
            return self.vendors.get(vendor_id)
        return None

    def plugin_lookup(
        self,
        name: str | None = None,
        vendor: str | None = None,
        vst3_cid: str | None = None,
        vst2_id: int | str | None = None,
        au: tuple[str, str, str] | None = None,
        clap_id: str | None = None,
        bundle_id: str | None = None,
    ) -> tuple[PluginRecord | None, str | None]:
        """Look up plugin by various identifiers.

        Returns:
            Tuple of (PluginRecord or None, match_method string or None)
            match_method describes how it was matched (e.g., "vst3_cid", "name_and_vendor")
        """
        # Try exact identity matches first
        if vst3_cid:
            vst3_cid_upper = vst3_cid.upper()
            plugin_id = self._plugins_by_vst3_cid.get(vst3_cid_upper)
            if plugin_id:
                plugin = self.plugins.get(plugin_id)
                if plugin:
                    return plugin, "vst3_cid"

        if clap_id:
            plugin_id = self._plugins_by_clap_id.get(clap_id)
            if plugin_id:
                plugin = self.plugins.get(plugin_id)
                if plugin:
                    return plugin, "clap_id"

        # Try AU lookup
        if au:
            au_type, au_subtype, au_manufacturer = au
            for plugin in self.plugins.values():
                for au_key in plugin.keys.au:
                    if (au_key.get("type") == au_type and
                        au_key.get("subtype") == au_subtype and
                        au_key.get("manufacturer") == au_manufacturer):
                        return plugin, "au_codes"

        # Try name + vendor lookup
        if name and vendor:
            vendor_rec = self.vendor_by_name(vendor)
            if vendor_rec:
                norm_name = self._normalize_name(name)
                for plugin in self.plugins.values():
                    if (plugin.vendor_id == vendor_rec.id and
                        self._normalize_name(plugin.name) == norm_name):
                        return plugin, "name_and_vendor"

        # Fallback: name-only lookup across vendors
        if name:
            norm_name = self._normalize_name(name)
            matches = []
            for plugin in self.plugins.values():
                if self._normalize_name(plugin.name) == norm_name:
                    matches.append(plugin)
            if len(matches) == 1:
                return matches[0], "name_only"
            elif len(matches) > 1:
                # Multiple matches: if vendor specified, filter
                if vendor:
                    vendor_rec = self.vendor_by_name(vendor)
                    if vendor_rec:
                        filtered = [p for p in matches if p.vendor_id == vendor_rec.id]
                        if len(filtered) == 1:
                            return filtered[0], "name_and_vendor"
                # Return first match as best guess
                if matches:
                    return matches[0], "name_ambiguous"

        return None, None

    def apply_update(self, local_bundle_dir: str | Path, update_dir: str | Path) -> None:
        """Apply an update bundle, merging vendors and plugins with override semantics.

        Updates in update_dir override/extend the local bundle.
        Newer entries (by last_verified date) take precedence.

        Args:
            local_bundle_dir: Path to current bundled kb/ directory.
            update_dir: Path to update directory (with vendors.json and/or plugins.json).
        """
        local_bundle_dir = Path(local_bundle_dir)
        update_dir = Path(update_dir)

        # Load update data
        update_vendors = self._load_json_safe(update_dir / "vendors.json") or []
        update_plugins = self._load_json_safe(update_dir / "plugins.json") or []

        # Merge vendors (update overrides if same id or if newer)
        for item in update_vendors:
            if isinstance(item, dict):
                try:
                    vendor = VendorRecord.from_dict(item)
                    if vendor.id in self.vendors:
                        local = self.vendors[vendor.id]
                        # Keep newer based on last_verified
                        if self._is_newer(vendor.last_verified, local.last_verified):
                            self.vendors[vendor.id] = vendor
                    else:
                        self.vendors[vendor.id] = vendor
                    self._update_vendor_caches(vendor)
                except ValueError:
                    self._load_warnings.append(f"Invalid vendor in update: {item}")

        # Merge plugins (similar logic)
        for item in update_plugins:
            if isinstance(item, dict):
                try:
                    plugin = PluginRecord.from_dict(item)
                    if plugin.id in self.plugins:
                        local = self.plugins[plugin.id]
                        # Keep newer based on last_verified
                        if self._is_newer(plugin.last_verified, local.last_verified):
                            self.plugins[plugin.id] = plugin
                    else:
                        self.plugins[plugin.id] = plugin
                except ValueError:
                    self._load_warnings.append(f"Invalid plugin in update: {item}")

    @staticmethod
    def _load_json_safe(path: Path) -> list[Any] | None:
        """Safely load JSON file, returning None on error."""
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else None
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _is_newer(date1: str | None, date2: str | None) -> bool:
        """Compare ISO date strings. Returns True if date1 > date2."""
        if date1 is None:
            return False
        if date2 is None:
            return True
        return date1 > date2

    def get_warnings(self) -> list[str]:
        """Return accumulated warnings from loading."""
        return self._load_warnings.copy()
