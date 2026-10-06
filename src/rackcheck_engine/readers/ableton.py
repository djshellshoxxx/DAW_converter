"""Ableton Live .als reader (SPEC-02 section 4.2).

Reads gzip-compressed XML, extracts plugin data, track structure, and media references.
"""

from __future__ import annotations

import contextlib
import gzip
import xml.etree.ElementTree as ET
from pathlib import Path

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

# Maximum decompressed XML held in memory (512 MB; real .als files are far smaller)
_MAX_DECOMPRESSED = 512 * 1024**2

# Stock devices shipped with Ableton (map element tag -> instrument=True/False)
_STOCK_DEVICES: dict[str, bool] = {
    # Instruments
    "Operator": True,
    "Wavetable": True,
    "Sampler": True,
    "OriginalSimpler": True,
    "MultiSampler": True,
    "Collision": True,
    "OriginalSimplerWarp": True,
    # Effects
    "Eq8": False,
    "Compressor2": False,
    "Reverb": False,
    "Delay": False,
    "Vocoder": False,
    "AudioEffectRack": False,
    "MidiEffectRack": False,
    "InstrumentGroupDevice": False,  # Racks are treated as containers
    "AudioEffectGroupDevice": False,
    "MidiEffectGroupDevice": False,
    "DrumGroupDevice": False,
    # Max for Live
    "MxDeviceAudioEffect": False,
    "MxDeviceInstrument": True,
    "MxDeviceMidiEffect": False,
}


