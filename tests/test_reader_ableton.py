"""Tests for the Ableton Live .als reader (SPEC-02 section 4.2)."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from rackcheck_engine.detect import ProjectFormat
from rackcheck_engine.errors import CORRUPT_PROJECT, EngineError
from rackcheck_engine.model import Confidence, PluginFormat, PluginRole, TrackType
from rackcheck_engine.readers.ableton import AbletonReader


def write_ableton_xml(path: Path, xml: str) -> Path:
    """Write Ableton XML as a gzipped file."""
    xml_bytes = xml.encode("utf-8")
    path.write_bytes(gzip.compress(xml_bytes))
    return path


def _vst2_xml(plug_name: str = "Test VST2", vendor: str = "Vendor", unique_id: int = 12345) -> str:
    """Generate VST2 plugin XML."""
    return f"""
    <PluginDevice>
        <Name Value="Instance"/>
        <PluginDesc>
            <VstPluginInfo PlugName="{plug_name}" Manufacturer="{vendor}" UniqueId="{unique_id}"/>
        </PluginDesc>
        <On Value="true"/>
    </PluginDevice>
    """


def _vst3_xml(
    name: str = "Test VST3",
    h: int = 0x12345678,
    low: int = 0x9ABCDEF0,
    h2: int = 0x11223344,
    l2: int = 0x55667788,
) -> str:
    """Generate VST3 plugin XML with CID."""
    return f"""
    <PluginDevice>
        <Name Value="Instance"/>
        <PluginDesc>
            <Vst3PluginInfo Name="{name}" DeviceType="instrument">
                <Uid h="{h}" l="{low}" h2="{h2}" l2="{l2}"/>
            </Vst3PluginInfo>
        </PluginDesc>
        <On Value="true"/>
    </PluginDevice>
    """


def _au_xml(
    name: str = "TestAU", manufacturer: str = "Manu", comp_type: int = 1633907571
) -> str:
    """Generate AU plugin XML."""
    return f"""
    <PluginDevice>
        <Name Value="Instance"/>
        <PluginDesc>
            <AuPluginInfo Name="{name}" Manufacturer="{manufacturer}"
                         ComponentType="{comp_type}" ComponentSubType="0"
                         ComponentManufacturer="0"/>
        </PluginDesc>
        <On Value="true"/>
    </PluginDevice>
    """


def _stock_device_xml(tag: str = "Eq8", bypassed: bool = False) -> str:
    """Generate stock device XML."""
    on_value = "false" if bypassed else "true"
    return f"""
    <{tag}>
        <Name Value="Instance"/>
        <On Value="{on_value}"/>
    </{tag}>
    """


def _rack_with_device_xml() -> str:
    """Generate nested rack with a device inside."""
    return """
    <InstrumentGroupDevice>
        <Name Value="Rack"/>
        <On Value="true"/>
        <Branches>
            <Branch>
                <DeviceChain>
                    <Devices>
                        <Compressor2>
                            <Name Value="Comp"/>
                            <On Value="true"/>
                        </Compressor2>
                    </Devices>
                </DeviceChain>
            </Branch>
        </Branches>
    </InstrumentGroupDevice>
    """


def test_vst2_plugin(tmp_path: Path):
    """Test extraction of VST2 plugin."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <MidiTrack>
                <Name Value="Track 1"/>
                <DeviceChain>
                    <Devices>
                        {_vst2_xml('Serum', 'Xfer Records', 0x12345678)}
                    </Devices>
                </DeviceChain>
            </MidiTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "vst2.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert result.source.format == ProjectFormat.ABLETON_ALS
    assert result.source.daw_name == "Ableton Live"
    assert result.source.daw_version == "Ableton Live 12.0.0"
    assert len(result.plugins) == 1
    plugin = result.plugins[0]
    assert plugin.format == PluginFormat.VST2
    assert plugin.name == "Serum"
    assert plugin.vendor == "Xfer Records"
    assert plugin.identity.vst2_unique_id == 0x12345678
    assert plugin.confidence == Confidence.PROBABLE


