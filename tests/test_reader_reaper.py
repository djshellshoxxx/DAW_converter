"""Tests for the REAPER reader (SPEC-02 section 4.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rackcheck_engine.errors import CORRUPT_PROJECT, EngineError
from rackcheck_engine.model import (
    Confidence,
    PluginFormat,
    PluginRole,
    TrackType,
)
from rackcheck_engine.readers.reaper import ReaperReader


@pytest.fixture
def reader() -> ReaperReader:
    """Create a REAPER reader instance."""
    return ReaperReader()


def test_reader_has_correct_metadata(reader: ReaperReader):
    """Test reader protocol compliance."""
    assert reader.version == "0.1.0"
    assert len(reader.formats) > 0


def test_minimal_rpp_project(tmp_path: Path, reader: ReaperReader):
    """Test reading a minimal valid .rpp file."""
    rpp_file = tmp_path / "minimal.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "TEMPO 120 0 0\n"
        "SAMPLERATE 48000\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert result.source.format == "reaper_rpp"
    assert result.source.daw_name == "REAPER"
    assert result.source.daw_version == "7.22/win64"
    assert result.project.tempo_bpm == 120.0
    assert result.project.sample_rate == 48000


def test_vst3_plugin_with_vendor(tmp_path: Path, reader: ReaperReader):
    """Test parsing VST3 plugin with vendor name."""
    rpp_file = tmp_path / "vst3.rpp"
    guid = "ABCD1234ABCD1234ABCD1234ABCD1234"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "TEMPO 120 0 0\n"
        "SAMPLERATE 48000\n"
        "<TRACK\n"
        '  NAME "Track 1"\n'
        "  <FXCHAIN\n"
        f'    <VST "VST3: Serum (Xfer Records)" Serum.vst3 0 "" 12345{{{guid}}}\n'
        "    >\n"
        "  >\n"
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.tracks) == 1
    assert result.tracks[0].name == "Track 1"
    assert len(result.plugins) == 1

    plugin = result.plugins[0]
    assert plugin.name == "Serum"
    assert plugin.vendor == "Xfer Records"
    assert plugin.format == PluginFormat.VST3
    assert plugin.role == PluginRole.EFFECT
    assert plugin.identity.vst3_cid == "ABCD1234ABCD1234ABCD1234ABCD1234"
    assert plugin.confidence == Confidence.PROBABLE
    assert plugin.bypassed is False


def test_vst2_plugin_with_id(tmp_path: Path, reader: ReaperReader):
    """Test parsing VST2 plugin with unique ID."""
    rpp_file = tmp_path / "vst2.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        "<FXCHAIN\n"
        '  <VST "VST: Nexus (reFX)" Nexus.dll 0 "" 1397703755\n'
        "  >\n"
        ">\n"
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    plugin = result.plugins[0]
    assert plugin.name == "Nexus"
    assert plugin.vendor == "reFX"
    assert plugin.format == PluginFormat.VST2
    assert plugin.identity.vst2_unique_id == 1397703755


def test_au_plugin(tmp_path: Path, reader: ReaperReader):
    """Test parsing AU plugin."""
    rpp_file = tmp_path / "au.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        "<FXCHAIN\n"
        '  <AU "AU: Pro-Q 3 (FabFilter)" "FabFilter: Pro-Q 3" "" 0 0\n'
        "  >\n"
        ">\n"
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    plugin = result.plugins[0]
    assert plugin.name == "Pro-Q 3"
    assert plugin.vendor == "FabFilter"
    assert plugin.format == PluginFormat.AU


def test_clap_plugin(tmp_path: Path, reader: ReaperReader):
    """Test parsing CLAP plugin."""
    rpp_file = tmp_path / "clap.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        "<FXCHAIN\n"
        '  <CLAP "CLAP: Surge XT (Surge Synth Team)" com.surge-synth-team.surge-xt 0\n'
        "  >\n"
        ">\n"
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    plugin = result.plugins[0]
    assert plugin.name == "Surge XT"
    assert plugin.vendor == "Surge Synth Team"
    assert plugin.format == PluginFormat.CLAP
    assert plugin.identity.clap_id == "com.surge-synth-team.surge-xt"


def test_js_plugin(tmp_path: Path, reader: ReaperReader):
    """Test parsing JSFX (JS) plugin."""
    rpp_file = tmp_path / "js.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        "<FXCHAIN\n"
        '  <JS "Effects/ReaComp.jsfx" ""\n'
        "  >\n"
        ">\n"
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    plugin = result.plugins[0]
    assert plugin.name == "ReaComp"
    assert plugin.vendor == "REAPER"
    assert plugin.format == PluginFormat.JS


def test_instrument_vst3i_role(tmp_path: Path, reader: ReaperReader):
    """Test instrument role detection for VST3i."""
    rpp_file = tmp_path / "instrument.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        "<FXCHAIN\n"
        '  <VST "VST3i: Serum (Xfer Records)" Serum.vst3 0 "" 12345{GUID}\n'
        "  >\n"
        ">\n"
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    plugin = result.plugins[0]
    assert plugin.role == PluginRole.INSTRUMENT


def test_bypass_state(tmp_path: Path, reader: ReaperReader):
    """Test bypass state parsing."""
    rpp_file = tmp_path / "bypass.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        "<FXCHAIN\n"
        "  BYPASS 1 0 0\n"
        '  <VST "VST3: Serum (Xfer Records)" Serum.vst3 0 "" 12345{GUID}\n'
        "  >\n"
        ">\n"
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    plugin = result.plugins[0]
    assert plugin.bypassed is True


def test_not_bypassed_state(tmp_path: Path, reader: ReaperReader):
    """Test not-bypassed state."""
    rpp_file = tmp_path / "not_bypassed.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        "<FXCHAIN\n"
        "  BYPASS 0 0 0\n"
        '  <VST "VST3: Serum (Xfer Records)" Serum.vst3 0 "" 12345{GUID}\n'
        "  >\n"
        ">\n"
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    plugin = result.plugins[0]
    assert plugin.bypassed is False


def test_multiple_instances_same_plugin(tmp_path: Path, reader: ReaperReader):
    """Test counting multiple instances of the same plugin."""
    rpp_file = tmp_path / "multi.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        "<FXCHAIN\n"
        '  <VST "VST3: Serum (Xfer Records)" Serum.vst3 0 "" 12345{GUID}\n'
        "  >\n"
        '  <VST "VST3: Serum (Xfer Records)" Serum.vst3 0 "" 12345{GUID}\n'
        "  >\n"
        '  <VST "VST3: Serum (Xfer Records)" Serum.vst3 0 "" 12345{GUID}\n'
        "  >\n"
        ">\n"
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.plugins) == 3
    for i, plugin in enumerate(result.plugins):
        assert plugin.name == "Serum"
        assert plugin.slot_index == i


def test_master_fxchain(tmp_path: Path, reader: ReaperReader):
    """Test parsing master FX chain."""
    rpp_file = tmp_path / "master_fx.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        "</TRACK>\n"
        "<MASTERFXLIST\n"
        '  <VST "VST3: FabFilter Pro-L 2 (FabFilter)" ProL.vst3 0 "" 12345{GUID}\n'
        "  >\n"
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.plugins) == 1
    plugin = result.plugins[0]
    assert plugin.track_id == "master"
    assert plugin.name == "FabFilter Pro-L 2"


def test_unicode_track_names(tmp_path: Path, reader: ReaperReader):
    """Test parsing unicode track names."""
    rpp_file = tmp_path / "unicode.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        '  NAME "Vocals - Résumé"\n'
        ">\n"
        "<TRACK\n"
        '  NAME "ドラム"\n'
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.tracks) == 2
    assert result.tracks[0].name == "Vocals - Résumé"
    assert result.tracks[1].name == "ドラム"


def test_media_file_references(tmp_path: Path, reader: ReaperReader):
    """Test parsing media file references."""
    rpp_file = tmp_path / "media.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        '<SOURCE SECTION\n'
        '  FILE "Audio/kick.wav"\n'
        '  FILE "Audio/snare.wav"\n'
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.media) >= 2
    paths = [m.path for m in result.media]
    assert "Audio/kick.wav" in paths
    assert "Audio/snare.wav" in paths


def test_time_signature(tmp_path: Path, reader: ReaperReader):
    """Test parsing time signature."""
    rpp_file = tmp_path / "timesig.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "TIMESIG 3 4 0 0\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert result.project.time_signature == "3/4"


def test_track_folder_type(tmp_path: Path, reader: ReaperReader):
    """Test parsing folder/group track type via ISBUS."""
    rpp_file = tmp_path / "folder.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        '  NAME "Folder"\n'
        "  ISBUS 1 0 0 0 0 0\n"
        "</TRACK>\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.tracks) == 1
    assert result.tracks[0].type == TrackType.FOLDER


def test_corrupt_input_raises_engine_error(tmp_path: Path, reader: ReaperReader):
    """Test that corrupt/unreadable input raises EngineError with CORRUPT_PROJECT."""
    rpp_file = tmp_path / "nonexistent.rpp"

    with pytest.raises(EngineError) as exc_info:
        reader.read(rpp_file)

    assert exc_info.value.code == CORRUPT_PROJECT


def test_plugin_slot_indices(tmp_path: Path, reader: ReaperReader):
    """Test that plugin slot indices are correct."""
    rpp_file = tmp_path / "slots.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        "<FXCHAIN\n"
        '  <VST "VST3: Plugin1 (Vendor)" P1.vst3 0 "" 111{GUID1}\n'
        "  >\n"
        '  <VST "VST3: Plugin2 (Vendor)" P2.vst3 0 "" 222{GUID2}\n'
        "  >\n"
        '  <VST "VST3: Plugin3 (Vendor)" P3.vst3 0 "" 333{GUID3}\n'
        "  >\n"
        ">\n"
        ">\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.plugins) == 3
    for i, plugin in enumerate(result.plugins):
        assert plugin.slot_index == i


def test_plugin_track_assignment(tmp_path: Path, reader: ReaperReader):
    """Test that plugins are assigned to correct tracks."""
    rpp_file = tmp_path / "track_assign.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        '  NAME "Track A"\n'
        "  <FXCHAIN\n"
        '    <VST "VST3: PluginA (Vendor)" PA.vst3 0 "" 111{GUID}\n'
        "    >\n"
        "  >\n"
        "</TRACK>\n"
        "<TRACK\n"
        '  NAME "Track B"\n'
        "  <FXCHAIN\n"
        '    <VST "VST3: PluginB (Vendor)" PB.vst3 0 "" 222{GUID}\n'
        "    >\n"
        "  >\n"
        "</TRACK>\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.tracks) == 2
    assert len(result.plugins) == 2

    # First plugin should be on first track
    assert result.plugins[0].track_id == "t0"
    assert result.plugins[0].name == "PluginA"

    # Second plugin should be on second track
    assert result.plugins[1].track_id == "t1"
    assert result.plugins[1].name == "PluginB"


def test_media_item_in_track_relative_file(tmp_path: Path, reader: ReaperReader):
    """Test parsing media FILE inside ITEM in track with relative path."""
    audio_dir = tmp_path / "Audio"
    audio_dir.mkdir()
    audio_file = audio_dir / "kick.wav"
    audio_file.write_bytes(b"fake audio")

    rpp_file = tmp_path / "project.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        '  NAME "Track 1"\n'
        "  <ITEM\n"
        '    <SOURCE WAVE\n'
        '      FILE "Audio/kick.wav"\n'
        "    >\n"
        "  >\n"
        "</TRACK>\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.media) >= 1
    paths = [m.path for m in result.media]
    assert "Audio/kick.wav" in paths

    # Check metadata
    media = [m for m in result.media if m.path == "Audio/kick.wav"][0]
    assert media.exists is True
    assert media.inside_project_folder is True
    assert media.size_bytes == 10


def test_media_item_in_track_absolute_file(tmp_path: Path, reader: ReaperReader):
    """Test parsing media FILE inside ITEM with absolute path."""
    audio_dir = tmp_path / "Audio"
    audio_dir.mkdir()
    audio_file = audio_dir / "snare.wav"
    audio_file.write_bytes(b"fake audio data")

    rpp_file = tmp_path / "project.rpp"
    rpp_file.write_text(
        f'<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        '  NAME "Track 1"\n'
        "  <ITEM\n"
        '    <SOURCE WAVE\n'
        f'      FILE "{audio_file.as_posix()}"\n'
        "    >\n"
        "  >\n"
        "</TRACK>\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.media) >= 1
    media = result.media[0]
    assert media.exists is True
    assert media.size_bytes == 15


def test_media_section_nested_source(tmp_path: Path, reader: ReaperReader):
    """Test parsing media from SECTION-nested SOURCE."""
    audio_dir = tmp_path / "Audio"
    audio_dir.mkdir()
    audio_file = audio_dir / "loop.wav"
    audio_file.write_bytes(b"loop data")

    rpp_file = tmp_path / "project.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        '  NAME "Track 1"\n'
        "  <ITEM\n"
        '    <SOURCE SECTION\n'
        '      <SOURCE WAVE\n'
        '        FILE "Audio/loop.wav"\n'
        "      >\n"
        "    >\n"
        "  >\n"
        "</TRACK>\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.media) >= 1
    paths = [m.path for m in result.media]
    assert "Audio/loop.wav" in paths


def test_media_dedupe(tmp_path: Path, reader: ReaperReader):
    """Test that duplicate media paths are deduplicated."""
    audio_dir = tmp_path / "Audio"
    audio_dir.mkdir()
    audio_file = audio_dir / "sample.wav"
    audio_file.write_bytes(b"sample")

    rpp_file = tmp_path / "project.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        '  NAME "Track 1"\n'
        "  <ITEM\n"
        '    <SOURCE WAVE\n'
        '      FILE "Audio/sample.wav"\n'
        "    >\n"
        "  >\n"
        "  <ITEM\n"
        '    <SOURCE WAVE\n'
        '      FILE "Audio/sample.wav"\n'
        "    >\n"
        "  >\n"
        "</TRACK>\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    # Should only have one entry for the same file
    paths = [m.path for m in result.media]
    assert paths.count("Audio/sample.wav") == 1


def test_media_missing_file(tmp_path: Path, reader: ReaperReader):
    """Test parsing media FILE that doesn't exist."""
    rpp_file = tmp_path / "project.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        '  NAME "Track 1"\n'
        "  <ITEM\n"
        '    <SOURCE WAVE\n'
        '      FILE "Audio/missing.wav"\n'
        "    >\n"
        "  >\n"
        "</TRACK>\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.media) >= 1
    media = [m for m in result.media if m.path == "Audio/missing.wav"][0]
    assert media.exists is False
    assert media.inside_project_folder is True  # Still inside project folder
    assert media.size_bytes is None


