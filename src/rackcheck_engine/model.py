"""Common data model every reader outputs (SPEC-02 section 3).

The full user-facing report (SPEC-02 section 10.2) is a superset built by the report
builder on top of this. Unknown values stay ``None``; readers never guess (SPEC-01 P4).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Confidence(StrEnum):
    CONFIRMED = "confirmed"  # documented or well-verified structure
    PROBABLE = "probable"  # reverse-engineered structure verified against fixtures
    HEURISTIC = "heuristic"  # string scanning or extension only


class TrackType(StrEnum):
    INSTRUMENT = "instrument"
    AUDIO = "audio"
    MIDI = "midi"
    RETURN = "return"
    GROUP = "group"
    MASTER = "master"
    FOLDER = "folder"
    OTHER = "other"


class PluginRole(StrEnum):
    INSTRUMENT = "instrument"
    EFFECT = "effect"
    UNKNOWN = "unknown"


class PluginFormat(StrEnum):
    VST2 = "vst2"
    VST3 = "vst3"
    AU = "au"
    AAX = "aax"
    CLAP = "clap"
    STOCK = "stock"
    JS = "js"
    LV2 = "lv2"
    UNKNOWN = "unknown"


@dataclass
class PluginIdentity:
    vst2_unique_id: int | None = None
    vst3_cid: str | None = None  # 32 hex chars, uppercase
    au_type: str | None = None
    au_subtype: str | None = None
    au_manufacturer: str | None = None
    clap_id: str | None = None
    aax_ids: dict[str, str] | None = None
    file_hint: str | None = None


@dataclass
class SourceInfo:
    path: str
    format: str
    daw_name: str | None = None
    daw_version: str | None = None
    reader_version: str | None = None


@dataclass
class ProjectInfo:
    tempo_bpm: float | None = None
    time_signature: str | None = None
    key: str | None = None
    sample_rate: int | None = None
    length_seconds: float | None = None


@dataclass
class TrackRef:
    id: str
    name: str | None
    type: TrackType
    devices: list[str] = field(default_factory=list)


@dataclass
class PluginRef:
    id: str
    track_id: str | None
    slot_index: int | None
    role: PluginRole
    format: PluginFormat
    name: str | None
    vendor: str | None
    confidence: Confidence
    version_in_project: str | None = None
    identity: PluginIdentity = field(default_factory=PluginIdentity)
    bypassed: bool | None = None
    nested_in: str | None = None


@dataclass
class MediaRef:
    path: str
    exists: bool | None = None
    inside_project_folder: bool | None = None
    size_bytes: int | None = None


@dataclass
class ScanResult:
    source: SourceInfo
    project: ProjectInfo = field(default_factory=ProjectInfo)
    tracks: list[TrackRef] = field(default_factory=list)
    plugins: list[PluginRef] = field(default_factory=list)
    media: list[MediaRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Reader evidence used by report enrichment; kept out of the stable ScanResult
    # JSON shape until its public schema is versioned.
    external_hardware_tracks: list[str] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("external_hardware_tracks", None)
        return data

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