def test_vst3_plugin_with_cid(tmp_path: Path):
    """Test extraction of VST3 plugin with CID."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <MidiTrack>
                <Name Value="Track 1"/>
                <DeviceChain>
                    <Devices>
                        {_vst3_xml('Surge XT', 0x11223344, 0x55667788, 0x99AABBCC, 0xDDEEFF00)}
                    </Devices>
                </DeviceChain>
            </MidiTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "vst3.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert len(result.plugins) == 1
    plugin = result.plugins[0]
    assert plugin.format == PluginFormat.VST3
    assert plugin.name == "Surge XT"
    # CID should be built from 4 int32 fields in uppercase hex
    assert plugin.identity.vst3_cid is not None
    assert len(plugin.identity.vst3_cid) == 32
    assert plugin.identity.vst3_cid.isupper()


def test_au_plugin(tmp_path: Path):
    """Test extraction of AU plugin."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <AudioTrack>
                <Name Value="Track 1"/>
                <DeviceChain>
                    <Devices>
                        {_au_xml('EQ', 'FabFilter', 1633907571)}
                    </Devices>
                </DeviceChain>
            </AudioTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "au.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert len(result.plugins) == 1
    plugin = result.plugins[0]
    assert plugin.format == PluginFormat.AU
    assert plugin.name == "EQ"
    assert plugin.vendor == "FabFilter"
    assert plugin.identity.au_type is not None


def test_stock_device(tmp_path: Path):
    """Test extraction of stock Ableton device."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <AudioTrack>
                <Name Value="Track 1"/>
                <DeviceChain>
                    <Devices>
                        {_stock_device_xml('Eq8', False)}
                    </Devices>
                </DeviceChain>
            </AudioTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "stock.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert len(result.plugins) == 1
    plugin = result.plugins[0]
    assert plugin.format == PluginFormat.STOCK
    assert plugin.name == "Eq8"
    assert plugin.vendor == "Ableton"
    assert plugin.bypassed is False


def test_bypass_state(tmp_path: Path):
    """Test extraction of bypass state."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <AudioTrack>
                <Name Value="Track 1"/>
                <DeviceChain>
                    <Devices>
                        {_stock_device_xml('Compressor2', True)}
                    </Devices>
                </DeviceChain>
            </AudioTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "bypassed.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert len(result.plugins) == 1
    plugin = result.plugins[0]
    assert plugin.bypassed is True


def test_nested_rack(tmp_path: Path):
    """Test extraction of devices nested inside a rack."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <MidiTrack>
                <Name Value="Track 1"/>
                <DeviceChain>
                    <Devices>
                        {_rack_with_device_xml()}
                    </Devices>
                </DeviceChain>
            </MidiTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "nested.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    # Should have 2 plugins: the rack and the device inside it
    assert len(result.plugins) == 2
    # First should be the rack
    rack = result.plugins[0]
    assert rack.format == PluginFormat.STOCK
    assert rack.name == "InstrumentGroupDevice"
    # Second should be the nested device
    nested = result.plugins[1]
    assert nested.format == PluginFormat.STOCK
    assert nested.name == "Compressor2"
    assert nested.nested_in == rack.id


def test_return_track(tmp_path: Path):
    """Test extraction of return track."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <ReturnTrack>
                <Name Value="Return 1"/>
                <DeviceChain>
                    <Devices>
                        {_stock_device_xml('Reverb', False)}
                    </Devices>
                </DeviceChain>
            </ReturnTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "return.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert len(result.tracks) == 1
    track = result.tracks[0]
    assert track.type == TrackType.RETURN
    assert track.name == "Return 1"


