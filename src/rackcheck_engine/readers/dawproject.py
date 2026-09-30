"""DAWproject (.dawproject) reader - open Bitwig format (MIT).

Container: zip with project.xml (content) and metadata.xml (metadata).
Opens read-only, in-memory (never extracts to disk). Rejects XXE/billion laughs attacks.
Confidence: CONFIRMED (documented format).
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

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
from ..safety import check_zip


class DawprojectReader:
    """Reads DAWproject (.dawproject) zip archives."""

    formats: tuple[ProjectFormat, ...] = (ProjectFormat.DAWPROJECT,)
    version: str = "0.1.0"

    def can_read(self, path: Path) -> Confidence | None:
        """Check if this is a readable DAWproject file."""
        if not path.is_file():
            return None
        try:
            with zipfile.ZipFile(path) as zf:
                check_zip(zf)
                names = {n.replace("\\", "/") for n in zf.namelist()}
                if "project.xml" in names and "metadata.xml" in names:
                    return Confidence.CONFIRMED
        except (zipfile.BadZipFile, OSError, EngineError):
            pass
        return None

    def read(self, path: Path) -> ScanResult:
        """Parse project.xml from the .dawproject zip into the common data model."""
        try:
            with zipfile.ZipFile(path) as zf:
                check_zip(zf)
                try:
                    project_xml_bytes = zf.read("project.xml")
                except KeyError:
                    raise EngineError(
                        CORRUPT_PROJECT, "Missing project.xml in archive"
                    ) from None
        except (zipfile.BadZipFile, OSError) as exc:
            raise EngineError(
                CORRUPT_PROJECT, f"Failed to read zip archive: {exc}"
            ) from exc
        except EngineError:
            raise

        # Parse XML with XXE/billion laughs protection
        try:
            root = self._parse_xml_safe(project_xml_bytes)
        except (ET.ParseError, ValueError) as exc:
            raise EngineError(
                CORRUPT_PROJECT, f"Failed to parse project.xml: {exc}"
            ) from exc

        # Extract basic info
        source = SourceInfo(
            path=str(path),
            format=ProjectFormat.DAWPROJECT,
            daw_name=self._extract_daw_name(root),
            daw_version=self._extract_daw_version(root),
            reader_version=self.version,
        )

        project = self._extract_project_info(root)
        tracks, track_by_id = self._extract_tracks(root)
        plugins = self._extract_plugins(root, track_by_id)
        media = self._extract_media(root)

        return ScanResult(
            source=source,
            project=project,
            tracks=tracks,
            plugins=plugins,
            media=media,
        )

    def _parse_xml_safe(self, xml_bytes: bytes) -> ET.Element:
        """Parse XML with XXE/entity/DOCTYPE protections.

        Uses stdlib only but applies defensive checks:
        - Rejects DOCTYPE declarations (prevents external entity declaration)
        - Rejects ENTITY declarations (prevents entity expansion)
        - Rejects external DTD references
        """
        # Reject DOCTYPE declarations (prevents XXE entirely)
        xml_text = xml_bytes.decode("utf-8", errors="replace")
        if "<!DOCTYPE" in xml_text or "<!ENTITY" in xml_text:
            raise ValueError("DOCTYPE and ENTITY declarations are not allowed")
        if "SYSTEM" in xml_text and "<!DOCTYPE" in xml_text:
            raise ValueError("External DTD references are not allowed")

        # Create a parser with limits on entity expansion
        parser = ET.XMLParser()

        try:
            root = ET.fromstring(xml_bytes, parser=parser)
        except ET.ParseError as exc:
            raise ValueError(f"XML parse error: {exc}") from exc

        return root

    def _extract_daw_name(self, root: ET.Element) -> str | None:
        """Extract Application name."""
        app = root.find(".//Application")
        if app is not None:
            name = app.get("name")
            if name:
                return name
        return None

    def _extract_daw_version(self, root: ET.Element) -> str | None:
        """Extract Application version."""
        app = root.find(".//Application")
        if app is not None:
            version = app.get("version")
            if version:
                return version
        return None

    def _extract_project_info(self, root: ET.Element) -> ProjectInfo:
        """Extract project-level info: tempo, time signature."""
        info = ProjectInfo()

        # Find Transport element for tempo and time signature
        transport = root.find(".//Transport")
        if transport is not None:
            # Tempo
            tempo_elem = transport.find("Tempo")
            if tempo_elem is not None:
                try:
                    tempo_str = tempo_elem.get("value")
                    if tempo_str:
                        info.tempo_bpm = float(tempo_str)
                except (ValueError, TypeError):
                    pass

            # TimeSignature
            ts_elem = transport.find("TimeSignature")
            if ts_elem is not None:
                try:
                    numerator = ts_elem.get("numerator")
                    denominator = ts_elem.get("denominator")
                    if numerator and denominator:
                        info.time_signature = f"{numerator}/{denominator}"
                except (ValueError, TypeError):
                    pass

        return info

    def _extract_tracks(self, root: ET.Element) -> tuple[list[TrackRef], dict[str, str]]:
        """Extract tracks from Structure element. Returns (tracks, track_by_id dict)."""
        tracks = []
        track_by_id = {}
        track_counter = [0]  # Use list to allow modification in nested function

        structure = root.find(".//Structure")
        if structure is None:
            return tracks, track_by_id

        def extract_track_recursive(track_elem: ET.Element) -> None:
            """Recursively extract tracks, handling nesting."""
            track_counter[0] += 1
            track_id = f"t{track_counter[0]}"
            track_ref = self._parse_track(track_elem, track_id)
            tracks.append(track_ref)
            track_by_id[track_id] = track_ref.name or ""

            # Handle nested tracks (folders/groups)
            for nested_elem in track_elem.findall("Track"):
                extract_track_recursive(nested_elem)

        for track_elem in structure.findall("Track"):
            extract_track_recursive(track_elem)

        return tracks, track_by_id

    def _parse_track(self, track_elem: ET.Element, track_id: str) -> TrackRef:
        """Parse a single Track element into a TrackRef."""
        name = track_elem.get("name")

        # Determine track type
        # DAWproject can have contentType attribute: audio, notes, master, return, group, etc.
        content_type = track_elem.get("contentType", "audio").lower()
        track_type = self._map_track_type(content_type, track_elem)

        # Find Channel element to get devices
        devices = []
        channel = track_elem.find("Channel")
        if channel is not None:
            devices = self._extract_channel_devices(channel)

        return TrackRef(id=track_id, name=name, type=track_type, devices=devices)

    def _map_track_type(self, content_type: str, track_elem: ET.Element) -> TrackType:
        """Map DAWproject contentType to TrackType."""
        if content_type == "master":
            return TrackType.MASTER
        elif content_type in ("audio", "audio-track"):
            return TrackType.AUDIO
        elif content_type in ("midi", "notes", "midi-track"):
            return TrackType.MIDI
        elif content_type in ("return", "return-track"):
            return TrackType.RETURN
        elif content_type in ("group", "folder", "group-track"):
            # Check if there are nested tracks (folder behavior)
            if track_elem.find("Track") is not None:
                return TrackType.FOLDER
            return TrackType.GROUP
        else:
            # Check Channel role if contentType doesn't help
            channel = track_elem.find("Channel")
            if channel is not None:
                role = channel.get("role", "").lower()
                if role in ("master", "masterTrack"):
                    return TrackType.MASTER
                elif role in ("return", "returnTrack"):
                    return TrackType.RETURN
                elif role in ("submix", "group"):
                    return TrackType.GROUP
            return TrackType.OTHER

    def _extract_channel_devices(self, channel: ET.Element) -> list[str]:
        """Extract device IDs from a Channel element's Devices."""
        devices = []
        devices_elem = channel.find("Devices")
        if devices_elem is None:
            return devices

        for _device_elem in devices_elem:
            device_id = f"p{len(devices) + 1}"  # Simple sequential numbering
            devices.append(device_id)

        return devices

    def _extract_plugins(
        self, root: ET.Element, track_by_id: dict[str, str]
    ) -> list[PluginRef]:
        """Extract all plugins from Structure > Track > Channel > Devices."""
        plugins = []
        plugin_id_counter = [0]  # Use list to allow modification in nested function

        structure = root.find(".//Structure")
        if structure is None:
            return plugins

        def extract_plugins_recursive(track_elem: ET.Element, track_counter: list[int]) -> None:
            """Recursively extract plugins from tracks."""
            track_counter[0] += 1
            track_id = f"t{track_counter[0]}"

            channel = track_elem.find("Channel")
            if channel is not None:
                plugins_in_channel = self._extract_devices(channel, track_id, plugin_id_counter[0])
                plugins.extend(plugins_in_channel)
                plugin_id_counter[0] += len(plugins_in_channel)

            # Handle nested tracks
            for nested_elem in track_elem.findall("Track"):
                extract_plugins_recursive(nested_elem, track_counter)

        track_counter = [0]
        for track_elem in structure.findall("Track"):
            extract_plugins_recursive(track_elem, track_counter)

        return plugins

    def _extract_devices(
        self, channel: ET.Element, track_id: str, start_index: int
    ) -> list[PluginRef]:
        """Extract device elements from a Channel."""
        plugins = []
        devices_elem = channel.find("Devices")
        if devices_elem is None:
            return plugins

        for slot_index, device_elem in enumerate(devices_elem):
            plugin_id = f"p{start_index + slot_index + 1}"
            tag = device_elem.tag

            # Determine plugin type and format
            if tag in ("Vst2Plugin", "Vst3Plugin", "ClapPlugin", "AuPlugin"):
                plugin_ref = self._parse_third_party_plugin(
                    device_elem, plugin_id, track_id, slot_index, tag
                )
            elif tag in (
                "BuiltinDevice",
                "Equalizer",
                "Compressor",
                "NoiseGate",
                "Limiter",
                "Device",
            ):
                plugin_ref = self._parse_builtin_device(
                    device_elem, plugin_id, track_id, slot_index, tag
                )
            else:
                # Unknown device type
                plugin_ref = self._parse_unknown_device(
                    device_elem, plugin_id, track_id, slot_index, tag
                )

            if plugin_ref is not None:
                plugins.append(plugin_ref)

        return plugins

    def _parse_third_party_plugin(
        self,
        device_elem: ET.Element,
        plugin_id: str,
        track_id: str,
        slot_index: int,
        tag: str,
    ) -> PluginRef | None:
        """Parse VST2/3, CLAP, or AU plugin element."""
        device_name = device_elem.get("deviceName")
        device_vendor = device_elem.get("deviceVendor")
        device_id = device_elem.get("deviceID")
        plugin_version = device_elem.get("pluginVersion")
        device_role = device_elem.get("deviceRole", "").lower()

        # Determine format
        format_map = {
            "Vst2Plugin": PluginFormat.VST2,
            "Vst3Plugin": PluginFormat.VST3,
            "ClapPlugin": PluginFormat.CLAP,
            "AuPlugin": PluginFormat.AU,
        }
        plugin_format = format_map.get(tag, PluginFormat.UNKNOWN)

        # Determine role
        role = self._map_device_role(device_role)

        # Parse identity based on format
        identity = self._parse_plugin_identity(plugin_format, device_id, device_vendor)

        # Check bypass status
        bypassed = self._is_bypassed(device_elem)

        return PluginRef(
            id=plugin_id,
            track_id=track_id,
            slot_index=slot_index,
            role=role,
            format=plugin_format,
            name=device_name,
            vendor=device_vendor,
            confidence=Confidence.CONFIRMED,
            version_in_project=plugin_version,
            identity=identity,
            bypassed=bypassed,
        )

    def _parse_builtin_device(
        self, device_elem: ET.Element, plugin_id: str, track_id: str, slot_index: int, tag: str
    ) -> PluginRef | None:
        """Parse built-in device (stock plugin)."""
        device_name = device_elem.get("deviceName") or tag

        # Map tag to display name for stock devices
        stock_names = {
            "Equalizer": "Equalizer",
            "Compressor": "Compressor",
            "NoiseGate": "Noise Gate",
            "Limiter": "Limiter",
            "BuiltinDevice": device_name or "Built-in Device",
            "Device": device_name or "Built-in Device",
        }
        display_name = stock_names.get(tag, device_name)

        role = self._map_device_role(device_elem.get("deviceRole", "").lower())
        bypassed = self._is_bypassed(device_elem)

        return PluginRef(
            id=plugin_id,
            track_id=track_id,
            slot_index=slot_index,
            role=role,
            format=PluginFormat.STOCK,
            name=display_name,
            vendor=None,
            confidence=Confidence.CONFIRMED,
            identity=PluginIdentity(),
            bypassed=bypassed,
        )

    def _parse_unknown_device(
        self, device_elem: ET.Element, plugin_id: str, track_id: str, slot_index: int, tag: str
    ) -> PluginRef | None:
        """Parse unknown device type."""
        device_name = device_elem.get("deviceName", tag)
        device_vendor = device_elem.get("deviceVendor")
        role = self._map_device_role(device_elem.get("deviceRole", "").lower())
        bypassed = self._is_bypassed(device_elem)

        return PluginRef(
            id=plugin_id,
            track_id=track_id,
            slot_index=slot_index,
            role=role,
            format=PluginFormat.UNKNOWN,
            name=device_name,
            vendor=device_vendor,
            confidence=Confidence.HEURISTIC,
            identity=PluginIdentity(),
            bypassed=bypassed,
        )

    def _parse_plugin_identity(
        self, format: PluginFormat, device_id: str | None, device_vendor: str | None
    ) -> PluginIdentity:
        """Parse plugin identity from deviceID based on format."""
        identity = PluginIdentity()

        if not device_id:
            return identity

        if format == PluginFormat.VST3:
            # VST3 CID: 32 hex chars, uppercase
            if len(device_id) == 32:
                identity.vst3_cid = device_id.upper()
        elif format == PluginFormat.VST2:
            # VST2 unique ID: typically 4 chars or numeric
            try:
                # Try parsing as int
                unique_id = int(device_id)
                identity.vst2_unique_id = unique_id
            except ValueError:
                # Might be 4-char code; store as is for now
                pass
        elif format == PluginFormat.CLAP:
            # CLAP ID: reverse-DNS string
            identity.clap_id = device_id
        elif format == PluginFormat.AU:
            # AU codes: typically three 4-char codes separated by slashes or colons
            # Format varies; store as is
            pass

        return identity

    def _map_device_role(self, device_role: str) -> PluginRole:
        """Map deviceRole attribute to PluginRole."""
        if device_role in ("instrument", "synth", "generator"):
            return PluginRole.INSTRUMENT
        elif device_role in ("audioFX", "effect", "noteFX", "midiEffect"):
            return PluginRole.EFFECT
        else:
            return PluginRole.UNKNOWN

    def _is_bypassed(self, device_elem: ET.Element) -> bool | None:
        """Check if device has Enabled element with value='false' (bypassed = True)."""
        enabled_elem = device_elem.find("Enabled")
        if enabled_elem is not None:
            enabled_attr = enabled_elem.get("value")
            if enabled_attr is not None:
                return enabled_attr.lower() == "false"
        return None

    def _extract_media(self, root: ET.Element) -> list[MediaRef]:
        """Extract media file references from Media element."""
        media = []

        media_elem = root.find(".//Media")
        if media_elem is None:
            return media

        for audio_elem in media_elem.findall("Audio"):
            file_elem = audio_elem.find("File")
            if file_elem is not None:
                path = file_elem.get("path")
                if path:
                    media.append(MediaRef(path=path))

        return media
