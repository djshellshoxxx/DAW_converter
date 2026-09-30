"""Tests for installed plugin inventory scanning."""

import json
import plistlib
from pathlib import Path

from rackcheck_engine.inventory import (
    InstalledPlugin,
    PluginSource,
    default_plugin_dirs,
    load_inventory,
    probe_in_subprocess,
    save_inventory,
    scan_installed,
)
from rackcheck_engine.model import PluginFormat, PluginIdentity


class TestDefaultPluginDirs:
    """Test default_plugin_dirs for Windows and macOS."""

    def test_windows_dirs(self):
        """Test Windows default plugin directories."""
        dirs = default_plugin_dirs("Windows")
        assert PluginFormat.VST3 in dirs
        assert PluginFormat.VST2 in dirs
        assert PluginFormat.CLAP in dirs
        assert PluginFormat.AAX in dirs
        assert PluginFormat.AU not in dirs or len(dirs[PluginFormat.AU]) == 0

        # Verify some paths exist as strings
        vst3_paths = dirs[PluginFormat.VST3]
        assert len(vst3_paths) > 0
        assert all(isinstance(p, Path) for p in vst3_paths)

    def test_macos_dirs(self):
        """Test macOS default plugin directories."""
        dirs = default_plugin_dirs("Darwin")
        assert PluginFormat.VST3 in dirs
        assert PluginFormat.VST2 in dirs
        assert PluginFormat.AU in dirs
        assert PluginFormat.CLAP in dirs
        assert PluginFormat.AAX in dirs

        # Verify at least one path per format
        for fmt in [PluginFormat.VST3, PluginFormat.VST2, PluginFormat.AU]:
            assert len(dirs[fmt]) > 0

    def test_unknown_platform_returns_dict(self):
        """Test that unknown platform returns a dict (possibly empty)."""
        dirs = default_plugin_dirs("Unknown")
        assert isinstance(dirs, dict)


class TestScanVST3:
    """Test VST3 scanning with moduleinfo.json."""

    def test_scan_vst3_with_moduleinfo_json(self, tmp_path):
        """Test scanning VST3 with moduleinfo.json."""
        # Create a fake VST3 bundle
        bundle = tmp_path / "TestPlugin.vst3"
        bundle.mkdir()
        contents = bundle / "Contents" / "Resources"
        contents.mkdir(parents=True)

        # Write with JSON5 features: trailing comma, comments
        moduleinfo_path = contents / "moduleinfo.json"
        # Add JSON5 features to test parser
        content = (
            "{\n"
            '  "Name": "TestPlugin",\n'
            '  "Factory Info": {\n'
            '    "Vendor": "Test Vendor", // Vendor name\n'
            '    "URL": "https://example.com",\n'
            '    "E-Mail": "test@example.com",\n'
            "  },\n"  # trailing comma
            '  "Classes": [\n'
            "    {\n"
            '      "CID": "ABCDEF0123456789ABCDEF0123456789",\n'
            '      "Name": "Test Synth",\n'
            '      "Vendor": "Test Vendor",\n'
            '      "Version": "1.2.3",\n'
            '      "Category": "Audio Module Class",\n'
            '      "Sub Categories": ["Instrument", "Synth",],\n'
            "    },\n"
            "    {\n"
            '      "CID": "11111111111111111111111111111111",\n'
            '      "Name": "Test Synth Controller",\n'
            '      "Category": "Component Controller Class",\n'
            "    },\n"  # trailing comma
            "  ],\n"  # trailing comma
            "}\n"
        )

        # Real moduleinfo.json files are UTF-8, sometimes with a BOM.
        moduleinfo_path.write_text("﻿" + content, encoding="utf-8")

        # Scan the directory
        dirs = {PluginFormat.VST3: [tmp_path]}
        plugins = scan_installed(dirs)

        assert len(plugins) == 1
        plugin = plugins[0]
        assert plugin.name == "Test Synth"
        assert plugin.vendor == "Test Vendor"
        assert plugin.format == PluginFormat.VST3
        assert plugin.version == "1.2.3"
        assert plugin.url == "https://example.com"
        assert plugin.identity.vst3_cid == "ABCDEF0123456789ABCDEF0123456789"
        assert plugin.categories == ["Instrument", "Synth"]
        assert plugin.source == PluginSource.MODULEINFO_JSON
        assert plugin.confidence == "confirmed"

    def test_scan_vst3_fallback_to_bundle_name(self, tmp_path):
        """Test VST3 scanning falls back to bundle name if no moduleinfo."""
        bundle = tmp_path / "FallbackPlugin.vst3"
        bundle.mkdir()
        (bundle / "Contents" / "Resources").mkdir(parents=True)

        dirs = {PluginFormat.VST3: [tmp_path]}
        plugins = scan_installed(dirs)

        assert len(plugins) == 1
        plugin = plugins[0]
        assert plugin.name == "FallbackPlugin"
        assert plugin.format == PluginFormat.VST3
        assert plugin.confidence == "heuristic"