class AbletonReader:
    """Reader for Ableton Live .als files."""

    formats = (ProjectFormat.ABLETON_ALS,)
    version = "0.1.0"

    def can_read(self, path: Path) -> Confidence | None:
        """Check if the file looks like an Ableton set."""
        if not path.is_file():
            return None
        try:
            with open(path, "rb") as f:
                head = f.read(2)
            if head == b"\x1f\x8b":
                # Gzip file, likely Ableton
                return Confidence.PROBABLE
        except OSError:
            pass
        return None

    def read(self, path: Path) -> ScanResult:
        """Parse the Ableton .als file and extract project info."""
        try:
            with gzip.open(path, "rb") as gz:
                xml_bytes = gz.read(_MAX_DECOMPRESSED + 1)
        except (OSError, EOFError, gzip.BadGzipFile, Exception) as e:
            # Catch all decompression errors (including zlib.error)
            raise EngineError(
                CORRUPT_PROJECT,
                f"Failed to decompress Ableton file: {e}",
                {"path": str(path)},
            ) from e

        if len(xml_bytes) > _MAX_DECOMPRESSED:
            raise EngineError(
                CORRUPT_PROJECT,
                "Decompressed file exceeds maximum allowed size.",
                {"limit_bytes": _MAX_DECOMPRESSED},
            )

        if not xml_bytes:
            raise EngineError(
                CORRUPT_PROJECT,
                "Decompressed file is empty.",
                {"path": str(path)},
            )

        # Parse XML with XXE protection
        try:
            root = self._parse_xml_safe(xml_bytes)
        except Exception as e:
            raise EngineError(
                CORRUPT_PROJECT,
                f"Failed to parse Ableton XML: {e}",
                {"path": str(path)},
            ) from e

        # Extract basic project info
        daw_version = root.attrib.get("Creator")
        result = ScanResult(
            source=SourceInfo(
                path=str(path),
                format=ProjectFormat.ABLETON_ALS,
                daw_name="Ableton Live",
                daw_version=daw_version,
                reader_version=self.version,
            ),
            project=ProjectInfo(),
        )

        # Extract project-level data
        self._extract_project_info(root, result)

        # Extract tracks and plugins
        self._extract_tracks(root, result)

        # Extract media (samples)
        self._extract_media(root, result, path.parent)

        return result

    def _parse_xml_safe(self, xml_bytes: bytes) -> ET.Element:
        """Parse XML with XXE protection.

        Rejects DOCTYPE/ENTITY/ELEMENT declarations to prevent XXE and billion-laughs attacks.
        """
        # Reject DOCTYPE and ENTITY declarations
        xml_text = xml_bytes.decode("utf-8", errors="replace")
        dangerous_keywords = ("<!DOCTYPE", "<!ENTITY", "<!ELEMENT", "SYSTEM", "PUBLIC")
        for keyword in dangerous_keywords:
            if keyword in xml_text:
                msg = f"Dangerous XML '{keyword}' declaration not allowed (XXE protection)"
                raise ValueError(msg)

        # Parse safely using ElementTree (no DTD expansion)
        # ElementTree's built-in protections prevent XXE by not expanding entities
        root = ET.fromstring(xml_bytes)
        return root

    def _extract_project_info(self, root: ET.Element, result: ScanResult) -> None:
        """Extract project-level information like tempo and time signature."""
        # Look for MasterTrack or MainTrack
        master_track = root.find(".//MasterTrack")
        if master_track is None:
            master_track = root.find(".//MainTrack")
        if master_track is None:
            return

        # Extract tempo from MasterTrack
        tempo_elem = master_track.find(".//Tempo/Manual")
        if tempo_elem is not None:
            value = tempo_elem.attrib.get("Value")
            if value:
                with contextlib.suppress(ValueError):
                    result.project.tempo_bpm = float(value)

        # Extract time signature if feasible
        time_sig_elem = master_track.find(".//TimeSignature")
        if time_sig_elem is not None:
            numerator = time_sig_elem.attrib.get("Numerator")
            denominator = time_sig_elem.attrib.get("Denominator")
            if numerator and denominator:
                with contextlib.suppress(ValueError):
                    numerator_int = int(numerator)
                    denominator_int = int(denominator)
                    result.project.time_signature = f"{numerator_int}/{denominator_int}"

    def _extract_tracks(self, root: ET.Element, result: ScanResult) -> None:
        """Extract tracks and their devices from the project."""
        plugin_id_counter = 0

        # Process all track types
        for track_id_counter, track_elem in enumerate(root.findall(".//Tracks/*"), 1):
            # Ignore PreHearTrack
            if track_elem.tag == "PreHearTrack":
                continue

            track_id = f"t{track_id_counter}"

            # Determine track type
            tag = track_elem.tag
            if tag == "AudioTrack":
                track_type = TrackType.AUDIO
            elif tag == "MidiTrack":
                track_type = TrackType.MIDI
            elif tag == "ReturnTrack":
                track_type = TrackType.RETURN
            elif tag == "GroupTrack":
                track_type = TrackType.GROUP
            elif tag in ("MasterTrack", "MainTrack"):
                track_type = TrackType.MASTER
            else:
                track_type = TrackType.OTHER

            # Extract track name
            track_name = self._extract_track_name(track_elem)

            # Create track reference
            track_ref = TrackRef(id=track_id, name=track_name, type=track_type)
            result.tracks.append(track_ref)

            # Extract devices from this track
            device_chain = track_elem.find(".//DeviceChain")
            if device_chain is not None:
                self._extract_devices(
                    device_chain,
                    result,
                    track_id,
                    track_ref,
                    plugin_id_counter,
                    is_first_device_in_midi_track=(track_type == TrackType.MIDI),
                )

    def _extract_track_name(self, track_elem: ET.Element) -> str | None:
        """Extract track name, preferring EffectiveName over Name."""
        # Try EffectiveName first
        effective_name = track_elem.find("./EffectiveName")
        if effective_name is not None:
            value = effective_name.attrib.get("Value")
            if value:
                return value

        # Fall back to Name
        name_elem = track_elem.find("./Name")
        if name_elem is not None:
            value = name_elem.attrib.get("Value")
            if value:
                return value

        return None

    def _extract_devices(
        self,
        device_chain: ET.Element,
        result: ScanResult,
        track_id: str,
        track_ref: TrackRef,
        plugin_id_counter: int,
        is_first_device_in_midi_track: bool = False,
        nested_in: str | None = None,
    ) -> int:
        """Recursively extract devices from a device chain."""
        devices_elem = device_chain.find("./Devices")
        if devices_elem is None:
            return plugin_id_counter

        for idx, device_elem in enumerate(devices_elem):
            plugin_id_counter += 1
            plugin_id = f"p{plugin_id_counter}"

            # These native Ableton devices explicitly connect a project to external
            # hardware. Preserve the containing track ID for the readiness report.
            if (device_elem.tag in ("ExternalInstrument", "ExternalAudioEffect")
                    and track_id not in result.external_hardware_tracks):
                result.external_hardware_tracks.append(track_id)

            # Check for nested racks
            if self._is_rack(device_elem.tag):
                plugin_id_counter = self._process_rack(
                    device_elem, result, track_id, plugin_id_counter, plugin_id
                )
                continue

            # Extract plugin info
            plugin_ref = self._extract_plugin(
                device_elem,
                plugin_id,
                track_id,
                idx,
                is_first_device_in_midi_track=(idx == 0 and is_first_device_in_midi_track),
                nested_in=nested_in,
            )
            if plugin_ref:
                result.plugins.append(plugin_ref)
                track_ref.devices.append(plugin_id)

        return plugin_id_counter

    def _is_rack(self, tag: str) -> bool:
        """Check if the element is a rack/container device."""
        return tag in (
            "InstrumentGroupDevice",
            "AudioEffectGroupDevice",
            "MidiEffectGroupDevice",
            "DrumGroupDevice",
        )

    def _process_rack(
        self,
        rack_elem: ET.Element,
        result: ScanResult,
        track_id: str,
        plugin_id_counter: int,
        rack_plugin_id: str,
    ) -> int:
        """Process a rack and its nested devices."""
        # Add the rack itself as a stock device
        bypassed = self._extract_bypass_state(rack_elem)

        rack_plugin = PluginRef(
            id=rack_plugin_id,
            track_id=track_id,
            slot_index=None,
            role=PluginRole.UNKNOWN,
            format=PluginFormat.STOCK,
            name=rack_elem.tag,
            vendor="Ableton",
            confidence=Confidence.PROBABLE,
            bypassed=bypassed,
        )
        result.plugins.append(rack_plugin)

        # Process branches (nested device chains) inside the rack
        branches = rack_elem.find(".//Branches")
        if branches is not None:
            for branch in branches:
                device_chain = branch.find("./DeviceChain")
                if device_chain is not None:
                    plugin_id_counter = self._extract_devices(
                        device_chain,
                        result,
                        track_id,
                        TrackRef(id=track_id, name=None, type=TrackType.OTHER),
                        plugin_id_counter,
                        nested_in=rack_plugin_id,
                    )

        return plugin_id_counter

    def _extract_plugin(
        self,
        device_elem: ET.Element,
        plugin_id: str,
        track_id: str,
        slot_index: int,
        is_first_device_in_midi_track: bool = False,
        nested_in: str | None = None,
    ) -> PluginRef | None:
        """Extract plugin information from a device element."""
        tag = device_elem.tag

        # Handle Max for Live devices specially to extract .amxd name
        if tag in ("MxDeviceAudioEffect", "MxDeviceInstrument", "MxDeviceMidiEffect"):
            return self._extract_max_for_live_device(
                device_elem,
                plugin_id,
                track_id,
                slot_index,
                tag,
                nested_in,
            )

        # Handle stock devices
        if tag in _STOCK_DEVICES:
            is_instrument = _STOCK_DEVICES[tag]
            role = PluginRole.INSTRUMENT if is_instrument else PluginRole.EFFECT
            bypassed = self._extract_bypass_state(device_elem)

            return PluginRef(
                id=plugin_id,
                track_id=track_id,
                slot_index=slot_index,
                role=role,
                format=PluginFormat.STOCK,
                name=tag,
                vendor="Ableton",
                confidence=Confidence.PROBABLE,
                bypassed=bypassed,
                nested_in=nested_in,
            )

        # Handle PluginDevice (third-party plugins)
        if tag == "PluginDevice":
            return self._extract_plugin_device(
                device_elem,
                plugin_id,
                track_id,
                slot_index,
                is_first_device_in_midi_track,
                nested_in,
            )

        return None

    def _extract_plugin_device(
        self,
        device_elem: ET.Element,
        plugin_id: str,
        track_id: str,
        slot_index: int,
        is_first_device_in_midi_track: bool,
        nested_in: str | None,
    ) -> PluginRef | None:
        """Extract a third-party plugin from a PluginDevice element."""
        plugin_desc = device_elem.find("./PluginDesc")
        if plugin_desc is None:
            return None

        # Try to extract from VstPluginInfo (VST2)
        vst2_info = plugin_desc.find("./VstPluginInfo")
        if vst2_info is not None:
            return self._extract_vst2_plugin(
                vst2_info,
                plugin_id,
                track_id,
                slot_index,
                is_first_device_in_midi_track,
                nested_in,
                device_elem,
            )

        # Try to extract from Vst3PluginInfo (VST3)
        vst3_info = plugin_desc.find("./Vst3PluginInfo")
        if vst3_info is not None:
            return self._extract_vst3_plugin(
                vst3_info,
                plugin_id,
                track_id,
                slot_index,
                is_first_device_in_midi_track,
                nested_in,
                device_elem,
            )

        # Try to extract from AuPluginInfo (AU)
        au_info = plugin_desc.find("./AuPluginInfo")
        if au_info is not None:
            return self._extract_au_plugin(
                au_info,
                plugin_id,
                track_id,
                slot_index,
                is_first_device_in_midi_track,
                nested_in,
                device_elem,
            )

        return None

    def _extract_vst2_plugin(
        self,
        vst2_info: ET.Element,
        plugin_id: str,
        track_id: str,
        slot_index: int,
        is_first_device_in_midi_track: bool,
        nested_in: str | None,
        device_elem: ET.Element,
    ) -> PluginRef:
        """Extract VST2 plugin information."""
        name = vst2_info.attrib.get("PlugName")
        manufacturer = vst2_info.attrib.get("Manufacturer")
        unique_id_str = vst2_info.attrib.get("UniqueId")

        # Parse unique ID
        unique_id = None
        if unique_id_str:
            with contextlib.suppress(ValueError):
                unique_id = int(unique_id_str)

        bypassed = self._extract_bypass_state(device_elem)

        # Determine role
        role = self._determine_plugin_role(
            PluginFormat.VST2, is_first_device_in_midi_track
        )

        return PluginRef(
            id=plugin_id,
            track_id=track_id,
            slot_index=slot_index,
            role=role,
            format=PluginFormat.VST2,
            name=name,
            vendor=manufacturer,
            confidence=Confidence.PROBABLE,
            bypassed=bypassed,
            nested_in=nested_in,
            identity=PluginIdentity(vst2_unique_id=unique_id),
        )

    def _extract_vst3_plugin(
        self,
        vst3_info: ET.Element,
        plugin_id: str,
        track_id: str,
        slot_index: int,
        is_first_device_in_midi_track: bool,
        nested_in: str | None,
        device_elem: ET.Element,
    ) -> PluginRef:
        """Extract VST3 plugin information."""
        name = vst3_info.attrib.get("Name")

        # Build CID from Uid Fields (4 signed int32 values)
        cid = None
        uid_fields = vst3_info.find("./Uid")
        if uid_fields is not None:
            cid = self._build_vst3_cid(uid_fields)

        bypassed = self._extract_bypass_state(device_elem)

        # Determine role
        device_type = vst3_info.attrib.get("DeviceType")
        role = self._determine_plugin_role_vst3(device_type, is_first_device_in_midi_track)

        return PluginRef(
            id=plugin_id,
            track_id=track_id,
            slot_index=slot_index,
            role=role,
            format=PluginFormat.VST3,
            name=name,
            vendor=None,
            confidence=Confidence.PROBABLE,
            bypassed=bypassed,
            nested_in=nested_in,
            identity=PluginIdentity(vst3_cid=cid),
        )

    def _build_vst3_cid(self, uid_elem: ET.Element) -> str | None:
        """Build 32-char hex CID from 4 signed int32 Uid fields."""
        try:
            # Extract the 4 fields as signed 32-bit integers
            fields = []
            for attr in ["h", "l", "h2", "l2"]:
                val_str = uid_elem.attrib.get(attr)
                if val_str is None:
                    return None
                # Parse as signed int32
                val = int(val_str)
                # Convert to unsigned for hex representation
                val_unsigned = val & 0xFFFFFFFF
                fields.append(val_unsigned)

            # Combine into 128-bit CID as 32 hex chars (uppercase)
            cid = "".join(f"{f:08X}" for f in fields)
            return cid if len(cid) == 32 else None
        except (ValueError, AttributeError):
            return None

    def _extract_au_plugin(
        self,
        au_info: ET.Element,
        plugin_id: str,
        track_id: str,
        slot_index: int,
        is_first_device_in_midi_track: bool,
        nested_in: str | None,
        device_elem: ET.Element,
    ) -> PluginRef:
        """Extract AU plugin information."""
        name = au_info.attrib.get("Name")
        manufacturer_name = au_info.attrib.get("Manufacturer")

        # Extract component codes (as integers)
        au_type = self._extract_au_code("ComponentType", au_info)
        au_subtype = self._extract_au_code("ComponentSubType", au_info)
        au_manufacturer = self._extract_au_code("ComponentManufacturer", au_info)

        bypassed = self._extract_bypass_state(device_elem)

        # Determine role
        role = self._determine_plugin_role(PluginFormat.AU, is_first_device_in_midi_track)

        return PluginRef(
            id=plugin_id,
            track_id=track_id,
            slot_index=slot_index,
            role=role,
            format=PluginFormat.AU,
            name=name,
            vendor=manufacturer_name,
            confidence=Confidence.PROBABLE,
            bypassed=bypassed,
            nested_in=nested_in,
            identity=PluginIdentity(
                au_type=au_type, au_subtype=au_subtype, au_manufacturer=au_manufacturer
            ),
        )

    def _extract_au_code(self, attr_name: str, au_info: ET.Element) -> str | None:
        """Extract a 4-char AU code from an integer attribute."""
        value_str = au_info.attrib.get(attr_name)
        if not value_str:
            return None
        with contextlib.suppress(ValueError):
            value = int(value_str)
            # Convert to 4-char code using bitwise operations
            return self._int_to_4char_code(value)
        return None

    def _int_to_4char_code(self, value: int) -> str:
        """Convert a 32-bit integer to a 4-character code (big-endian)."""
        # Extract bytes in big-endian order
        bytes_list = [
            (value >> 24) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ]
        with contextlib.suppress(Exception):
            return bytes(bytes_list).decode("ascii", errors="replace")
        return None

    def _extract_device_name(self, device_elem: ET.Element) -> str | None:
        """Extract device name if available."""
        name_elem = device_elem.find("./Name")
        if name_elem is not None:
            return name_elem.attrib.get("Value")
        return None

    def _extract_bypass_state(self, device_elem: ET.Element) -> bool | None:
        """Extract bypass state from device's On parameter."""
        on_elem = device_elem.find("./On")
        if on_elem is not None:
            value = on_elem.attrib.get("Value")
            if value is not None:
                # Bypassed if On/Manual Value == "false"
                if value.lower() in ("false", "0"):
                    return True
                elif value.lower() in ("true", "1"):
                    return False
        return None

    def _determine_plugin_role(
        self, fmt: PluginFormat, is_first_in_midi_track: bool
    ) -> PluginRole:
        """Determine plugin role based on format and position."""
        if (
            fmt in (PluginFormat.VST2, PluginFormat.VST3, PluginFormat.AU, PluginFormat.CLAP)
            and is_first_in_midi_track
        ):
            # Heuristic: first device in a MIDI track is likely an instrument
            return PluginRole.INSTRUMENT
        return PluginRole.UNKNOWN

    def _determine_plugin_role_vst3(
        self, device_type: str | None, is_first_in_midi_track: bool
    ) -> PluginRole:
        """Determine VST3 plugin role from DeviceType if available."""
        if device_type:
            if "instrument" in device_type.lower():
                return PluginRole.INSTRUMENT
            elif "effect" in device_type.lower():
                return PluginRole.EFFECT

        # Fallback to positional heuristic
        if is_first_in_midi_track:
            return PluginRole.INSTRUMENT
        return PluginRole.UNKNOWN

    def _extract_max_for_live_device(
        self,
        device_elem: ET.Element,
        plugin_id: str,
        track_id: str,
        slot_index: int,
        tag: str,
        nested_in: str | None,
    ) -> PluginRef:
        """Extract Max for Live device information from Mx* element.

        Extracts the .amxd file name from nested FileRef and uses it as the plugin name.
        If no .amxd name is found, uses the element tag as the name.
        """
        # Determine role based on device type
        role = (
            PluginRole.INSTRUMENT
            if tag == "MxDeviceInstrument"
            else PluginRole.EFFECT
        )

        # Try to extract .amxd file name from FileRef
        amxd_name = self._extract_amxd_filename(device_elem)
        name = amxd_name if amxd_name else tag

        bypassed = self._extract_bypass_state(device_elem)

        return PluginRef(
            id=plugin_id,
            track_id=track_id,
            slot_index=slot_index,
            role=role,
            format=PluginFormat.STOCK,
            name=name,
            vendor=None,
            confidence=Confidence.PROBABLE,
            bypassed=bypassed,
            nested_in=nested_in,
            identity=PluginIdentity(file_hint=amxd_name),
        )

    def _extract_amxd_filename(self, device_elem: ET.Element) -> str | None:
        """Extract .amxd file name from FileRef elements within a device."""
        # Look for FileRef elements anywhere in the device
        for file_ref in device_elem.findall(".//FileRef"):
            # Try Path first (absolute path, Live 11/12)
            path_elem = file_ref.find("./Path")
            if path_elem is not None:
                path_value = path_elem.attrib.get("Value")
                if path_value and path_value.endswith(".amxd"):
                    return Path(path_value).name
            # Try RelativePath (Live 10+)
            rel_path_elem = file_ref.find("./RelativePath")
            if rel_path_elem is not None:
                rel_path_value = rel_path_elem.attrib.get("Value")
                if rel_path_value and rel_path_value.endswith(".amxd"):
                    return Path(rel_path_value).name
        return None

    def _extract_media(
        self, root: ET.Element, result: ScanResult, als_folder: Path
    ) -> None:
        """Extract media references (samples) from SampleRef > FileRef elements."""
        seen_paths: set[str] = set()

        # Find all SampleRef > FileRef combinations throughout the document
        for sample_ref in root.findall(".//SampleRef"):
            file_ref = sample_ref.find("./FileRef")
            if file_ref is None:
                continue

            # Extract path from FileRef
            resolved_path = self._resolve_file_ref_path(file_ref, als_folder)
            if resolved_path is None:
                continue

            # Dedupe by path
            path_str = str(resolved_path)
            if path_str in seen_paths:
                continue
            seen_paths.add(path_str)

            # Check if file exists and is inside project folder
            try:
                exists = resolved_path.exists()
                inside_project = self._is_inside_folder(resolved_path, als_folder)
                size_bytes = resolved_path.stat().st_size if exists else None
            except (OSError, ValueError):
                # Never raise on odd paths
                exists = False
                inside_project = False
                size_bytes = None

            media_ref = MediaRef(
                path=path_str,
                exists=exists,
                inside_project_folder=inside_project,
                size_bytes=size_bytes,
            )
            result.media.append(media_ref)

    def _resolve_file_ref_path(self, file_ref: ET.Element, als_folder: Path) -> Path | None:
        """Resolve a FileRef to an absolute path.

        Prefers absolute Path@Value (Live 11/12), else builds from RelativePath@Value
        (Live 10+). For Live 9 style RelativePath > RelativePathElement@Dir, joins Dir values.
        """
        # Try absolute path first (Live 11/12)
        path_elem = file_ref.find("./Path")
        if path_elem is not None:
            path_value = path_elem.attrib.get("Value")
            if path_value:
                try:
                    return Path(path_value)
                except (ValueError, TypeError):
                    pass

        # Try simple RelativePath (Live 10+)
        rel_path_elem = file_ref.find("./RelativePath")
        if rel_path_elem is not None:
            rel_path_value = rel_path_elem.attrib.get("Value")
            if rel_path_value:
                try:
                    return als_folder / rel_path_value
                except (ValueError, TypeError):
                    pass

        # Try Live 9 style RelativePath > RelativePathElement@Dir
        rel_path_parent = file_ref.find("./RelativePath")
        if rel_path_parent is not None:
            dir_parts = []
            for rel_path_elem in rel_path_parent.findall("./RelativePathElement"):
                dir_value = rel_path_elem.attrib.get("Dir")
                if dir_value:
                    dir_parts.append(dir_value)
            if dir_parts:
                try:
                    return als_folder / Path(*dir_parts)
                except (ValueError, TypeError):
                    pass

        return None

    def _is_inside_folder(self, path: Path, folder: Path) -> bool:
        """Check if path is inside folder."""
        try:
            path.resolve().relative_to(folder.resolve())
            return True
        except (ValueError, RuntimeError):
            return False
