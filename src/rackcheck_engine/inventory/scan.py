"""Scan installed plugins on the user's machine (SPEC-02 section 6).

Never loads plugin binaries in the main process (P6). Reads metadata files only.
For binaries that must be probed, uses subprocess with timeout.
"""

from __future__ import annotations

import json
import platform
import plistlib
import re
import struct
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal

from rackcheck_engine.model import PluginFormat, PluginIdentity


class PluginSource(StrEnum):
    """How metadata was obtained."""

    MODULEINFO_JSON = "moduleinfo_json"  # VST3 JSON metadata
    INFO_PLIST = "info_plist"  # AU / macOS bundle plist
    BUNDLE_NAME = "bundle_name"  # Heuristic: bundle directory name
    FILENAME = "filename"  # Heuristic: plugin file name
    SUBPROCESS_PROBE = "subprocess_probe"  # Probed in sandboxed child process


@dataclass
class InstalledPlugin:
    """A plugin found on the user's machine."""

    name: str
    vendor: str | None
    format: PluginFormat
    version: str | None
    path: str
    identity: PluginIdentity = field(default_factory=PluginIdentity)
    url: str | None = None
    categories: list[str] = field(default_factory=list)
    architectures: list[str] = field(default_factory=list)
    bundle_id: str | None = None  # CFBundleIdentifier (macOS bundles only)
    source: PluginSource = PluginSource.FILENAME
    confidence: Literal["confirmed", "probable", "heuristic"] = "heuristic"

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict via asdict."""
        result = asdict(self)
        # Ensure enums are serialized as strings
        result["format"] = str(self.format.value)
        result["source"] = str(self.source.value)
        result["identity"] = asdict(self.identity)
        return result


def default_plugin_dirs(platform_name: str | None = None) -> dict[PluginFormat, list[Path]]:
    """Get standard plugin directories for the current platform.

    Args:
        platform_name: 'Windows', 'Darwin' (macOS), or None to detect.
                      Can use actual platform.system() values.

    Returns:
        Mapping of PluginFormat to list of Path objects.
    """
    if platform_name is None:
        platform_name = platform.system()

    result: dict[PluginFormat, list[Path]] = {}

    if platform_name == "Windows":
        pf = Path("C:/Program Files")
        pf_x86 = Path("C:/Program Files (x86)")
        common = Path("C:/Program Files/Common Files")
        local_appdata = Path.home() / "AppData/Local"

        result[PluginFormat.VST3] = [common / "VST3"]
        result[PluginFormat.VST2] = [
            pf / "VSTPlugins",
            common / "VST",
            common / "VST2",
            pf_x86 / "VSTPlugins",
        ]
        result[PluginFormat.CLAP] = [
            common / "CLAP",
            local_appdata / "Programs/Common/CLAP",
        ]
        result[PluginFormat.AAX] = [common / "Avid/Audio/Plug-Ins"]
        result[PluginFormat.AU] = []

    elif platform_name == "Darwin":
        home_lib = Path.home() / "Library/Audio/Plug-Ins"
        system_lib = Path("/Library/Audio/Plug-Ins")
        home_app_support = Path.home() / "Library/Application Support"
        system_app_support = Path("/Library/Application Support")

        result[PluginFormat.VST3] = [
            system_lib / "VST3",
            home_lib / "VST3",
        ]
        result[PluginFormat.VST2] = [
            system_lib / "VST",
            home_lib / "VST",
        ]
        result[PluginFormat.AU] = [
            system_lib / "Components",
            home_lib / "Components",
        ]
        result[PluginFormat.CLAP] = [
            system_lib / "CLAP",
            home_lib / "CLAP",
        ]
        result[PluginFormat.AAX] = [
            system_app_support / "Avid/Audio/Plug-Ins",
            home_app_support / "Avid/Audio/Plug-Ins",
        ]

    else:
        # Linux or unknown: return empty
        pass

    return result


def _read_json5(text: str) -> dict:
    """Parse JSON5-like content (trailing commas, // comments)."""
    import re

    # Remove // comments more carefully (don't remove from URLs)
    # Only remove comments that appear after JSON syntax (quotes, commas, braces)
    result_lines = []
    for line in text.split("\n"):
        # Check if there's a // comment by looking for // outside of strings
        in_string = False
        escaped = False
        comment_start = -1

        for i, char in enumerate(line):
            if escaped:
                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue

            if char == '"':
                in_string = not in_string
                continue

            if not in_string and i < len(line) - 1 and line[i : i + 2] == "//":
                comment_start = i
                break

        if comment_start >= 0:
            line = line[:comment_start]

        result_lines.append(line)

    text = "\n".join(result_lines)

    # Remove trailing commas before ] or }
    text = re.sub(r",(\s*[}\]])", r"\1", text)

    return json.loads(text)


def _read_moduleinfo_json(path: Path) -> dict | None:
    """Try to read VST3 moduleinfo.json."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            content = f.read()
            return _read_json5(content)
    except Exception:
        # Silently ignore parse errors
        return None


def _read_plist(path: Path) -> dict | None:
    """Try to read Info.plist."""
    try:
        with open(path, "rb") as f:
            return plistlib.load(f)
    except Exception:
        return None


def _parse_macho_architectures(path: Path) -> list[str]:
    """Parse Mach-O binary header to list architectures.

    Reads only the header bytes to identify architecture (no binary loading).
    Returns empty list on error.
    """
    try:
        with open(path, "rb") as f:
            header = f.read(512)

        if len(header) < 8:
            return []

        archs = []

        # Read magic as both big-endian and little-endian
        magic_be = struct.unpack(">I", header[:4])[0]
        magic_le = struct.unpack("<I", header[:4])[0]

        if magic_be == 0xCAFEBABE:  # Fat binary, big-endian
            nfat = struct.unpack(">I", header[4:8])[0]
            for i in range(min(nfat, 10)):  # cap at 10 archs
                cpu_type = struct.unpack(">I", header[8 + i * 8 : 12 + i * 8])[0]
                if cpu_type == 0x00000007:
                    archs.append("i386")
                elif cpu_type == 0x01000007:
                    archs.append("x86_64")
                elif cpu_type == 0x0000000C:
                    archs.append("arm64")
                elif cpu_type == 0x0100000C:
                    archs.append("arm64e")

        elif magic_le in (0xFEEDFACE, 0xFEEDFACF):  # Single arch, little-endian
            cpu_type = struct.unpack("<I", header[4:8])[0]
            if cpu_type == 0x00000007:
                archs.append("i386")
            elif cpu_type == 0x01000007:
                archs.append("x86_64")
            elif cpu_type == 0x0000000C:
                archs.append("arm")
            elif cpu_type == 0x0100000C:
                archs.append("arm64")

        elif magic_be in (0xCEFAEDFE, 0xCFFAEDFE):  # Single arch, big-endian
            # Big-endian Mach-O (rare, mostly for older PPC Macs)
            cpu_type = struct.unpack(">I", header[4:8])[0]
            if cpu_type == 0x00000007:
                archs.append("i386")
            elif cpu_type == 0x01000007:
                archs.append("x86_64")
            elif cpu_type == 0x0000000C:
                archs.append("arm")
            elif cpu_type == 0x0100000C:
                archs.append("arm64")

        return archs
    except Exception:
        return []


def probe_in_subprocess(path: Path, timeout: float = 2.0) -> dict | None:
    """Probe a plugin in a sandboxed subprocess (future work).

    For now, returns file-level info only. Real descriptor loading is future work.

    Args:
        path: Path to plugin bundle or binary.
        timeout: Timeout in seconds.

    Returns:
        Dict with probed info, or None on error/timeout.
    """
    code = f"""
import sys
path = {str(path)!r}
# Future: load plugin and read descriptor
print("{{" + '"name": "unknown"' + "}}")
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return json.loads(result.stdout.strip())
    except Exception:
        pass
    return None


def scan_installed(
    dirs: dict[PluginFormat, list[Path]] | None = None,
    *,
    allow_sandbox_probe: bool = False,
    max_depth: int = 3,
) -> list[InstalledPlugin]:
    """Scan for installed plugins in standard directories.

    Never loads plugin binaries in the main process.

    Args:
        dirs: Plugin directories per format. If None, uses default_plugin_dirs().
        allow_sandbox_probe: If True, use subprocess to probe binaries (CLAP, VST2).
        max_depth: Max recursion depth to prevent deep traversal.

    Returns:
        List of InstalledPlugin objects.
    """
    if dirs is None:
        dirs = default_plugin_dirs()

    plugins: list[InstalledPlugin] = []

    def walk_dir(start: Path, format_type: PluginFormat, depth: int = 0):
        """Recursively walk directory tree."""
        if depth > max_depth:
            return

        try:
            entries = list(start.iterdir())
        except (PermissionError, OSError):
            return

        for entry in entries:
            try:
                # Don't follow symlinks outside project
                if entry.is_symlink():
                    continue

                if format_type == PluginFormat.VST3:
                    if entry.suffix.lower() == ".vst3":
                        # Bundle folder, or a legacy single-file .vst3 on Windows.
                        plugins.extend(_scan_vst3(entry))
                        continue  # never descend into a plugin bundle

                elif format_type == PluginFormat.VST2:
                    if entry.suffix in (".dll", ".vst") and entry.is_file():
                        plugin = _scan_vst2(entry)
                        if plugin:
                            plugins.append(plugin)

                elif format_type == PluginFormat.AU:
                    if entry.suffix == ".component" and entry.is_dir():
                        plugin = _scan_au(entry)
                        if plugin:
                            plugins.append(plugin)

                elif format_type == PluginFormat.CLAP:
                    if entry.suffix == ".clap":
                        if entry.is_dir():  # macOS
                            plugin = _scan_clap_macos(entry, allow_sandbox_probe)
                        else:  # Windows
                            plugin = _scan_clap_windows(entry, allow_sandbox_probe)
                        if plugin:
                            plugins.append(plugin)

                elif (
                    format_type == PluginFormat.AAX
                    and entry.suffix == ".aaxplugin"
                    and entry.is_dir()
                ):
                    plugin = _scan_aax(entry)
                    if plugin:
                        plugins.append(plugin)

                # Recurse
                if entry.is_dir() and depth < max_depth:
                    walk_dir(entry, format_type, depth + 1)

            except (PermissionError, OSError):
                continue

    for format_type, dir_list in dirs.items():
        for dir_path in dir_list:
            if dir_path.exists():
                walk_dir(dir_path, format_type)

    for plugin in plugins:
        if plugin.bundle_id is None and plugin.path:
            plist = _read_plist(Path(plugin.path) / "Contents" / "Info.plist")
            if isinstance(plist, dict):
                bid = plist.get("CFBundleIdentifier")
                plugin.bundle_id = bid if isinstance(bid, str) and bid else None

    return plugins


def _bundle_architectures(bundle_path: Path) -> list[str]:
    macho_dir = bundle_path / "Contents" / "MacOS"
    if not macho_dir.is_dir():
        return []
    for exe in macho_dir.iterdir():
        if exe.is_file():
            return _parse_macho_architectures(exe)
    return []


def _scan_vst3(bundle_path: Path) -> list[InstalledPlugin]:
    """Scan a VST3 bundle: one entry per "Audio Module Class" in moduleinfo.json.

    Falls back to Info.plist (macOS) and finally the bundle name (heuristic).
    """
    archs = _bundle_architectures(bundle_path) if bundle_path.is_dir() else []

    for moduleinfo_path in (
        bundle_path / "Contents" / "Resources" / "moduleinfo.json",
        bundle_path / "Contents" / "moduleinfo.json",  # SDK 3.7.5 location
    ):
        if not moduleinfo_path.is_file():
            continue
        data = _read_moduleinfo_json(moduleinfo_path)
        if not isinstance(data, dict):
            break
        factory = data.get("Factory Info") or {}
        factory_vendor = factory.get("Vendor") or None
        factory_url = factory.get("URL") or None
        found: list[InstalledPlugin] = []
        for cls in data.get("Classes") or []:
            if not isinstance(cls, dict) or cls.get("Category") != "Audio Module Class":
                continue
            cid = str(cls.get("CID", "")).upper()
            found.append(
                InstalledPlugin(
                    name=cls.get("Name") or data.get("Name") or bundle_path.stem,
                    vendor=cls.get("Vendor") or factory_vendor,
                    format=PluginFormat.VST3,
                    version=cls.get("Version") or data.get("Version") or None,
                    path=str(bundle_path),
                    identity=PluginIdentity(
                        vst3_cid=cid if re.fullmatch(r"[0-9A-F]{32}", cid) else None
                    ),
                    url=factory_url,
                    categories=[str(c) for c in cls.get("Sub Categories") or []],
                    architectures=archs,
                    source=PluginSource.MODULEINFO_JSON,
                    confidence="confirmed",
                )
            )
        if found:
            return found
        break

    name, vendor, version = bundle_path.stem, None, None
    source = PluginSource.BUNDLE_NAME
    confidence: Literal["confirmed", "probable", "heuristic"] = "heuristic"
    plist = _read_plist(bundle_path / "Contents" / "Info.plist")
    if plist:
        name = plist.get("CFBundleName") or name
        vendor = plist.get("CFBundleVendor") or None
        version = plist.get("CFBundleShortVersionString") or None
        source = PluginSource.INFO_PLIST
        confidence = "probable"
    return [
        InstalledPlugin(
            name=name,
            vendor=vendor,
            format=PluginFormat.VST3,
            version=version,
            path=str(bundle_path),
            architectures=archs,
            source=source,
            confidence=confidence,
        )
    ]


def _scan_vst2(file_path: Path) -> InstalledPlugin | None:
    """Scan VST2 binary for plugin metadata."""
    name = file_path.stem
    return InstalledPlugin(
        name=name,
        vendor=None,
        format=PluginFormat.VST2,
        version=None,
        path=str(file_path),
        source=PluginSource.FILENAME,
        confidence="heuristic",
    )


def _scan_au(bundle_path: Path) -> InstalledPlugin | None:
    """Scan AU bundle for plugin metadata."""
    plist_path = bundle_path / "Contents" / "Info.plist"
    name = bundle_path.stem
    vendor = None
    version = None
    identity = PluginIdentity()
    source = PluginSource.BUNDLE_NAME
    confidence: Literal["confirmed", "probable", "heuristic"] = "heuristic"
    archs: list[str] = []

    if plist_path.exists():
        plist = _read_plist(plist_path)
        if plist:
            # Get version and bundle info first
            version = plist.get("CFBundleShortVersionString", version)
            vendor = plist.get("CFBundleVendor", vendor)
            name = plist.get("CFBundleName", name)

            # Try AudioComponents array
            audio_components = plist.get("AudioComponents", [])
            if audio_components and isinstance(audio_components, list):
                comp = audio_components[0]
                if "name" in comp:
                    name = comp["name"]
                if "manufacturer" in comp:
                    # Store as 4-char code
                    identity.au_manufacturer = comp["manufacturer"]
                if "type" in comp:
                    identity.au_type = comp["type"]
                if "subtype" in comp:
                    identity.au_subtype = comp["subtype"]
                source = PluginSource.INFO_PLIST
                confidence = "confirmed"

            # Read Mach-O architecture
            macho_path = bundle_path / "Contents" / "MacOS"
            if macho_path.exists():
                for exe in macho_path.iterdir():
                    if exe.is_file():
                        archs = _parse_macho_architectures(exe)
                        break

    return InstalledPlugin(
        name=name,
        vendor=vendor,
        format=PluginFormat.AU,
        version=version,
        path=str(bundle_path),
        identity=identity,
        architectures=archs,
        source=source,
        confidence=confidence,
    )


def _scan_clap_macos(bundle_path: Path, allow_probe: bool = False) -> InstalledPlugin | None:
    """Scan CLAP bundle on macOS."""
    name = bundle_path.stem
    vendor = None
    version = None
    archs: list[str] = []

    # Try Info.plist
    plist_path = bundle_path / "Contents" / "Info.plist"
    if plist_path.exists():
        plist = _read_plist(plist_path)
        if plist:
            name = plist.get("CFBundleName", name)
            vendor = plist.get("CFBundleVendor", vendor)
            version = plist.get("CFBundleShortVersionString", version)

    # Read Mach-O architecture
    macho_path = bundle_path / "Contents" / "MacOS"
    if macho_path.exists():
        for exe in macho_path.iterdir():
            if exe.is_file():
                archs = _parse_macho_architectures(exe)
                break

    return InstalledPlugin(
        name=name,
        vendor=vendor,
        format=PluginFormat.CLAP,
        version=version,
        path=str(bundle_path),
        architectures=archs,
        source=PluginSource.BUNDLE_NAME,
        confidence="heuristic",
    )


def _scan_clap_windows(file_path: Path, allow_probe: bool = False) -> InstalledPlugin | None:
    """Scan CLAP binary on Windows."""
    return InstalledPlugin(
        name=file_path.stem,
        vendor=None,
        format=PluginFormat.CLAP,
        version=None,
        path=str(file_path),
        source=PluginSource.FILENAME,
        confidence="heuristic",
    )


def _scan_aax(bundle_path: Path) -> InstalledPlugin | None:
    """Scan AAX bundle for plugin metadata."""
    plist_path = bundle_path / "Contents" / "Info.plist"
    name = bundle_path.stem

    if plist_path.exists():
        plist = _read_plist(plist_path)
        if plist:
            name = plist.get("CFBundleName", name)
            vendor = plist.get("CFBundleVendor")
            version = plist.get("CFBundleShortVersionString")

            return InstalledPlugin(
                name=name,
                vendor=vendor,
                format=PluginFormat.AAX,
                version=version,
                path=str(bundle_path),
                source=PluginSource.INFO_PLIST,
                confidence="confirmed",
            )

    return InstalledPlugin(
        name=name,
        vendor=None,
        format=PluginFormat.AAX,
        version=None,
        path=str(bundle_path),
        source=PluginSource.BUNDLE_NAME,
        confidence="heuristic",
    )


def save_inventory(plugins: list[InstalledPlugin], path: Path | str) -> None:
    """Save inventory to JSON file."""
    path = Path(path)
    data = [p.to_dict() for p in plugins]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_inventory(path: Path | str) -> list[InstalledPlugin]:
    """Load inventory from JSON file."""
    path = Path(path)
    if not path.exists():
        return []

    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)

    plugins = []
    for item in data:
        identity = PluginIdentity(
            vst2_unique_id=item.get("identity", {}).get("vst2_unique_id"),
            vst3_cid=item.get("identity", {}).get("vst3_cid"),
            au_type=item.get("identity", {}).get("au_type"),
            au_subtype=item.get("identity", {}).get("au_subtype"),
            au_manufacturer=item.get("identity", {}).get("au_manufacturer"),
            clap_id=item.get("identity", {}).get("clap_id"),
            aax_ids=item.get("identity", {}).get("aax_ids"),
            file_hint=item.get("identity", {}).get("file_hint"),
        )

        plugin = InstalledPlugin(
            name=item.get("name", ""),
            vendor=item.get("vendor"),
            format=PluginFormat(item.get("format", "unknown")),
            version=item.get("version"),
            path=item.get("path", ""),
            identity=identity,
            url=item.get("url"),
            categories=item.get("categories", []),
            architectures=item.get("architectures", []),
            bundle_id=item.get("bundle_id"),
            source=PluginSource(item.get("source", "filename")),
            confidence=item.get("confidence", "heuristic"),
        )
        plugins.append(plugin)

    return plugins