def test_master_track(tmp_path: Path):
    """Test extraction of master track with tempo."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <MasterTrack>
            <Name Value="Master"/>
            <Tempo>
                <Manual Value="120.0"/>
            </Tempo>
            <DeviceChain>
                <Devices/>
            </DeviceChain>
        </MasterTrack>
        <Tracks/>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "master.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert result.project.tempo_bpm == 120.0


def test_unicode_names(tmp_path: Path):
    """Test extraction of Unicode track and plugin names."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <AudioTrack>
                <Name Value="트랙 한글"/>
                <DeviceChain>
                    <Devices>
                        {_stock_device_xml('Eq8', False)}
                    </Devices>
                </DeviceChain>
            </AudioTrack>
            <MidiTrack>
                <Name Value="Piste 日本語"/>
                <DeviceChain>
                    <Devices>
                        {_vst2_xml('plugin мир', 'фирма', 99999)}
                    </Devices>
                </DeviceChain>
            </MidiTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "unicode.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert len(result.tracks) == 2
    assert result.tracks[0].name == "트랙 한글"
    assert result.tracks[1].name == "Piste 日本語"
    assert result.plugins[1].name == "plugin мир"
    assert result.plugins[1].vendor == "фирма"


def test_three_instances_same_plugin(tmp_path: Path):
    """Test extraction of 3 instances of the same plugin on different tracks."""
    plugin_xml = _vst2_xml("Serum", "Xfer Records", 0x12345678)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <MidiTrack>
                <Name Value="Track 1"/>
                <DeviceChain>
                    <Devices>
                        {plugin_xml}
                    </Devices>
                </DeviceChain>
            </MidiTrack>
            <MidiTrack>
                <Name Value="Track 2"/>
                <DeviceChain>
                    <Devices>
                        {plugin_xml}
                    </Devices>
                </DeviceChain>
            </MidiTrack>
            <MidiTrack>
                <Name Value="Track 3"/>
                <DeviceChain>
                    <Devices>
                        {plugin_xml}
                    </Devices>
                </DeviceChain>
            </MidiTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "multi.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert len(result.plugins) == 3
    for plugin in result.plugins:
        assert plugin.name == "Serum"
        assert plugin.vendor == "Xfer Records"


def test_xxe_rejection_with_doctype(tmp_path: Path):
    """Test that DOCTYPE declarations are rejected (XXE protection)."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE Ableton [
      <!ENTITY xxe SYSTEM "file:///etc/passwd">
    ]>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks/>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "xxe.als", xml)
    reader = AbletonReader()

    with pytest.raises(EngineError) as exc_info:
        reader.read(path)
    assert exc_info.value.code == CORRUPT_PROJECT


def test_xxe_rejection_with_entity(tmp_path: Path):
    """Test that ENTITY declarations are rejected (XXE protection)."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <!ENTITY test "malicious">
        <Tracks/>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "entity.als", xml)
    reader = AbletonReader()

    with pytest.raises(EngineError) as exc_info:
        reader.read(path)
    assert exc_info.value.code == CORRUPT_PROJECT


def test_corrupt_gzip(tmp_path: Path):
    """Test that corrupt gzip raises CORRUPT_PROJECT error."""
    path = tmp_path / "corrupt.als"
    path.write_bytes(b"\x1f\x8b\x08\x00" + b"\x00" * 100)  # Truncated gzip

    reader = AbletonReader()
    with pytest.raises(EngineError) as exc_info:
        reader.read(path)
    assert exc_info.value.code == CORRUPT_PROJECT


def test_time_signature_extraction(tmp_path: Path):
    """Test extraction of time signature from MasterTrack."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <MasterTrack>
            <Name Value="Master"/>
            <TimeSignature Numerator="3" Denominator="4"/>
            <DeviceChain>
                <Devices/>
            </DeviceChain>
        </MasterTrack>
        <Tracks/>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "timesig.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert result.project.time_signature == "3/4"


def test_track_devices_linked(tmp_path: Path):
    """Test that track.devices list references plugin IDs correctly."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <AudioTrack>
                <Name Value="Track 1"/>
                <DeviceChain>
                    <Devices>
                        {_stock_device_xml('Eq8', False)}
                        {_stock_device_xml('Compressor2', False)}
                    </Devices>
                </DeviceChain>
            </AudioTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "linked.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert len(result.tracks) == 1
    track = result.tracks[0]
    assert len(track.devices) == 2
    # Verify devices exist and are referenced
    device_ids = [p.id for p in result.plugins]
    assert all(did in device_ids for did in track.devices)


