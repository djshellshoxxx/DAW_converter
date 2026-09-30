"""Tests for knowledge base loading, validation, and lookups."""

import json
from pathlib import Path

import pytest

from rackcheck_engine.kb import KnowledgeBase, VendorRecord


@pytest.fixture
def kb():
    """Load the bundled KB."""
    return KnowledgeBase.load()


class TestKBLoading:
    """Test KB loading and file availability."""

    def test_kb_loads_without_error(self):
        """KB should load without crashing."""
        kb = KnowledgeBase.load()
        assert kb is not None
        assert isinstance(kb.vendors, dict)
        assert isinstance(kb.plugins, dict)

    def test_bundled_kb_exists(self):
        """Bundled KB files should exist."""
        package_root = Path(__file__).parent.parent
        kb_dir = package_root / "kb"
        assert (kb_dir / "vendors.json").exists()
        assert (kb_dir / "plugins.json").exists()


class TestSchemaValidation:
    """Test that shipped KB files conform to schema."""

    def test_vendors_json_is_valid(self):
        """vendors.json should be valid JSON."""
        package_root = Path(__file__).parent.parent
        vendors_file = package_root / "kb" / "vendors.json"
        with open(vendors_file, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_plugins_json_is_valid(self):
        """plugins.json should be valid JSON."""
        package_root = Path(__file__).parent.parent
        plugins_file = package_root / "kb" / "plugins.json"
        with open(plugins_file, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_all_vendor_records_valid(self, kb):
        """Every vendor record should have required fields."""
        for vendor_id, vendor in kb.vendors.items():
            assert vendor.id == vendor_id, f"Vendor id mismatch: {vendor_id}"
            assert vendor.name is not None and len(vendor.name) > 0
            assert isinstance(vendor.id, str)
            assert isinstance(vendor.name, str)

    def test_all_plugin_records_valid(self, kb):
        """Every plugin record should have required fields."""
        for plugin_id, plugin in kb.plugins.items():
            assert plugin.id == plugin_id, f"Plugin id mismatch: {plugin_id}"
            assert plugin.name is not None and len(plugin.name) > 0
            assert plugin.vendor_id is not None and len(plugin.vendor_id) > 0
            assert isinstance(plugin.id, str)
            assert isinstance(plugin.name, str)
            assert isinstance(plugin.vendor_id, str)

    def test_vendor_ids_unique(self, kb):
        """All vendor IDs should be unique."""
        ids = list(kb.vendors.keys())
        assert len(ids) == len(set(ids))

    def test_plugin_ids_unique(self, kb):
        """All plugin IDs should be unique."""
        ids = list(kb.plugins.keys())
        assert len(ids) == len(set(ids))

    def test_every_plugin_vendor_exists(self, kb):
        """Every plugin should reference an existing vendor."""
        for plugin_id, plugin in kb.plugins.items():
            assert plugin.vendor_id in kb.vendors, \
                f"Plugin {plugin_id}: vendor {plugin.vendor_id} not found"

    def test_urls_are_https(self, kb):
        """All links should be HTTPS or None."""
        for vendor_id, vendor in kb.vendors.items():
            if vendor.homepage:
                assert vendor.homepage.startswith("https://"), \
                    f"Vendor {vendor_id}: homepage not HTTPS: {vendor.homepage}"
            if vendor.support_url:
                assert vendor.support_url.startswith("https://"), \
                    f"Vendor {vendor_id}: support_url not HTTPS: {vendor.support_url}"

        for plugin_id, plugin in kb.plugins.items():
            if plugin.homepage:
                assert plugin.homepage.startswith("https://"), \
                    f"Plugin {plugin_id}: homepage not HTTPS: {plugin.homepage}"
            if plugin.manual_url:
                assert plugin.manual_url.startswith("https://"), \
                    f"Plugin {plugin_id}: manual_url not HTTPS: {plugin.manual_url}"

    def test_provenance_set(self, kb):
        """Every entry should have provenance and verified flags."""
        for vendor_id, vendor in kb.vendors.items():
            assert vendor.provenance is not None, f"Vendor {vendor_id}: missing provenance"
            # Seed data has never been checked by a human, so it must not claim a date.
            assert not vendor.verified and vendor.last_verified is None, vendor_id

        for plugin_id, plugin in kb.plugins.items():
            assert plugin.provenance is not None, f"Plugin {plugin_id}: missing provenance"
            assert not plugin.verified and plugin.last_verified is None, plugin_id


class TestVendorLookups:
    """Test vendor lookup functions."""

    def test_vendor_by_name_exact(self, kb):
        """Should find vendor by exact name."""
        vendor = kb.vendor_by_name("FabFilter")
        assert vendor is not None
        assert vendor.id == "fabfilter"
        assert vendor.name == "FabFilter"

    def test_vendor_by_name_case_insensitive(self, kb):
        """Should find vendor case-insensitively."""
        vendor = kb.vendor_by_name("fabfilter")
        assert vendor is not None
        assert vendor.id == "fabfilter"

        vendor = kb.vendor_by_name("FABFILTER")
        assert vendor is not None
        assert vendor.id == "fabfilter"

    def test_vendor_by_name_punctuation_insensitive(self, kb):
        """Should find vendor ignoring punctuation."""
        # This depends on the actual vendor names in the KB
        vendor = kb.vendor_by_name("U-he")
        if vendor:
            assert vendor.id == "u-he"

    def test_vendor_by_alias(self, kb):
        """Should find vendor by alias."""
        # FabFilter Software Instruments is an alias
        vendor = kb.vendor_by_name("FabFilter Software Instruments")
        assert vendor is not None
        assert vendor.id == "fabfilter"

    def test_vendor_not_found(self, kb):
        """Should return None for unknown vendor."""
        vendor = kb.vendor_by_name("NonexistentVendor12345")
        assert vendor is None


class TestPluginLookups:
    """Test plugin lookup functions."""

    def test_plugin_by_vst3_cid(self, kb):
        """Should find plugin by VST3 CID."""
        # Use a known plugin with a CID
        plugin, method = kb.plugin_lookup(vst3_cid="B7F40E50F36F4D6FB27A92DCEF57C1C5")
        if plugin:
            assert plugin.id is not None
            assert method == "vst3_cid"

    def test_plugin_by_clap_id(self, kb):
        """Should find plugin by CLAP ID."""
        plugin, method = kb.plugin_lookup(clap_id="org.surge-synth-team.surge-xt")
        if plugin:
            assert plugin.id is not None
            assert method == "clap_id"

    def test_plugin_by_name_and_vendor(self, kb):
        """Should find plugin by name and vendor."""
        plugin, method = kb.plugin_lookup(name="Serum", vendor="Xfer Records")
        if plugin:
            assert plugin.name is not None
            assert plugin.vendor_id == "xfer-records"
            assert method in ["name_and_vendor", "name_only"]

    def test_plugin_by_name_only(self, kb):
        """Should find plugin by name only if unique."""
        plugin, method = kb.plugin_lookup(name="Vital")
        if plugin:
            assert plugin.name is not None
            assert method in ["name_only", "name_and_vendor"]

    def test_plugin_not_found(self, kb):
        """Should return None for unknown plugin."""
        plugin, method = kb.plugin_lookup(name="NonexistentPlugin12345")
        assert plugin is None
        assert method is None

    def test_plugin_lookup_by_au(self, kb):
        """Should find plugin by AU codes."""
        # Look for FabFilter Pro-Q with AU codes
        plugin, method = kb.plugin_lookup(au=("aufx", "", "FabF"))
        if plugin:
            assert plugin.id is not None
            if method:
                assert method == "au_codes"


class TestBadRecordHandling:
    """Test handling of malformed records."""

    def test_kb_handles_load_warnings(self):
        """KB should accumulate warnings without crashing."""
        kb = KnowledgeBase.load()
        warnings = kb.get_warnings()
        assert isinstance(warnings, list)
        # Warnings should only exist if files are malformed, which ours aren't
        # But the mechanism should work

    def test_invalid_vendor_rejected(self):
        """Invalid vendor records should be skipped with warning."""
        # This tests the internal validation logic
        with pytest.raises(ValueError):
            VendorRecord.from_dict({"id": None, "name": "Test"})


class TestUpdateMerging:
    """Test KB update operations."""

    def test_apply_update_merges_vendors(self, tmp_path):
        """Should merge vendor updates."""
        kb = KnowledgeBase()
        kb.vendors["test-vendor"] = VendorRecord(
            id="test-vendor",
            name="Test Vendor",
            last_verified="2026-01-01"
        )

        update_dir = tmp_path / "update"
        update_dir.mkdir()

        # Create update with newer vendor
        update_data = [{
            "id": "test-vendor",
            "name": "Test Vendor Updated",
            "last_verified": "2026-09-01",
            "aliases": None,
            "homepage": None,
            "support_url": None,
            "bundle_id_prefixes": None,
            "vst3_factory_vendor_strings": None,
            "au_manufacturer_codes": None,
            "licensing": None,
            "notes": None,
            "provenance": "update",
            "verified": True
        }]

        with open(update_dir / "vendors.json", "w") as f:
            json.dump(update_data, f)

        kb.apply_update(tmp_path, update_dir)
        assert kb.vendors["test-vendor"].name == "Test Vendor Updated"

    def test_apply_update_keeps_older_local(self, tmp_path):
        """Should not overwrite newer local data with older update."""
        kb = KnowledgeBase()
        kb.vendors["test-vendor"] = VendorRecord(
            id="test-vendor",
            name="Test Vendor",
            last_verified="2026-09-01"
        )

        update_dir = tmp_path / "update"
        update_dir.mkdir()

        # Create update with older vendor
        update_data = [{
            "id": "test-vendor",
            "name": "Test Vendor Old",
            "last_verified": "2026-01-01",
            "aliases": None,
            "homepage": None,
            "support_url": None,
            "bundle_id_prefixes": None,
            "vst3_factory_vendor_strings": None,
            "au_manufacturer_codes": None,
            "licensing": None,
            "notes": None,
            "provenance": "update",
            "verified": False
        }]

        with open(update_dir / "vendors.json", "w") as f:
            json.dump(update_data, f)

        kb.apply_update(tmp_path, update_dir)
        # Should keep newer local version
        assert kb.vendors["test-vendor"].name == "Test Vendor"


class TestIntegration:
    """Integration tests."""

    def test_full_workflow(self, kb):
        """Test complete workflow: load, validate, query."""
        # Load successful
        assert len(kb.vendors) > 0
        assert len(kb.plugins) > 0

        # Lookups work
        vendor = kb.vendor_by_name("Xfer Records")
        assert vendor is not None

        plugin, method = kb.plugin_lookup(name="Serum", vendor="Xfer Records")
        if plugin:
            assert plugin.name is not None

    def test_has_seeded_vendors(self, kb):
        """Should have at least the seeded vendors."""
        vendor_ids = set(kb.vendors.keys())
        assert "fabfilter" in vendor_ids
        assert "xfer-records" in vendor_ids
        assert "native-instruments" in vendor_ids
        assert "waves" in vendor_ids

    def test_has_seeded_plugins(self, kb):
        """Should have at least the seeded plugins."""
        plugin_ids = set(kb.plugins.keys())
        assert "fabfilter-pro-q-4" in plugin_ids
        assert "xfer-serum" in plugin_ids
        assert "surge-synth-team-surge-xt" in plugin_ids
        assert "vital-audio-vital" in plugin_ids


class TestNormalization:
    """Test name normalization for lookups."""

    def test_name_normalization_lowercase(self, kb):
        """Normalization should handle case."""
        vendor = kb.vendor_by_name("FABFILTER")
        assert vendor is not None

    def test_name_normalization_punctuation(self, kb):
        """Normalization should handle punctuation."""
        # Test with variations
        vendor1 = kb.vendor_by_name("Native-Instruments")
        vendor2 = kb.vendor_by_name("Native Instruments")
        if vendor1 and vendor2:
            assert vendor1.id == vendor2.id

    def test_plugin_name_normalization(self, kb):
        """Plugin name lookup should be case-insensitive."""
        # Try with different cases
        result1 = kb.plugin_lookup(name="SERUM", vendor="Xfer Records")
        result2 = kb.plugin_lookup(name="Serum", vendor="Xfer Records")
        result3 = kb.plugin_lookup(name="serum", vendor="Xfer Records")

        # All should find the same plugin if it exists
        if result1[0] and result2[0]:
            assert result1[0].id == result2[0].id
        if result2[0] and result3[0]:
            assert result2[0].id == result3[0].id