class TestScanAU:
    """Test AU (Audio Unit) scanning."""

    def test_scan_au_with_info_plist(self, tmp_path):
        """Test AU scanning with Info.plist."""
        bundle = tmp_path / "TestAU.component"
        bundle.mkdir()
        contents = bundle / "Contents"
        contents.mkdir(parents=True)
        macos = contents / "MacOS"
        macos.mkdir()

        # Create Info.plist with AudioComponents
        plist_data = {
            "CFBundleName": "Test AU Plugin",
            "CFBundleVendor": "Au Vendor Inc.",
            "CFBundleShortVersionString": "2.0.1",
            "AudioComponents": [
                {
                    "type": "aufx",
                    "subtype": "test",
                    "manufacturer": "TEST",
                    "name": "Test AU Plugin",
                },
            ],
        }

        plist_path = contents / "Info.plist"
        with open(plist_path, "wb") as f:
            plistlib.dump(plist_data, f)

        # Create a minimal Mach-O binary (64-bit x86_64)
        exe_path = macos / "TestAU"
        with open(exe_path, "wb") as f:
            # Mach-O 64-bit little-endian header
            f.write(b"\xcf\xfa\xed\xfe")  # Magic 0xfeedfacf
            f.write(b"\x07\x00\x00\x01")  # CPU type 0x01000007 (x86_64) as little-endian
            f.write(b"\x00" * 16)  # Rest of header

        dirs = {PluginFormat.AU: [tmp_path]}
        plugins = scan_installed(dirs)

        assert len(plugins) == 1
        plugin = plugins[0]
        assert plugin.name == "Test AU Plugin"
        assert plugin.vendor == "Au Vendor Inc."
        assert plugin.format == PluginFormat.AU
        assert plugin.version == "2.0.1"
        assert plugin.identity.au_type == "aufx"
        assert plugin.identity.au_subtype == "test"
        assert plugin.identity.au_manufacturer == "TEST"
        assert "x86_64" in plugin.architectures
        assert plugin.source == PluginSource.INFO_PLIST
        assert plugin.confidence == "confirmed"


class TestScanVST2:
    """Test VST2 scanning."""

    def test_scan_vst2_windows_dll(self, tmp_path):
        """Test VST2 DLL scanning."""
        plugin_dll = tmp_path / "MyPlugin_x64.dll"
        plugin_dll.write_bytes(b"DLL")

        dirs = {PluginFormat.VST2: [tmp_path]}
        plugins = scan_installed(dirs)

        assert len(plugins) == 1
        plugin = plugins[0]
        assert plugin.name == "MyPlugin_x64"
        assert plugin.format == PluginFormat.VST2
        assert plugin.source == PluginSource.FILENAME
        assert plugin.confidence == "heuristic"


class TestScanCLAP:
    """Test CLAP scanning."""

    def test_scan_clap_macos_bundle(self, tmp_path):
        """Test CLAP bundle scanning on macOS."""
        bundle = tmp_path / "TestCLAP.clap"
        bundle.mkdir()
        contents = bundle / "Contents"
        contents.mkdir(parents=True)
        macos = contents / "MacOS"
        macos.mkdir()

        # Create Info.plist
        plist_data = {
            "CFBundleName": "Test CLAP",
            "CFBundleVendor": "CLAP Vendor",
            "CFBundleShortVersionString": "1.0.0",
        }

        plist_path = contents / "Info.plist"
        with open(plist_path, "wb") as f:
            plistlib.dump(plist_data, f)

        # Create minimal Mach-O (arm64)
        exe_path = macos / "TestCLAP"
        with open(exe_path, "wb") as f:
            f.write(b"\xcf\xfa\xed\xfe")  # Magic 0xfeedfacf (little-endian)
            # CPU type 0x0100000C (arm64) as little-endian bytes
            f.write(b"\x0c\x00\x00\x01")
            f.write(b"\x00" * 16)

        dirs = {PluginFormat.CLAP: [tmp_path]}
        plugins = scan_installed(dirs)

        assert len(plugins) == 1
        plugin = plugins[0]
        assert plugin.name == "Test CLAP"
        assert plugin.vendor == "CLAP Vendor"
        assert plugin.format == PluginFormat.CLAP
        assert plugin.version == "1.0.0"
        assert "arm64" in plugin.architectures

    def test_scan_clap_windows_dll(self, tmp_path):
        """Test CLAP DLL scanning on Windows."""
        plugin_dll = tmp_path / "myclaplugin.clap"
        plugin_dll.write_bytes(b"CLAP")

        dirs = {PluginFormat.CLAP: [tmp_path]}
        plugins = scan_installed(dirs)

        assert len(plugins) == 1
        plugin = plugins[0]
        assert plugin.name == "myclaplugin"
        assert plugin.format == PluginFormat.CLAP
        assert plugin.source == PluginSource.FILENAME