def test_main_track_live_12(tmp_path: Path):
    """Test extraction of MainTrack (Live 12 may call it MainTrack instead of MasterTrack)."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <MainTrack>
            <Name Value="Main"/>
            <Tempo>
                <Manual Value="100.0"/>
            </Tempo>
            <DeviceChain>
                <Devices/>
            </DeviceChain>
        </MainTrack>
        <Tracks/>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "main.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert result.project.tempo_bpm == 100.0


def test_group_track(tmp_path: Path):
    """Test extraction of group track."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <GroupTrack>
                <Name Value="Group 1"/>
                <DeviceChain>
                    <Devices>
                        {_stock_device_xml('Eq8', False)}
                    </Devices>
                </DeviceChain>
            </GroupTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "group.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert len(result.tracks) == 1
    assert result.tracks[0].type == TrackType.GROUP
    assert result.tracks[0].name == "Group 1"


def test_can_read_returns_probable(tmp_path: Path):
    """Test that can_read identifies gzip files as PROBABLE."""
    path = tmp_path / "test.als"
    path.write_bytes(b"\x1f\x8b" + b"\x00" * 100)  # Gzip header

    reader = AbletonReader()
    confidence = reader.can_read(path)
    assert confidence == Confidence.PROBABLE


def test_can_read_returns_none_for_non_files(tmp_path: Path):
    """Test that can_read returns None for non-files."""
    reader = AbletonReader()
    assert reader.can_read(tmp_path) is None
    assert reader.can_read(tmp_path / "nonexistent.als") is None


def test_effective_name_preferred_over_name(tmp_path: Path):
    """Test that EffectiveName is preferred over Name for tracks."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <AudioTrack>
                <Name Value="OldName"/>
                <EffectiveName Value="NewName"/>
                <DeviceChain>
                    <Devices>
                        {_stock_device_xml('Eq8', False)}
                    </Devices>
                </DeviceChain>
            </AudioTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "effective.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert result.tracks[0].name == "NewName"


def test_empty_device_chain(tmp_path: Path):
    """Test handling of tracks with empty device chains."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <AudioTrack>
                <Name Value="Empty"/>
                <DeviceChain>
                    <Devices/>
                </DeviceChain>
            </AudioTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "empty.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert len(result.tracks) == 1
    assert len(result.tracks[0].devices) == 0
    assert len(result.plugins) == 0


def test_reader_version_in_result(tmp_path: Path):
    """Test that reader version is included in results."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks/>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "version.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    assert result.source.reader_version == "0.1.0"


def test_first_midi_track_device_is_instrument(tmp_path: Path):
    """Test that stock effect devices are marked with EFFECT role."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <MidiTrack>
                <Name Value="Track 1"/>
                <DeviceChain>
                    <Devices>
                        {_stock_device_xml('Compressor2', False)}
                    </Devices>
                </DeviceChain>
            </MidiTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "instrument.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    # Stock device Compressor2 is an effect
    plugin = result.plugins[0]
    assert plugin.role == PluginRole.EFFECT


def test_audio_track_device_is_effect(tmp_path: Path):
    """Test that stock effect devices are marked with EFFECT role."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Ableton MajorVersion="5" Creator="Ableton Live 12.0.0">
        <Tracks>
            <AudioTrack>
                <Name Value="Track 1"/>
                <DeviceChain>
                    <Devices>
                        {_stock_device_xml('Eq8', False)}
                    </Devices>
                </DeviceChain>
            </AudioTrack>
        </Tracks>
    </Ableton>
    """
    path = write_ableton_xml(tmp_path / "audio.als", xml)
    reader = AbletonReader()
    result = reader.read(path)

    plugin = result.plugins[0]
    assert plugin.role == PluginRole.EFFECT  # Stock Eq8 is an effect
