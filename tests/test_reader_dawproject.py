"""Tests for the DAWproject (.dawproject) reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import write_zip
from rackcheck_engine.errors import EngineError
from rackcheck_engine.model import (
    Confidence,
    PluginFormat,
    PluginRole,
    TrackType,
)
from rackcheck_engine.readers.dawproject import DawprojectReader


def make_dawproject(
    tmp_path: Path,
    name: str = "test.dawproject",
    project_xml: bytes | None = None,
    metadata_xml: bytes | None = None,
) -> Path:
    """Create a synthetic DAWproject zip."""
    if project_xml is None:
        project_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project/>"""
    if metadata_xml is None:
        metadata_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<MetaData/>"""
    return write_zip(tmp_path / name, {"project.xml": project_xml, "metadata.xml": metadata_xml})


def test_reader_has_protocol(tmp_path: Path):
    """Reader implements the Reader protocol."""
    reader = DawprojectReader()
    assert reader.formats == ("dawproject",)
    assert reader.version == "0.1.0"
    assert hasattr(reader, "can_read")
    assert hasattr(reader, "read")


def test_can_read_dawproject(tmp_path: Path):
    """can_read returns CONFIRMED for valid dawproject."""
    path = make_dawproject(tmp_path)
    reader = DawprojectReader()
    result = reader.can_read(path)
    assert result == Confidence.CONFIRMED


def test_can_read_not_a_zip(tmp_path: Path):
    """can_read returns None for non-zip files."""
    p = tmp_path / "notzip.txt"
    p.write_text("hello")
    reader = DawprojectReader()
    assert reader.can_read(p) is None


def test_can_read_zip_without_required_files(tmp_path: Path):
    """can_read returns None for zip missing project.xml or metadata.xml."""
    p = write_zip(tmp_path / "bad.dawproject", {"readme.txt": b"hi"})
    reader = DawprojectReader()
    assert reader.can_read(p) is None


def test_read_minimal_project(tmp_path: Path):
    """read() parses minimal valid project."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Application name="Bitwig Studio" version="5.1.0"/>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert result.source.format == "dawproject"
    assert result.source.daw_name == "Bitwig Studio"
    assert result.source.daw_version == "5.1.0"
    assert result.source.reader_version == "0.1.0"


def test_read_tempo_and_time_signature(tmp_path: Path):
    """read() extracts tempo and time signature."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Application name="Bitwig Studio" version="5.1.0"/>
  <Transport>
    <Tempo value="120.5"/>
    <TimeSignature numerator="3" denominator="4"/>
  </Transport>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert result.project.tempo_bpm == 120.5
    assert result.project.time_signature == "3/4"


def test_read_master_track(tmp_path: Path):
    """read() extracts master track."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Master" contentType="master">
      <Channel role="masterTrack"/>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.tracks) == 1
    assert result.tracks[0].name == "Master"
    assert result.tracks[0].type == TrackType.MASTER


def test_read_multiple_track_types(tmp_path: Path):
    """read() extracts different track types."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Drums" contentType="audio">
      <Channel/>
    </Track>
    <Track name="Keys" contentType="midi">
      <Channel/>
    </Track>
    <Track name="Reverb Return" contentType="return">
      <Channel role="return"/>
    </Track>
    <Track name="Master" contentType="master">
      <Channel role="masterTrack"/>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.tracks) == 4
    assert result.tracks[0].type == TrackType.AUDIO
    assert result.tracks[1].type == TrackType.MIDI
    assert result.tracks[2].type == TrackType.RETURN
    assert result.tracks[3].type == TrackType.MASTER


def test_read_nested_tracks(tmp_path: Path):
    """read() handles nested tracks (folders/groups)."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Folder" contentType="group">
      <Channel/>
      <Track name="Nested Track 1" contentType="audio">
        <Channel/>
      </Track>
      <Track name="Nested Track 2" contentType="audio">
        <Channel/>
      </Track>
    </Track>
    <Track name="Other" contentType="audio">
      <Channel/>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    # Should have: Folder (t1), Nested Track 1 (t2), Nested Track 2 (t3), Other (t4)
    assert len(result.tracks) >= 2
    assert result.tracks[0].name == "Folder"
    assert result.tracks[0].type == TrackType.FOLDER