class TestScanAAX:
    """Test AAX scanning."""

    def test_scan_aax_bundle(self, tmp_path):
        """Test AAX bundle scanning."""
        bundle = tmp_path / "TestAAX.aaxplugin"
        bundle.mkdir()
        contents = bundle / "Contents"
        contents.mkdir(parents=True)

        plist_data = {
            "CFBundleName": "Test AAX Plugin",
            "CFBundleVendor": "AAX Vendor",
            "CFBundleShortVersionString": "3.0.0",
        }

        plist_path = contents / "Info.plist"
        with open(plist_path, "wb") as f:
            plistlib.dump(plist_data, f)

        dirs = {PluginFormat.AAX: [tmp_path]}
        plugins = scan_installed(dirs)

        assert len(plugins) == 1
        plugin = plugins[0]
        assert plugin.name == "Test AAX Plugin"
        assert plugin.vendor == "AAX Vendor"
        assert plugin.format == PluginFormat.AAX
        assert plugin.version == "3.0.0"
        assert plugin.source == PluginSource.INFO_PLIST
        assert plugin.confidence == "confirmed"


class TestMachOParsing:
    """Test Mach-O architecture parsing."""

    def test_parse_single_arch_x86_64(self, tmp_path):
        """Test parsing single-arch x86_64 Mach-O."""
        from rackcheck_engine.inventory.scan import _parse_macho_architectures

        exe = tmp_path / "test_x86_64"
        with open(exe, "wb") as f:
            f.write(b"\xcf\xfa\xed\xfe")  # Mach-O 64-bit magic (little-endian)
            # CPU type 0x01000007 (x86_64) as little-endian bytes
            f.write(b"\x07\x00\x00\x01")
            f.write(b"\x00" * 16)

        archs = _parse_macho_architectures(exe)
        assert "x86_64" in archs, f"Expected x86_64, got {archs}"

    def test_parse_fat_binary(self, tmp_path):
        """Test parsing fat binary (universal)."""
        from rackcheck_engine.inventory.scan import _parse_macho_architectures

        exe = tmp_path / "test_universal"
        with open(exe, "wb") as f:
            f.write(b"\xca\xfe\xba\xbe")  # Fat binary magic
            f.write(b"\x00\x00\x00\x02")  # 2 architectures
            # First: x86_64
            f.write(b"\x01\x00\x00\x07")  # CPU type (big-endian)
            f.write(b"\x00\x00\x00\x03")  # CPU subtype
            f.write(b"\x00" * 16)
            # Second: arm64
            f.write(b"\x01\x00\x00\x0c")  # ARM64
            f.write(b"\x00\x00\x00\x00")  # CPU subtype
            f.write(b"\x00" * 16)

        archs = _parse_macho_architectures(exe)
        assert "x86_64" in archs or "arm64" in archs