def test_can_read_confidence(tmp_path: Path, reader: ReaperReader):
    """Test can_read method returns proper confidence."""
    rpp_file = tmp_path / "test.rpp"
    rpp_file.write_text('<REAPER_PROJECT 0.1 "7.22/win64"\n>\n')

    confidence = reader.can_read(rpp_file)
    assert confidence is not None


def test_latin1_fallback(tmp_path: Path, reader: ReaperReader):
    """Test reading files with latin-1 encoding."""
    rpp_file = tmp_path / "latin1.rpp"
    # Write some text with latin-1 encoding
    content = '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\nTEMPO 120 0 0\n>\n'
    rpp_file.write_bytes(content.encode("latin-1"))

    result = reader.read(rpp_file)
    assert result.project.tempo_bpm == 120.0


def test_multiple_tracks_with_devices(tmp_path: Path, reader: ReaperReader):
    """Test parsing multiple tracks with device IDs tracked."""
    rpp_file = tmp_path / "multi_tracks.rpp"
    rpp_file.write_text(
        '<REAPER_PROJECT 0.1 "7.22/win64" 1726000000\n'
        "<TRACK\n"
        '  NAME "Track 1"\n'
        "  <FXCHAIN\n"
        '    <VST "VST3: P1 (V)" P1.vst3 0 "" 111{GUID}\n'
        "    >\n"
        '    <VST "VST3: P2 (V)" P2.vst3 0 "" 222{GUID}\n'
        "    >\n"
        "  >\n"
        "</TRACK>\n"
        "<TRACK\n"
        '  NAME "Track 2"\n'
        "  <FXCHAIN\n"
        '    <VST "VST3: P3 (V)" P3.vst3 0 "" 333{GUID}\n'
        "    >\n"
        "  >\n"
        "</TRACK>\n"
        ">\n",
        encoding="utf-8",
    )

    result = reader.read(rpp_file)

    assert len(result.tracks) == 2
    assert len(result.plugins) == 3

    # Track 1 should have first 2 plugins
    assert len(result.tracks[0].devices) == 2
    assert result.tracks[0].devices == ["p0", "p1"]

    # Track 2 should have last plugin
    assert len(result.tracks[1].devices) == 1
    assert result.tracks[1].devices == ["p2"]