def test_read_vst3_plugin(tmp_path: Path):
    """read() extracts VST3 plugins with CLAP ID."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Track 1" contentType="audio">
      <Channel>
        <Devices>
          <Vst3Plugin deviceID="AABBCCDD11223344556677889900AABB"
                      deviceName="Serum"
                      deviceVendor="Xfer Records"
                      pluginVersion="1.368"
                      deviceRole="effect">
            <Enabled value="true"/>
          </Vst3Plugin>
        </Devices>
      </Channel>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.plugins) == 1
    plugin = result.plugins[0]
    assert plugin.format == PluginFormat.VST3
    assert plugin.name == "Serum"
    assert plugin.vendor == "Xfer Records"
    assert plugin.role == PluginRole.EFFECT
    assert plugin.version_in_project == "1.368"
    assert plugin.confidence == Confidence.CONFIRMED
    assert plugin.identity.vst3_cid == "AABBCCDD11223344556677889900AABB"
    assert plugin.bypassed is False


def test_read_vst2_plugin(tmp_path: Path):
    """read() extracts VST2 plugins."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Track 1" contentType="audio">
      <Channel>
        <Devices>
          <Vst2Plugin deviceID="12345"
                      deviceName="Vintage Synth"
                      deviceVendor="Spectrasonics"
                      deviceRole="instrument">
            <Enabled value="false"/>
          </Vst2Plugin>
        </Devices>
      </Channel>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.plugins) == 1
    plugin = result.plugins[0]
    assert plugin.format == PluginFormat.VST2
    assert plugin.name == "Vintage Synth"
    assert plugin.role == PluginRole.INSTRUMENT
    assert plugin.bypassed is True


def test_read_clap_plugin(tmp_path: Path):
    """read() extracts CLAP plugins."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Track 1" contentType="audio">
      <Channel>
        <Devices>
          <ClapPlugin deviceID="org.surge-synth-team.surge-xt"
                      deviceName="Surge XT"
                      deviceVendor="Surge Synth Team"
                      deviceRole="instrument">
            <Enabled value="true"/>
          </ClapPlugin>
        </Devices>
      </Channel>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.plugins) == 1
    plugin = result.plugins[0]
    assert plugin.format == PluginFormat.CLAP
    assert plugin.identity.clap_id == "org.surge-synth-team.surge-xt"
    assert plugin.name == "Surge XT"


def test_read_au_plugin(tmp_path: Path):
    """read() extracts AU plugins."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Track 1" contentType="audio">
      <Channel>
        <Devices>
          <AuPlugin deviceID="aufx:pmeq:appl"
                    deviceName="Parametric EQ"
                    deviceVendor="Apple"
                    deviceRole="effect">
            <Enabled value="true"/>
          </AuPlugin>
        </Devices>
      </Channel>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.plugins) == 1
    plugin = result.plugins[0]
    assert plugin.format == PluginFormat.AU


def test_read_builtin_devices(tmp_path: Path):
    """read() extracts built-in devices as STOCK."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Track 1" contentType="audio">
      <Channel>
        <Devices>
          <Equalizer deviceName="Equalizer" deviceRole="effect">
            <Enabled value="true"/>
          </Equalizer>
          <Compressor deviceName="Compressor" deviceRole="effect">
            <Enabled value="true"/>
          </Compressor>
          <NoiseGate deviceName="Noise Gate" deviceRole="effect">
            <Enabled value="true"/>
          </NoiseGate>
          <Limiter deviceName="Limiter" deviceRole="effect">
            <Enabled value="true"/>
          </Limiter>
        </Devices>
      </Channel>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.plugins) == 4
    for plugin in result.plugins:
        assert plugin.format == PluginFormat.STOCK
        assert plugin.role == PluginRole.EFFECT
        assert plugin.confidence == Confidence.CONFIRMED


def test_read_multiple_instances_same_plugin(tmp_path: Path):
    """read() counts multiple instances correctly."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Track 1" contentType="audio">
      <Channel>
        <Devices>
          <Vst3Plugin deviceID="AABBCCDD11223344556677889900AABB"
                      deviceName="Serum"
                      deviceVendor="Xfer Records"
                      deviceRole="instrument">
            <Enabled value="true"/>
          </Vst3Plugin>
          <Vst3Plugin deviceID="AABBCCDD11223344556677889900AABB"
                      deviceName="Serum"
                      deviceVendor="Xfer Records"
                      deviceRole="effect">
            <Enabled value="true"/>
          </Vst3Plugin>
          <Vst3Plugin deviceID="AABBCCDD11223344556677889900AABB"
                      deviceName="Serum"
                      deviceVendor="Xfer Records"
                      deviceRole="effect">
            <Enabled value="false"/>
          </Vst3Plugin>
        </Devices>
      </Channel>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.plugins) == 3
    assert result.plugins[0].role == PluginRole.INSTRUMENT
    assert result.plugins[1].role == PluginRole.EFFECT
    assert result.plugins[2].role == PluginRole.EFFECT
    assert result.plugins[0].bypassed is False
    assert result.plugins[1].bypassed is False
    assert result.plugins[2].bypassed is True