class TestSaveLoadInventory:
    """Test inventory save/load."""

    def test_save_and_load_inventory(self, tmp_path):
        """Test saving and loading inventory to/from JSON."""
        plugin1 = InstalledPlugin(
            name="Plugin One",
            vendor="Vendor A",
            format=PluginFormat.VST3,
            version="1.0",
            path="/path/to/plugin1.vst3",
            identity=PluginIdentity(vst3_cid="ABCD1234" + "0" * 24),
            url="https://example.com",
            source=PluginSource.MODULEINFO_JSON,
            confidence="confirmed",
        )

        plugin2 = InstalledPlugin(
            name="Plugin Two",
            vendor="Vendor B",
            format=PluginFormat.AU,
            version="2.0",
            path="/path/to/plugin2.component",
            identity=PluginIdentity(
                au_type="aufx", au_subtype="dely", au_manufacturer="VenB"
            ),
            source=PluginSource.INFO_PLIST,
            confidence="probable",
        )

        plugins = [plugin1, plugin2]
        inv_path = tmp_path / "inventory.json"

        # Save
        save_inventory(plugins, inv_path)
        assert inv_path.exists()

        # Load
        loaded = load_inventory(inv_path)
        assert len(loaded) == 2

        # Verify first plugin
        assert loaded[0].name == "Plugin One"
        assert loaded[0].vendor == "Vendor A"
        assert loaded[0].format == PluginFormat.VST3
        assert loaded[0].identity.vst3_cid == "ABCD1234" + "0" * 24
        assert loaded[0].confidence == "confirmed"

        # Verify second plugin
        assert loaded[1].name == "Plugin Two"
        assert loaded[1].identity.au_type == "aufx"


class TestInstalledPluginToDict:
    """Test InstalledPlugin.to_dict() for JSON serialization."""

    def test_to_dict_serializable(self):
        """Test that to_dict() produces JSON-serializable output."""
        plugin = InstalledPlugin(
            name="Test",
            vendor="Vendor",
            format=PluginFormat.VST3,
            version="1.0",
            path="/path",
            identity=PluginIdentity(vst3_cid="A" * 32),
            source=PluginSource.MODULEINFO_JSON,
            confidence="confirmed",
            categories=["Instrument"],
            architectures=["x86_64"],
        )

        d = plugin.to_dict()

        # Verify it can be JSON-serialized
        assert json.dumps(d)

        # Verify enums are strings
        assert isinstance(d["format"], str)
        assert d["format"] == "vst3"
        assert isinstance(d["source"], str)
        assert d["source"] == "moduleinfo_json"
        assert isinstance(d["confidence"], str)


class TestNoPluginBinaryLoading:
    """Verify that plugin binaries are never loaded in main process."""

    def test_scan_does_not_import_plugins(self, tmp_path):
        """Test that scanning doesn't import or load plugin binaries."""
        # This is hard to test directly, but we can ensure:
        # 1. No subprocess is spawned without allow_sandbox_probe=True
        # 2. Only metadata files are read, not the binary

        bundle = tmp_path / "Test.vst3"
        bundle.mkdir()
        contents = bundle / "Contents" / "Resources"
        contents.mkdir(parents=True)

        # Create moduleinfo.json only (no binary)
        moduleinfo_path = contents / "moduleinfo.json"
        with open(moduleinfo_path, "w") as f:
            json.dump(
                {
                    "Factory Info": {"Vendor": "Test"},
                    "Classes": [
                        {"Name": "Test", "CID": "A" * 32, "Category": "Audio Module Class"}
                    ],
                },
                f,
            )

        dirs = {PluginFormat.VST3: [tmp_path]}

        # This should not raise any errors or try to load the plugin
        plugins = scan_installed(dirs, allow_sandbox_probe=False)
        assert len(plugins) == 1


class TestProbeInSubprocess:
    """Test subprocess probing."""

    def test_probe_returns_dict_or_none(self):
        """Test that probe_in_subprocess returns dict or None."""
        result = probe_in_subprocess(Path("/nonexistent/plugin"))
        assert result is None or isinstance(result, dict)


class TestRecursionDepth:
    """Test that recursion depth is limited."""

    def test_max_depth_respected(self, tmp_path):
        """Test that scanning respects max_depth parameter."""
        # Create deeply nested VST3 bundles
        root = tmp_path / "depth0"
        root.mkdir()

        current = root
        for i in range(1, 6):
            nested = current / f"depth{i}"
            nested.mkdir()
            current = nested

        # Create a plugin at deep level
        bundle = current / "DeepPlugin.vst3"
        bundle.mkdir()

        # Scan with max_depth=2 (should not find it at depth 5)
        dirs = {PluginFormat.VST3: [root]}
        plugins = scan_installed(dirs, max_depth=2)
        assert len(plugins) == 0

        # Scan with max_depth=10 (should find it)
        plugins = scan_installed(dirs, max_depth=10)
        assert len(plugins) == 1
