"""REAPER .rpp, .rfxchain, .RTrackTemplate reader (SPEC-02 section 4.1).

Parses plain-text nested chunk format. Extracts DAW version, tempo, sample rate,
tracks, plugins with identities, bypass states, and media references.
"""

from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..detect import ProjectFormat
from ..errors import CORRUPT_PROJECT, EngineError
from ..model import (
    Confidence,
    MediaRef,
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


@dataclass
class Token:
    """A token from the REAPER text format."""

    type: str  # "chunk_open", "chunk_close", "word", "string", "number"
    value: str | int | float


class ReaperReader:
    """Reads REAPER .rpp, .rfxchain, .RTrackTemplate files."""

    formats = (
        ProjectFormat.REAPER_RPP,
        ProjectFormat.REAPER_FXCHAIN,
        ProjectFormat.REAPER_TRACK_TEMPLATE,
    )
    version = "0.1.0"

    def can_read(self, path: Path) -> Confidence | None:
        """Check if we can read this file as REAPER format."""
        try:
            text = self._read_text(path)
            if text.lstrip().startswith("<REAPER_PROJECT") or text.lstrip().startswith("<"):
                return Confidence.PROBABLE
        except (OSError, UnicodeDecodeError):
            pass
        return None

    def read(self, path: Path) -> ScanResult:
        """Parse a REAPER file into the common data model."""
        try:
            text = self._read_text(path)
        except (OSError, UnicodeDecodeError) as exc:
            raise EngineError(
                CORRUPT_PROJECT,
                f"Could not read {path.name}: {exc}",
                {"path": str(path)},
            ) from exc

        try:
            parser = ReaperParser(text, project_path=path.parent)
            data = parser.parse_project()
        except (ValueError, IndexError) as exc:
            raise EngineError(
                CORRUPT_PROJECT,
                f"Could not parse {path.name}: {exc}",
                {"path": str(path)},
            ) from exc

        # Build ScanResult
        daw_version = data.get("daw_version")
        tempo_bpm = data.get("tempo_bpm")
        time_sig = data.get("time_signature")
        sample_rate = data.get("sample_rate")

        source = SourceInfo(
            path=str(path),
            format=data.get("format", "reaper_rpp"),
            daw_name="REAPER",
            daw_version=daw_version,
            reader_version=self.version,
        )

        project = ProjectInfo(
            tempo_bpm=tempo_bpm,
            time_signature=time_sig,
            sample_rate=sample_rate,
        )

        tracks = data.get("tracks", [])
        plugins = data.get("plugins", [])
        media = data.get("media", [])

        return ScanResult(
            source=source,
            project=project,
            tracks=tracks,
            plugins=plugins,
            media=media,
            warnings=data.get("warnings", []),
        )

    @staticmethod
    def _read_text(path: Path) -> str:
        """Read file as text, trying UTF-8 first then latin-1."""
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1")


class ReaperParser:
    """Parser for REAPER text format."""

    def __init__(self, text: str, project_path: Path | None = None):
        self.lines = text.split("\n")
        self.line_idx = 0
        self.chunk_depth = 0
        self.project_path = project_path or Path(".")
        self.record_path = None  # Will be set if RECORD_PATH is found

    def parse_project(self) -> dict[str, Any]:
        """Parse a REAPER project file and return extracted data."""
        result = {
            "format": "reaper_rpp",
            "daw_version": None,
            "tempo_bpm": None,
            "time_signature": None,
            "sample_rate": None,
            "tracks": [],
            "plugins": [],
            "media": [],
            "warnings": [],
        }

        # Parse header line
        if self.line_idx < len(self.lines):
            header_line = self.lines[self.line_idx].strip()
            if header_line.startswith("<REAPER_PROJECT"):
                result["daw_version"] = self._parse_header_version(header_line)
                self.line_idx += 1

        # Parse project content
        track_id_counter = 0
        plugin_id_counter = 0
        media_by_path = {}  # For deduplication

        while self.line_idx < len(self.lines):
            line = self.lines[self.line_idx].strip()

            if not line or line == ">":
                self.line_idx += 1
                continue

            # Parse RECORD_PATH (for resolving relative media paths)
            if line.startswith("RECORD_PATH "):
                parts = line.split()
                if len(parts) >= 2:
                    record_path = self._unquote(parts[1])
                    if record_path:
                        self.record_path = record_path
                self.line_idx += 1
                continue

            # Parse TEMPO
            if line.startswith("TEMPO "):
                parts = line.split()
                if len(parts) >= 2:
                    with suppress(ValueError):
                        result["tempo_bpm"] = float(parts[1])
                self.line_idx += 1
                continue

            # Parse TIME_SIGNATURE
            if line.startswith("TIMESIG "):
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        num = int(parts[1])
                        denom = int(parts[2])
                        result["time_signature"] = f"{num}/{denom}"
                    except ValueError:
                        pass
                self.line_idx += 1
                continue

            # Parse SAMPLERATE
            if line.startswith("SAMPLERATE "):
                parts = line.split()
                if len(parts) >= 2:
                    with suppress(ValueError):
                        result["sample_rate"] = int(parts[1])
                self.line_idx += 1
                continue

            # Parse TRACK
            if line.startswith("<TRACK"):
                self.line_idx += 1  # Skip the <TRACK line
                track_id = f"t{track_id_counter}"
                track_id_counter += 1
                track_data, plugin_ids, media_refs = self._parse_track_chunk(
                    track_id, plugin_id_counter
                )
                if track_data:
                    result["tracks"].append(track_data)
                plugin_id_counter += len(plugin_ids)
                for plugin_data in plugin_ids:
                    result["plugins"].append(plugin_data)
                for media_ref in media_refs:
                    media_by_path[media_ref.path] = media_ref
                continue  # line_idx was already advanced by _parse_track_chunk

            # Parse MASTERFXLIST
            if line.startswith("<MASTERFXLIST"):
                self.line_idx += 1  # Skip the <MASTERFXLIST line
                plugins, media_refs = self._parse_fxchain_chunk("master", plugin_id_counter)
                plugin_id_counter += len(plugins)
                for plugin_data in plugins:
                    result["plugins"].append(plugin_data)
                for media_ref in media_refs:
                    media_by_path[media_ref.path] = media_ref
                continue  # line_idx was already advanced by _parse_fxchain_chunk

            # Parse FILE references at top level (rare but possible)
            if line.startswith('FILE "'):
                media_ref = self._parse_file_line(line)
                if media_ref:
                    media_by_path[media_ref.path] = media_ref
                self.line_idx += 1
                continue

            self.line_idx += 1

        # Convert deduplicated media dict to list
        result["media"] = list(media_by_path.values())
        return result

    def _parse_header_version(self, header_line: str) -> str | None:
        """Extract DAW version from header line.
        Format: <REAPER_PROJECT 0.1 "7.22/win64" ...
        """
        match = re.search(r'"([^"]+)"', header_line)
        if match:
            return match.group(1)
        return None

    def _parse_track_chunk(
        self, track_id: str, base_plugin_id: int
    ) -> tuple[TrackRef | None, list[PluginRef], list[MediaRef]]:
        """Parse a <TRACK ... > chunk and return (track, [plugins], [media])."""
        track_name = None
        track_type = TrackType.AUDIO
        is_folder = False
        folder_depth = 0
        device_ids = []
        plugins = []
        media_refs = []

        # Read lines until closing >
        while self.line_idx < len(self.lines):
            line = self.lines[self.line_idx].strip()

            # Check for end of TRACK block
            if line == ">" or line.startswith("</TRACK"):
                self.line_idx += 1
                break

            # Parse NAME (don't advance yet, we'll do it at the bottom)
            if line.startswith("NAME "):
                track_name = self._unquote(line[5:])

            # Parse ISBUS (folder/group)
            if line.startswith("ISBUS "):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        folder_depth = int(parts[1])
                        is_folder = folder_depth > 0
                        if is_folder:
                            track_type = TrackType.FOLDER
                    except ValueError:
                        pass

            # Parse FXCHAIN - this function will advance line_idx past the entire FXCHAIN block
            if line.startswith("<FXCHAIN"):
                self.line_idx += 1  # Skip the <FXCHAIN line
                fxchain_plugins, fxchain_media = self._parse_fxchain_chunk(
                    track_id, base_plugin_id + len(plugins)
                )
                for plugin_data in fxchain_plugins:
                    device_ids.append(plugin_data.id)
                    plugins.append(plugin_data)
                for media_ref in fxchain_media:
                    media_refs.append(media_ref)
                continue  # line_idx was already advanced by _parse_fxchain_chunk

            # Parse ITEM (contains <SOURCE with FILE)
            if line.startswith("<ITEM"):
                self.line_idx += 1
                item_media = self._parse_item_chunk()
                for media_ref in item_media:
                    media_refs.append(media_ref)
                continue

            # Parse FILE references inside track
            if line.startswith('FILE "'):
                media_ref = self._parse_file_line(line)
                if media_ref:
                    media_refs.append(media_ref)

            self.line_idx += 1

        track = TrackRef(
            id=track_id,
            name=track_name,
            type=track_type,
            devices=device_ids,
        )

        return track, plugins, media_refs

    def _parse_fxchain_chunk(
        self, track_id: str, base_plugin_id: int
    ) -> tuple[list[PluginRef], list[MediaRef]]:
        """Parse an <FXCHAIN ... > chunk and return ([plugins], [media]).

        Called with line_idx already pointing to the line AFTER '<FXCHAIN'.
        """
        plugins = []
        media_refs = []
        plugin_count = 0
        bypass_state = False

        while self.line_idx < len(self.lines):
            line = self.lines[self.line_idx].strip()

            # Check for end of FXCHAIN block
            if line == ">" or line.startswith("</FXCHAIN"):
                self.line_idx += 1
                break

            if not line or line.startswith(";"):
                self.line_idx += 1
                continue

            # Parse BYPASS line (before plugin definition)
            if line.startswith("BYPASS "):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        bypass_state = int(parts[1]) != 0
                    except ValueError:
                        bypass_state = False
                self.line_idx += 1
                continue

            # Parse VST/AU/CLAP/JS plugin lines
            if line.startswith("<VST "):
                plugin_data = self._parse_vst_plugin(
                    line,
                    f"p{base_plugin_id + plugin_count}",
                    track_id,
                    plugin_count,
                    bypass_state,
                )
                if plugin_data:
                    plugins.append(plugin_data)
                    plugin_count += 1
                self.line_idx += 1
                # Skip past plugin state lines (base64, etc.)
                self._skip_plugin_state()
                bypass_state = False
                continue

            elif line.startswith("<AU "):
                plugin_data = self._parse_au_plugin(
                    line,
                    f"p{base_plugin_id + plugin_count}",
                    track_id,
                    plugin_count,
                    bypass_state,
                )
                if plugin_data:
                    plugins.append(plugin_data)
                    plugin_count += 1
                self.line_idx += 1
                self._skip_plugin_state()
                bypass_state = False
                continue

            elif line.startswith("<CLAP "):
                plugin_data = self._parse_clap_plugin(
                    line,
                    f"p{base_plugin_id + plugin_count}",
                    track_id,
                    plugin_count,
                    bypass_state,
                )
                if plugin_data:
                    plugins.append(plugin_data)
                    plugin_count += 1
                self.line_idx += 1
                self._skip_plugin_state()
                bypass_state = False
                continue

            elif line.startswith("<JS "):
                plugin_data = self._parse_js_plugin(
                    line,
                    f"p{base_plugin_id + plugin_count}",
                    track_id,
                    plugin_count,
                    bypass_state,
                )
                if plugin_data:
                    plugins.append(plugin_data)
                    plugin_count += 1
                self.line_idx += 1
                self._skip_plugin_state()
                bypass_state = False
                continue

            elif line.startswith("<DX "):
                # DirectX plugins (rare, skip for now)
                plugin_count += 1
                self.line_idx += 1
                self._skip_plugin_state()
                bypass_state = False
                continue

            # Parse FILE references inside FXCHAIN
            if line.startswith('FILE "'):
                media_ref = self._parse_file_line(line)
                if media_ref:
                    media_refs.append(media_ref)

            self.line_idx += 1

        return plugins, media_refs

    def _skip_plugin_state(self) -> None:
        """Skip past base64 state lines and other plugin data until closing >."""
        while self.line_idx < len(self.lines):
            line = self.lines[self.line_idx].strip()
            if line == ">":
                self.line_idx += 1
                break
            self.line_idx += 1

    def _parse_vst_plugin(
        self,
        line: str,
        plugin_id: str,
        track_id: str,
        slot_index: int,
        bypassed: bool,
    ) -> PluginRef | None:
        """Parse <VST "VST3: Name (Vendor)" ... or <VST "VST: Name (Vendor)" ..."""
        # Extract quoted name field
        match = re.search(r'<VST\s+"([^"]+)"', line)
        if not match:
            return None

        display_name = match.group(1)

        # Determine format and role
        if display_name.startswith("VST3i:"):
            format_ = PluginFormat.VST3
            role = PluginRole.INSTRUMENT
            display_name = display_name[6:].strip()
        elif display_name.startswith("VST3:"):
            format_ = PluginFormat.VST3
            role = PluginRole.EFFECT
            display_name = display_name[5:].strip()
        elif display_name.startswith("VSTi:"):
            format_ = PluginFormat.VST2
            role = PluginRole.INSTRUMENT
            display_name = display_name[5:].strip()
        elif display_name.startswith("VST:"):
            format_ = PluginFormat.VST2
            role = PluginRole.EFFECT
            display_name = display_name[4:].strip()
        else:
            format_ = PluginFormat.VST2
            role = PluginRole.UNKNOWN

        name, vendor = self._parse_name_vendor(display_name)

        # Extract identity
        vst3_cid = None
        vst2_unique_id = None

        if format_ == PluginFormat.VST3:
            # Extract GUID from line: <VST ... {...GUID...}
            guid_match = re.search(r"\{([0-9A-Fa-f]+)\}", line)
            if guid_match:
                vst3_cid = guid_match.group(1).upper()

        elif format_ == PluginFormat.VST2:
            # Extract unique ID from line
            # Format: <VST "..." file.dll 0 "" <uniqueid>...
            id_match = re.search(r'"\s+[\w\.\-]+\s+\d+\s+""\s+(\d+)', line)
            if id_match:
                with suppress(ValueError):
                    vst2_unique_id = int(id_match.group(1))

        identity = PluginIdentity(
            vst3_cid=vst3_cid,
            vst2_unique_id=vst2_unique_id,
        )

        return PluginRef(
            id=plugin_id,
            track_id=track_id,
            slot_index=slot_index,
            role=role,
            format=format_,
            name=name,
            vendor=vendor,
            confidence=Confidence.PROBABLE,
            identity=identity,
            bypassed=bypassed,
        )

    def _parse_au_plugin(
        self,
        line: str,
        plugin_id: str,
        track_id: str,
        slot_index: int,
        bypassed: bool,
    ) -> PluginRef | None:
        """Parse <AU "AU: Name (Vendor)" "Vendor: Name" ..."""
        # Extract quoted name fields
        matches = re.findall(r'"([^"]*)"', line)
        if len(matches) < 1:
            return None

        display_name = matches[0]

        # Determine role
        if display_name.startswith("AUi:"):
            role = PluginRole.INSTRUMENT
            display_name = display_name[4:].strip()
        elif display_name.startswith("AU:"):
            role = PluginRole.EFFECT
            display_name = display_name[3:].strip()
        else:
            role = PluginRole.UNKNOWN

        name, vendor = self._parse_name_vendor(display_name)

        return PluginRef(
            id=plugin_id,
            track_id=track_id,
            slot_index=slot_index,
            role=role,
            format=PluginFormat.AU,
            name=name,
            vendor=vendor,
            confidence=Confidence.PROBABLE,
            bypassed=bypassed,
        )

    def _parse_clap_plugin(
        self,
        line: str,
        plugin_id: str,
        track_id: str,
        slot_index: int,
        bypassed: bool,
    ) -> PluginRef | None:
        """Parse <CLAP "CLAP: Name (Vendor)" com.vendor.id..."""
        # Extract quoted name field
        match = re.search(r'<CLAP\s+"([^"]+)"', line)
        if not match:
            return None

        display_name = match.group(1)

        # Determine role
        if display_name.startswith("CLAPi:"):
            role = PluginRole.INSTRUMENT
            display_name = display_name[6:].strip()
        elif display_name.startswith("CLAP:"):
            role = PluginRole.EFFECT
            display_name = display_name[5:].strip()
        else:
            role = PluginRole.UNKNOWN

        name, vendor = self._parse_name_vendor(display_name)

        # Extract CLAP ID from the rest of the line
        clap_id = None
        parts = line.split()
        for part in parts:
            if "." in part and not part.startswith('"'):
                clap_id = part
                break

        identity = PluginIdentity(clap_id=clap_id)

        return PluginRef(
            id=plugin_id,
            track_id=track_id,
            slot_index=slot_index,
            role=role,
            format=PluginFormat.CLAP,
            name=name,
            vendor=vendor,
            confidence=Confidence.PROBABLE,
            identity=identity,
            bypassed=bypassed,
        )

    def _parse_js_plugin(
        self,
        line: str,
        plugin_id: str,
        track_id: str,
        slot_index: int,
        bypassed: bool,
    ) -> PluginRef | None:
        """Parse <JS path/to/effect ..."""
        # Extract path from quoted string
        match = re.search(r'<JS\s+"([^"]*)"', line)
        if not match:
            return None

        path = match.group(1)
        # Extract file name as plugin name
        name = Path(path).stem if path else "JSFX"

        return PluginRef(
            id=plugin_id,
            track_id=track_id,
            slot_index=slot_index,
            role=PluginRole.EFFECT,
            format=PluginFormat.JS,
            name=name,
            vendor="REAPER",
            confidence=Confidence.PROBABLE,
            bypassed=bypassed,
        )

    @staticmethod
    def _parse_name_vendor(display_str: str) -> tuple[str | None, str | None]:
        """Parse 'Name (Vendor)' format.

        The vendor is the last parenthesized group.
        """
        # Find the last parenthesized group
        matches = re.findall(r"\(([^)]+)\)", display_str)
        if matches:
            vendor = matches[-1]
            # Remove the last parenthesized group from display string
            name = re.sub(r"\s*\([^)]*\)\s*$", "", display_str).strip()
            if not name:
                name = display_str
            return name, vendor
        return display_str, None

    def _parse_item_chunk(self) -> list[MediaRef]:
        """Parse an <ITEM ... > chunk and collect media from nested SOURCE blocks."""
        media_refs = []

        # Read lines until closing >
        while self.line_idx < len(self.lines):
            line = self.lines[self.line_idx].strip()

            # Check for end of ITEM block
            if line == ">" or line.startswith("</ITEM"):
                self.line_idx += 1
                break

            # Parse SOURCE (contains FILE)
            if line.startswith("<SOURCE"):
                self.line_idx += 1
                source_media = self._parse_source_chunk()
                for media_ref in source_media:
                    media_refs.append(media_ref)
                continue

            self.line_idx += 1

        return media_refs

    def _parse_source_chunk(self) -> list[MediaRef]:
        """Parse a <SOURCE ... > chunk and collect media from nested blocks."""
        media_refs = []

        # Read lines until closing >
        while self.line_idx < len(self.lines):
            line = self.lines[self.line_idx].strip()

            # Check for end of SOURCE block
            if line == ">" or line.startswith("</SOURCE"):
                self.line_idx += 1
                break

            # Parse FILE references inside SOURCE
            if line.startswith('FILE "'):
                media_ref = self._parse_file_line(line)
                if media_ref:
                    media_refs.append(media_ref)

            # Parse nested SOURCE (SECTION sources can contain other SOURCES)
            if line.startswith("<SOURCE"):
                self.line_idx += 1
                nested_media = self._parse_source_chunk()
                for media_ref in nested_media:
                    media_refs.append(media_ref)
                continue

            self.line_idx += 1

        return media_refs

    def _parse_file_line(self, line: str) -> MediaRef | None:
        """Parse FILE "path" line and resolve path metadata."""
        match = re.search(r'FILE\s+"([^"]*)"', line)
        if not match:
            return None

        path_str = match.group(1)
        try:
            path_obj = Path(path_str)

            # Resolve absolute vs relative
            if path_obj.is_absolute():
                resolved_path = path_obj
            else:
                # Check RECORD_PATH first, then project directory
                if self.record_path:
                    record_dir = self.project_path / self.record_path
                    resolved_path = record_dir / path_str
                else:
                    resolved_path = self.project_path / path_str

            # Normalize for comparison
            resolved_path = resolved_path.resolve(strict=False)

            # Check if file exists and is inside project folder
            exists = False
            inside_project_folder = False
            size_bytes = None

            if resolved_path.exists() and resolved_path.is_file():
                exists = True
                with suppress(OSError, ValueError):
                    size_bytes = resolved_path.stat().st_size

            # Check if inside project folder
            try:
                project_folder = self.project_path.resolve()
                resolved_path.resolve().relative_to(project_folder)
                inside_project_folder = True
            except ValueError:
                inside_project_folder = False

            return MediaRef(
                path=path_str,
                exists=exists,
                inside_project_folder=inside_project_folder,
                size_bytes=size_bytes,
            )
        except Exception:
            # Never raise on odd paths
            return MediaRef(path=path_str)

    @staticmethod
    def _unquote(text: str) -> str | None:
        """Remove surrounding quotes from text."""
        text = text.strip()
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        return text if text else None


# Module-level reader instance
_READER = ReaperReader()