def test_read_unicode_names(tmp_path: Path):
    """read() handles unicode track and plugin names."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Application name="Bitwig Studio" version="5.1.0"/>
  <Structure>
    <Track name="🎹 Synth ñ Café" contentType="audio">
      <Channel>
        <Devices>
          <Vst3Plugin deviceID="AABBCCDD11223344556677889900AABB"
                      deviceName="Serum 日本語"
                      deviceVendor="Xfer Records"
                      deviceRole="effect">
            <Enabled value="true"/>
          </Vst3Plugin>
        </Devices>
      </Channel>
    </Track>
  </Structure>
</Project>""".encode()
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert result.tracks[0].name == "🎹 Synth ñ Café"
    assert result.plugins[0].name == "Serum 日本語"


def test_read_media_references(tmp_path: Path):
    """read() extracts media file references."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Media>
    <Audio>
      <File path="audio/drum_loop.wav"/>
    </Audio>
    <Audio>
      <File path="../samples/synth.wav"/>
    </Audio>
  </Media>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.media) == 2
    assert result.media[0].path == "audio/drum_loop.wav"
    assert result.media[1].path == "../samples/synth.wav"


def test_read_xxe_attack_rejected(tmp_path: Path):
    """read() rejects XML with DOCTYPE declarations (XXE protection)."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Project [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<Project>
  <Data>&xxe;</Data>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()

    with pytest.raises(EngineError) as exc_info:
        reader.read(path)
    assert exc_info.value.code == "CORRUPT_PROJECT"


def test_read_entity_attack_rejected(tmp_path: Path):
    """read() rejects XML with ENTITY declarations."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Project [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">
]>
<Project>
  <Data>&lol2;</Data>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()

    with pytest.raises(EngineError) as exc_info:
        reader.read(path)
    assert exc_info.value.code == "CORRUPT_PROJECT"


def test_read_missing_project_xml(tmp_path: Path):
    """read() raises CORRUPT_PROJECT if project.xml is missing."""
    p = write_zip(tmp_path / "bad.dawproject", {"metadata.xml": b"<MetaData/>"})
    reader = DawprojectReader()

    with pytest.raises(EngineError) as exc_info:
        reader.read(p)
    assert exc_info.value.code == "CORRUPT_PROJECT"
    assert "project.xml" in exc_info.value.message.lower()


def test_read_corrupted_xml_syntax(tmp_path: Path):
    """read() raises CORRUPT_PROJECT for malformed XML."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Unclosed>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()

    with pytest.raises(EngineError) as exc_info:
        reader.read(path)
    assert exc_info.value.code == "CORRUPT_PROJECT"


def test_read_corrupted_zip(tmp_path: Path):
    """read() raises CORRUPT_PROJECT for invalid zip."""
    p = tmp_path / "bad.dawproject"
    p.write_bytes(b"PK\x03\x04" + b"corrupted data")
    reader = DawprojectReader()

    with pytest.raises(EngineError) as exc_info:
        reader.read(p)
    assert exc_info.value.code == "CORRUPT_PROJECT"


def test_read_file_not_found(tmp_path: Path):
    """read() raises appropriate error for missing file."""
    path = tmp_path / "nonexistent.dawproject"
    reader = DawprojectReader()

    with pytest.raises(EngineError) as exc_info:
        reader.read(path)
    assert exc_info.value.code == "CORRUPT_PROJECT"


def test_read_plugins_assigned_to_tracks(tmp_path: Path):
    """read() assigns plugins to correct tracks."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Track 1" contentType="audio">
      <Channel>
        <Devices>
          <Vst3Plugin deviceID="AABBCCDD11223344556677889900AABB"
                      deviceName="Serum"
                      deviceVendor="Xfer Records"
                      deviceRole="instrument">
            <Enabled value="true"/>
          </Vst3Plugin>
        </Devices>
      </Channel>
    </Track>
    <Track name="Track 2" contentType="audio">
      <Channel>
        <Devices>
          <Vst3Plugin deviceID="11223344556677889900AABBCCDDAABB"
                      deviceName="Pro-Q"
                      deviceVendor="FabFilter"
                      deviceRole="effect">
            <Enabled value="true"/>
          </Vst3Plugin>
        </Devices>
      </Channel>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.plugins) == 2
    assert result.plugins[0].track_id == "t1"
    assert result.plugins[1].track_id == "t2"


def test_read_bypass_status(tmp_path: Path):
    """read() correctly extracts bypass status from Enabled element."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Track 1" contentType="audio">
      <Channel>
        <Devices>
          <Vst3Plugin deviceID="AABBCCDD11223344556677889900AABB"
                      deviceName="Plugin A"
                      deviceVendor="Vendor"
                      deviceRole="effect">
            <Enabled value="true"/>
          </Vst3Plugin>
          <Vst3Plugin deviceID="11223344556677889900AABBCCDDAABB"
                      deviceName="Plugin B"
                      deviceVendor="Vendor"
                      deviceRole="effect">
            <Enabled value="false"/>
          </Vst3Plugin>
          <Vst3Plugin deviceID="CC11223344556677889900AABBCCDDAA"
                      deviceName="Plugin C"
                      deviceVendor="Vendor"
                      deviceRole="effect">
          </Vst3Plugin>
        </Devices>
      </Channel>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert result.plugins[0].bypassed is False
    assert result.plugins[1].bypassed is True
    assert result.plugins[2].bypassed is None


def test_read_complex_nested_project(tmp_path: Path):
    """read() handles complex project with nested tracks, multiple plugins, and media."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Application name="Bitwig Studio" version="5.1.0"/>
  <Transport>
    <Tempo value="128"/>
    <TimeSignature numerator="4" denominator="4"/>
  </Transport>
  <Structure>
    <Track name="Drums Folder" contentType="group">
      <Channel/>
      <Track name="Kick" contentType="audio">
        <Channel>
          <Devices>
            <Vst3Plugin deviceID="AABBCCDD11223344556677889900AABB"
                        deviceName="Kick Synth"
                        deviceVendor="Vendor1"
                        deviceRole="instrument">
              <Enabled value="true"/>
            </Vst3Plugin>
          </Devices>
        </Channel>
      </Track>
      <Track name="Snare" contentType="audio">
        <Channel>
          <Devices>
            <Equalizer deviceName="Equalizer" deviceRole="effect">
              <Enabled value="false"/>
            </Equalizer>
          </Devices>
        </Channel>
      </Track>
    </Track>
    <Track name="Bass" contentType="audio">
      <Channel>
        <Devices>
          <ClapPlugin deviceID="org.vendor.bass-synth"
                      deviceName="Bass Synth"
                      deviceVendor="Vendor2"
                      deviceRole="instrument">
            <Enabled value="true"/>
          </ClapPlugin>
          <Compressor deviceName="Compressor" deviceRole="effect">
            <Enabled value="true"/>
          </Compressor>
        </Devices>
      </Channel>
    </Track>
    <Track name="Reverb Return" contentType="return">
      <Channel role="return">
        <Devices>
          <BuiltinDevice deviceName="Reverb" deviceRole="effect">
            <Enabled value="true"/>
          </BuiltinDevice>
        </Devices>
      </Channel>
    </Track>
    <Track name="Master" contentType="master">
      <Channel role="masterTrack">
        <Devices>
          <Limiter deviceName="Limiter" deviceRole="effect">
            <Enabled value="true"/>
          </Limiter>
        </Devices>
      </Channel>
    </Track>
  </Structure>
  <Media>
    <Audio>
      <File path="audio/drum_loop.wav"/>
    </Audio>
    <Audio>
      <File path="samples/bass.wav"/>
    </Audio>
  </Media>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    # Verify source
    assert result.source.daw_name == "Bitwig Studio"
    assert result.source.daw_version == "5.1.0"

    # Verify project info
    assert result.project.tempo_bpm == 128
    assert result.project.time_signature == "4/4"

    # Verify tracks
    assert len(result.tracks) >= 4
    assert result.tracks[-1].type == TrackType.MASTER

    # Verify plugins
    # Total: Kick Synth (VST3) + Equalizer (stock) + Bass Synth (CLAP) +
    # Compressor (stock) + Reverb (builtin) + Limiter (stock) = 6
    assert len(result.plugins) == 6

    # Count instrument vs effect plugins
    instrument_plugins = [p for p in result.plugins if p.role == PluginRole.INSTRUMENT]
    effect_plugins = [p for p in result.plugins if p.role == PluginRole.EFFECT]
    assert len(instrument_plugins) == 2
    assert len(effect_plugins) == 4

    # Verify media
    assert len(result.media) == 2
    assert result.media[0].path == "audio/drum_loop.wav"
    assert result.media[1].path == "samples/bass.wav"


def test_read_empty_devices_element(tmp_path: Path):
    """read() handles tracks with empty Devices element."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Empty Track" contentType="audio">
      <Channel>
        <Devices>
        </Devices>
      </Channel>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.tracks) == 1
    assert result.tracks[0].name == "Empty Track"
    assert len(result.plugins) == 0


def test_read_no_channel_element(tmp_path: Path):
    """read() handles tracks without Channel element."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Track No Channel" contentType="audio">
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.tracks) == 1
    assert result.tracks[0].name == "Track No Channel"
    assert len(result.plugins) == 0


def test_read_device_without_attributes(tmp_path: Path):
    """read() handles devices with missing attributes gracefully."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Track 1" contentType="audio">
      <Channel>
        <Devices>
          <Vst3Plugin>
            <Enabled value="true"/>
          </Vst3Plugin>
        </Devices>
      </Channel>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    # Should still read but with None values
    assert len(result.plugins) == 1
    assert result.plugins[0].name is None
    assert result.plugins[0].vendor is None


def test_read_mixed_plugin_formats_on_track(tmp_path: Path):
    """read() correctly handles tracks with mixed VST/CLAP/AU/builtin plugins."""
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Structure>
    <Track name="Full Stack" contentType="audio">
      <Channel>
        <Devices>
          <Vst3Plugin deviceID="AABBCCDD11223344556677889900AABB"
                      deviceName="VST3 Plugin"
                      deviceVendor="Vendor1"
                      deviceRole="effect">
            <Enabled value="true"/>
          </Vst3Plugin>
          <Vst2Plugin deviceID="VST2"
                      deviceName="VST2 Plugin"
                      deviceVendor="Vendor2"
                      deviceRole="effect">
            <Enabled value="false"/>
          </Vst2Plugin>
          <ClapPlugin deviceID="org.vendor.clap"
                      deviceName="CLAP Plugin"
                      deviceVendor="Vendor3"
                      deviceRole="effect">
            <Enabled value="true"/>
          </ClapPlugin>
          <AuPlugin deviceID="aufx:code:appl"
                    deviceName="AU Plugin"
                    deviceVendor="Vendor4"
                    deviceRole="effect">
            <Enabled value="true"/>
          </AuPlugin>
          <Equalizer deviceName="Equalizer" deviceRole="effect">
            <Enabled value="true"/>
          </Equalizer>
        </Devices>
      </Channel>
    </Track>
  </Structure>
</Project>"""
    path = make_dawproject(tmp_path, project_xml=xml)
    reader = DawprojectReader()
    result = reader.read(path)

    assert len(result.plugins) == 5
    formats = [p.format for p in result.plugins]
    assert PluginFormat.VST3 in formats
    assert PluginFormat.VST2 in formats
    assert PluginFormat.CLAP in formats
    assert PluginFormat.AU in formats
    assert PluginFormat.STOCK in formats
