# SPEC-02: File Format Readers

**Project:** Plugin Dependency Scanner (working name: "Rackcheck")
**Companion specs:** SPEC-01-build-order.md, SPEC-03-gui-and-engine-integration.md
**Status:** Draft v1, September 2026

This spec defines how each project file type is detected and read, where plugin data lives inside it, and which existing projects to study or use. License classes (A/B/C) are defined in SPEC-01 section 4.

**Important:** internal element names, offsets and field names below come from public reverse-engineering work and documentation. Treat every structural detail as "verify against fixtures" until a crafted fixture confirms it. Where something is unconfirmed, it says so.

---

## 1. Supported inputs

| DAW | Extensions | Container | Phase |
|---|---|---|---|
| REAPER | .rpp, .rpp-bak, .RTrackTemplate, .RfxChain | Plain text | 1 |
| Ableton Live | .als (also Backup/*.als) | Gzip + XML | 1 |
| DAWproject (Bitwig, Cubase 14+, Studio One, others) | .dawproject | Zip + XML | 1 |
| Studio One / Fender Studio Pro | .song | Zip + XML | 3 |
| FL Studio | .flp | Binary event stream | 3 |
| Cubase / Nuendo | .cpr, .npr | Binary, RIFF-like | 3 |
| Logic Pro / GarageBand | .logicx, .band (folder bundles) | Bundle + binary ProjectData | 4 |
| Pro Tools | .ptx (.ptf, .pts older) | XOR-obfuscated binary | 5 |
| Pro Tools text export | .txt | Plain text | 5 |
| Bitwig native | .bwproject | Proprietary binary | 7 (heuristic only) |

Wrappers the app must also accept: a folder (search it for project files), a .zip (extract to temp), a zipped .logicx bundle.

---

## 2. Format detection

Detect by content first, extension second. Run checks in this order; first confident match wins.

| Check | Result |
|---|---|
| Path is a directory containing `Alternatives/` and `Resources/ProjectInformation.plist` | Logic / GarageBand bundle |
| First 2 bytes `1F 8B` (gzip), decompressed content starts with `<?xml` and contains `<Ableton` | Ableton .als |
| First 4 bytes `50 4B 03 04` (zip) and contains `project.xml` + `metadata.xml` at root | DAWproject |
| Zip containing `Song/song.xml` or `Song/mediapool.xml` | Studio One .song (verify entry names with fixtures) |
| Zip, none of the above | Generic zip: extract and re-run detection on contents |
| Text starting with `<REAPER_PROJECT` | REAPER |
| First 4 bytes `FLhd` | FL Studio .flp |
| First 4 bytes `RIFF` and contains `NUND` marker near start | Cubase / Nuendo (verify marker with fixtures) |
| Text containing Pro Tools session info header lines (`SESSION NAME:`, `SAMPLE RATE:`, plugin list section) | Pro Tools text export |
| Extension .ptx/.ptf/.pts and ptformat header check passes | Pro Tools binary |
| Extension .bwproject | Bitwig native (heuristic reader) |
| Otherwise | Unsupported: tell the user which formats are supported and, if it looks like a project from a known DAW, suggest the export path (e.g. "Export as DAWproject") |

Every detection returns `{format, confidence, reason}` so failures are explainable.

---

## 3. Common data model

This is the minimum internal structure every reader outputs. The full user-facing report (reader output plus enrichment, summary and warnings) is the superset defined in section 10, and readers should fill any section 9 fields they can using the section 10 field names. JSON shape:

```json
{
  "source": {
    "path": "string",
    "format": "ableton_als",
    "daw_name": "Ableton Live",
    "daw_version": "12.1.5",
    "reader_version": "1.0.0"
  },
  "project": {
    "tempo_bpm": 128.0,
    "time_signature": "4/4",
    "key": null,
    "sample_rate": 48000,
    "length_seconds": null
  },
  "tracks": [
    {
      "id": "t1",
      "name": "Bass",
      "type": "instrument | audio | midi | return | group | master | folder | other",
      "devices": ["p1", "p2"]
    }
  ],
  "plugins": [
    {
      "id": "p1",
      "track_id": "t1",
      "slot_index": 0,
      "role": "instrument | effect | unknown",
      "format": "vst2 | vst3 | au | aax | clap | stock | js | lv2 | unknown",
      "name": "Serum",
      "vendor": "Xfer Records",
      "version_in_project": null,
      "identity": {
        "vst2_unique_id": null,
        "vst3_cid": null,
        "au_type": null, "au_subtype": null, "au_manufacturer": null,
        "clap_id": null,
        "aax_ids": null,
        "file_hint": "Serum_x64.dll"
      },
      "bypassed": false,
      "nested_in": null,
      "confidence": "confirmed | probable | heuristic"
    }
  ],
  "media": [
    { "path": "string", "exists": true, "inside_project_folder": true, "size_bytes": 0 }
  ],
  "warnings": ["string"]
}
```

Rules:
- `nested_in` links a plugin inside a rack/container/chain to its parent device.
- Stock (built-in) devices are recorded with `format: "stock"` and `vendor` set to the DAW maker, so the report can say "needs Ableton" rather than "missing".
- Unknown fields are `null`, never guessed (SPEC-01 P4).

---

## 4. Reader specs

Each section: what the file is, how to open it, where plugins live, what to extract, pitfalls, and prior work.

### 4.1 REAPER (.rpp) - Phase 1

**Container:** plain text, nested chunks in angle brackets. Readable by eye.

**Open:** read as text (UTF-8, fall back to latin-1). Parse chunk tree.

**Where plugins live:** each `<TRACK` chunk contains an `<FXCHAIN` chunk. Plugin entries inside it start with a format tag. Typical forms (verify with fixtures):
- `<VST "VST3: Name (Vendor)" filename.vst3 0 "" <numeric id>{<32-hex GUID>} ...`
- `<VST "VST: Name (Vendor)" filename.dll 0 "" <numeric unique id><...> ...`
- `<AU "AU: Name (Vendor)" "Vendor: Name" "" ...`
- `<CLAP "CLAP: Name (Vendor)" com.vendor.pluginid ...`
- `<JS path/to/effect ""` (REAPER JSFX, treat as stock)
- `<LV2 ...>`, `<DX ...>` (rare)
- `BYPASS a b c` line before each plugin: first value is bypass state
- Master track FX: `<MASTERFXLIST` chunk. Input FX / monitoring FX: `<FXCHAIN_REC`
- Base64 lines inside each plugin chunk are plugin state: skip

**Extract:** the display string gives both name and vendor in "Name (Vendor)" form; split on the last parenthesis. VST3 GUID gives exact identity.

**Pitfalls:** users can rename FX instances (the display string may be custom; check REAPER's rename field if present and prefer the original name); very large files with big state blobs (stream the parse); .rpp-bak is identical format.

**Prior work:**
| Project | Language | License | Class | Notes |
|---|---|---|---|---|
| Perlence/rpp | Python | BSD-3-Clause | A | Parser/emitter, ElementTree-like API |
| IcEarthlight/rppxml | Python + C++ (WDL) | Check repo | Verify | About 13x faster than rpp on large files, reads .RfxChain |
| reaproj (PyPI) | Python | Check PyPI | Verify | Object model on top of rpp |
| GriffinSauce/reaper-project-parser | TypeScript | Check repo | Verify | Pre-1.0 |

**Recommendation:** writing our own chunk parser is simple (it's a line-based format) and avoids a dependency. Use Perlence/rpp tests as a reference for edge cases.

### 4.2 Ableton Live (.als) - Phase 1

**Container:** gzip-compressed XML.

**Open:** gunzip, parse XML (use a streaming parser for large sets). The root `<Ableton>` element carries `Creator` (Live version) and schema attributes.

**Where plugins live** (verify all names with fixtures):
- Third-party plugins appear as `PluginDevice` elements (instruments and effects) inside each track's device chain.
- Inside `PluginDevice` is `PluginDesc`, which contains one of:
  - `VstPluginInfo`: VST2. Fields include plugin name, file name/path, and the 4-char unique ID as an integer
  - `Vst3PluginInfo`: VST3. Fields include name and the class ID stored as integer fields that combine into the 128-bit CID
  - `AuPluginInfo`: AU. Fields include name, manufacturer name, and component type / subtype / manufacturer codes
- Racks (`InstrumentGroupDevice`, `AudioEffectGroupDevice`, `MidiEffectGroupDevice`, `DrumGroupDevice`) contain `Branches` with their own device chains; recurse and set `nested_in`.
- Stock devices are their own element names (e.g. `Eq8`, `Compressor2`, `Reverb`, `OriginalSimpler`, `MultiSampler`). Record as `stock`.
- Max for Live devices (`MxDeviceAudioEffect`, `MxDeviceInstrument`, `MxDeviceMidiEffect`) reference .amxd files: record as stock-ish with the .amxd name, since the collaborator needs the same M4L device file.
- Device on/off state is a parameter on each device (for bypass).
- Track types: `AudioTrack`, `MidiTrack`, `ReturnTrack`, `GroupTrack`, `MasterTrack` (and `PreHearTrack`, ignore).
- Sample references: `SampleRef > FileRef` with relative and absolute path info.

**Pitfalls:** schema changes between Live 9, 10, 11 and 12 (test each); VST3 CID assembly from integer fields must match the byte order used by the plugin's moduleinfo CID (confirm with a fixture that has a known CID); `Backup/` folder contains timestamped copies with the same format.

**Prior work:**
| Project | Language | License | Class | Notes |
|---|---|---|---|---|
| bounceconnection/pluginventory | Swift | MIT | A | macOS app: scans .als for AU/VST3/VST2 plugins, flags missing ones. Closest existing product; study its matching logic |
| bravoh-daw (docs.rs) | Rust | MIT | A | Unified parser including Ableton plugins |
| luizen/als-tools | C# | Check repo | Verify | Search/list/count across .als files |
| my5t3ry/als-parser | Java | Check repo | Verify | Live 8+ |
| offlinemark/dawtool (and forks) | Python | Check repo | Verify | ADC 2020 talk; focused on markers/tempo |
| madisonrickert/ableton-tools | Python | Check repo | Verify | Safe .als editing, sample reference handling |

### 4.3 DAWproject (.dawproject) - Phase 1

**Container:** zip. Root contains `project.xml` (content), `metadata.xml` (title, artist, etc.), plus audio and a `plugins/` folder of state files.

**Open:** unzip in memory, parse `project.xml`.

**Where plugins live:** each `Track > Channel > Devices` element contains device elements:
- `Vst2Plugin`, `Vst3Plugin`, `ClapPlugin`, `AuPlugin`: third-party plugins
- Built-in device profiles (generic EQ, Compressor, NoiseGate, Limiter) and generic `Device` elements for DAW-internal devices
- Attributes include `deviceID`, `deviceName`, `deviceRole` (instrument / audioFX / noteFX / analyzer), `loaded`, plus `deviceVendor` and `pluginVersion` where the exporter provides them (confirm in the XSD)
- `Enabled` child element holds on/off (bypass)
- `State path="plugins/<uuid>.<ext>"` points to the state file. We don't need to read it.

Example from the official repo README: a `ClapPlugin` element with `deviceID="org.surge-synth-team.surge-xt"` and `deviceName="Surge XT"`.

**Identity mapping:** `deviceID` holds the format-native ID: CLAP reverse-DNS id, VST3 CID, VST2 unique ID, AU codes (confirm the exact string format for VST2 and AU from fixtures exported by Bitwig, Cubase and Studio One, as each exporter may differ).

**Pitfalls:** exporters vary in completeness (early implementations were buggy); the user has to export manually; plugin state formats are undocumented (irrelevant for us).

**Prior work:**
| Project | Language | License | Class | Notes |
|---|---|---|---|---|
| bitwig/dawproject | Java + XSD + docs | MIT | A | Official spec, XML schema, reference DOM |
| roex-audio/dawproject-py | Python | MIT | A | Load/inspect/save .dawproject |
| dawproject-rs | Rust | "MIT NO-AI" | C | Nonstandard license; do not use |
| audiohacking/daw2logic | Python | Check repo | Verify | DAWproject to Logic converter; good test-file source |

**Recommendation:** validate against the official XSD, parse with our own code or dawproject-py.

### 4.4 Studio One / Fender Studio Pro (.song) - Phase 3

**Container:** zip archive of XML files.

**Open:** unzip in memory. Known entry: `Song/mediapool.xml` (media references with stored paths). Device/plugin data lives in other XML entries in the archive (likely under a `Devices/` folder, e.g. mixer and synth-folder XML). Map the entries with crafted fixtures before writing the reader.

**Where plugins live (to confirm):** plugin elements carrying a class ID attribute and a name. Studio One's plugin identity is likely the format-native ID (VST3 CID, etc.).

**Pitfalls:** SongLens release notes mention Studio One / Fender Studio Pro XML containing element names with invalid C++-style `::` double colons. Use a tolerant XML parser or pre-sanitize before parsing. Songs also keep a `History/` folder of older versions.

**Prior work:**
| Project | Language | License | Class | Notes |
|---|---|---|---|---|
| Myvryn/StudioOneTools ("Six Walls") | C# | Check repo | Verify | Reads mediapool.xml, archives songs |
| askinner432/SongLens | Unknown | Check repo | Verify | Reads song metadata; handles malformed XML |
| DAWproject export | - | - | - | Fallback: Studio One 6.5+ exports DAWproject |

### 4.5 FL Studio (.flp) - Phase 3

**Container:** binary. Header chunk `FLhd`, then data chunk `FLdt` containing a flat stream of events. Each event is an ID byte plus a value whose size depends on the ID range (byte, word, dword, or variable-length text/data with a varint length).

**Where plugins live:** channel (generator) events and mixer insert slot events. Native FL plugins are identified by an internal name (e.g. "Fruity Parametric EQ 2", "Sytrus"). Third-party plugins load through FL's VST wrapper; the wrapper's data event contains the actual plugin name, vendor, file path, and identity (VST2 unique ID, or VST3/CLAP IDs in newer versions).

**Pitfalls:** event IDs change across FL versions; PyFLP's author notes older projects (pre-FL 20) may not parse; the channel display name may differ from the true plugin name (PyFLP discussion #172 explains that FL assigns a default channel name that isn't reliable, and the VST name field should be used instead); FL's plugin database (.nfo files) maps names on the user's machine.

**Prior work:**
| Project | Language | License | Class | Notes |
|---|---|---|---|---|
| demberto/PyFLP (and forks e.g. Meowrium/PyFLP) | Python | 1.x GPL-3.0; changelog says 2.0 switched to MIT. Verify LICENSE in pinned release | A if MIT confirmed, else C | VSTPlugin exposes name, vendor, plugin path; mixer slots and channel plugins |
| monadgroup/FLParser | C# | GPL (per PyFLP changelog) | C | Original format research |
| vaguilera/flpviewer | Go | GPL-3.0 | C | Shows samples and VSTs |
| dawtool | Python | Check repo | Verify | Based on LMMS, PyDaw, FLParser work |
| LMMS FLP import | C++ | GPL | C | Older format knowledge |
| bravoh-daw | Rust | MIT | A | Includes FL plugins |
| demberto/fl-plugin-db-organiser | Python | Check repo | Verify | Reads FL plugin database .nfo files (useful for installed inventory on FL machines) |

### 4.6 Cubase / Nuendo (.cpr / .npr) - Phase 3

**Container:** binary, RIFF-like, big-endian chunks. Contains class-name strings for internal objects, plus plugin names and GUIDs as readable strings.

**Where plugins live:** plugin entries carry the plugin name and a 32-hex-character GUID (VST3 CID). Project also records the Cubase version and architecture (32/64-bit).

**Pitfalls:** no official docs; format evolves between major versions; Cubase 14+ can export DAWproject as a more reliable fallback.

**Prior work:**
| Project | Language | License | Class | Notes |
|---|---|---|---|---|
| fgimian/cubase-project-plugins | Go | MIT | A | Purpose-built: lists plugins used in .cpr files plus Cubase version; GUID/name ignore config. Best starting point |
| schwifty00/CubaseTools | Python | Check repo | Verify | Cubase 10 to 15; plugin chains, name, vendor, bypass; has docs/ on CPR format |
| omeriko9/Cubase-Project-File-Reverse-Engineering | C# | Check repo | Verify | SX2/SX3 era; tree view of file hierarchy |

### 4.7 Logic Pro / GarageBand (.logicx / .band) - Phase 4

**Container:** macOS package (a folder). Layout:
```
Project.logicx/
  Alternatives/000/MetaData.plist    tempo, key, time signature
  Alternatives/000/ProjectData       binary project (the hard part)
  Resources/ProjectInformation.plist Logic version
  Media/                             audio files
```
Multiple alternatives (000, 001...) can exist; scan the active one (check plists for which is current) and optionally all.

**ProjectData:** undocumented little-endian chunk-based binary, starting with bytes `23 47 c0 ab` per logicx-analyzer. Channel strip blocks (called "OCuA" in logicxkit) hold plugin references. Plugins are Audio Units: identified by type / subtype / manufacturer four-char codes, plus Apple's stock plugins.

**Approach:**
1. Read plists (easy, confirmed).
2. Walk the chunk structure using published notes to find channel strip blocks and AU identifiers.
3. Fallback: string-level scan for AU names and component codes, marked `heuristic` (bravoh-daw uses string-level analysis for Logic plugin chains).
4. Resolve AU codes to names via the installed inventory (AU Info.plist AudioComponents) and KB.

**Pitfalls:** Logic updates may change layout (LogicProFormatWriter warns about this); custom track names were still an open problem in logicx-analyzer; GarageBand .band differences need fixtures.

**Prior work:**
| Project | Language | License | Class | Notes |
|---|---|---|---|---|
| geoffmyers/logicx-analyzer | Python (stdlib) | Check repo | Verify | Plugin detection, Session Players presets; about 60% of format understood per README |
| jonkubis/LogicProFormatWriter | Python | MIT | A | Writer, but includes PROJECTDATA_FORMAT.md byte-level spec and RE workbench tools |
| ebravofm/logicxkit (and fork phierceweb/logicxkit) | Python + Swift | Check repo | Verify | Reads channel strips and 3rd-party AU state; documents the one-change-per-save diff method |
| bravoh-daw | Rust | MIT | A | String-level plugin chain extraction for Logic |
| audiohacking/daw2logic | Python | Check repo | Verify | Uses LogicProFormatWriter; references AU preset format docs |

### 4.8 Pro Tools - Phase 5

#### 4.8a Text export (ship first)
User runs File > Export > Session Info as Text in Pro Tools with the plugin list option enabled. The text file lists session info, tracks, and plugins. Parse sections by their header lines. Confirm current option names and section headers against real exports from the current Pro Tools version.

UI: when the user drops a .ptx before 5b is ready, show a short instruction card for creating this export.

#### 4.8b Native .ptx
**Decryption (solved):** files are XOR-obfuscated. The key is derived from two header bytes using a modular inverse calculation; older .pts files use a different multiplier and key indexing.

**Structure (solved for audio/MIDI):** decrypted data is a recursive block tree. Each block has a sentinel ("ZMARK"), type, size, and content type. Known content types cover audio file lists, track names, regions, and timing. ptformat's compatibility table covers PT 5 to 12 for audio/MIDI.

**Plugin inserts (unsolved publicly):** no known public project extracts inserts. Method:
1. Create a blank session, save.
2. Add one known AAX plugin to insert A on one track, save as a new file.
3. Decrypt both, dump the block trees, diff.
4. Repeat: different plugin, different slot (A to J), different track, bypassed, on an aux, instrument track.
5. Document findings in `docs/format-notes/protools.md`.
6. Confirm on current PT and at least PT 12.

AAX identity: AAX plugins are identified by manufacturer and product IDs (four-char codes). Map to names via KB, since AAX doesn't ship a readable metadata file like moduleinfo.json.

**Prior work:**
| Project | Language | License | Class | Notes |
|---|---|---|---|---|
| zamaudio/ptformat (Damien Zammit, Robin Gareus) | C++ | LGPL-2.1+ | B | The foundation. Ships in Ardour 9. Includes crafted test sessions for regression |
| Ardour PT import code | C++ | GPL-2+ | C | Shows how ptformat output is used |
| jacobtodd/protools-to-logic | Python | Non-commercial | C | Clear written explanation of XOR key derivation and block walk in README |

Legal review required before shipping 5b (SPEC-01 section 4).

### 4.9 Bitwig native (.bwproject) - Phase 7

Proprietary binary. Plugin file paths appear as readable strings (a KVR forum user extracted them with `strings | grep .so`). Reader: string scan for plugin paths/names, all results `heuristic`. Primary guidance to users: export DAWproject for an exact result. Reference: jaxter184/bwEdit-Python (lists tracks, partial).

---

## 5. Plugin identity resolution

Goal: turn a raw plugin reference into one canonical plugin, even across formats.

**Identity keys by format:**
| Format | Key |
|---|---|
| VST3 | Class ID (32 hex, uppercase) |
| VST2 | 4-char unique ID (store as int and as 4 ASCII chars) + vendor |
| AU | type + subtype + manufacturer (three 4-char codes) |
| CLAP | reverse-DNS id string |
| AAX | manufacturer ID + product ID (+ plugin ID) |
| Stock | DAW + internal device name |

**Resolution order:**
1. Exact key match against installed inventory.
2. Exact key match against KB.
3. Cross-format match: same plugin in a different format (project uses VST2 Serum, user has VST3 Serum). Use KB `aliases` linking keys across formats; fall back to normalized vendor + name.
4. Normalized name + vendor (lowercase, strip "x64", "(x64)", "VST3", "Stereo/Mono", version suffixes), marked `probable`.
5. Unresolved: show raw name, mark "unknown plugin", offer opt-in report to improve KB.

**Output states in the report:** Installed (same format) / Installed (different format: will this DAW auto-substitute? KB note) / Not installed / Stock (needs DAW X) / Unknown.

---

## 6. Installed plugin inventory

Scan the user's machine so the report can say "installed" or "missing".

**Default locations:**
| OS | Format | Paths |
|---|---|---|
| Windows | VST3 | `C:\Program Files\Common Files\VST3` |
| Windows | VST2 | `C:\Program Files\VSTPlugins`, `C:\Program Files\Steinberg\VSTPlugins`, `C:\Program Files\Common Files\VST2`, plus registry VSTPluginsPath values |
| Windows | CLAP | `C:\Program Files\Common Files\CLAP`, `%LOCALAPPDATA%\Programs\Common\CLAP` |
| Windows | AAX | `C:\Program Files\Common Files\Avid\Audio\Plug-Ins` |
| macOS | VST3 | `/Library/Audio/Plug-Ins/VST3`, `~/Library/Audio/Plug-Ins/VST3` |
| macOS | VST2 | `/Library/Audio/Plug-Ins/VST`, `~/Library/Audio/Plug-Ins/VST` |
| macOS | AU | `/Library/Audio/Plug-Ins/Components`, `~/Library/Audio/Plug-Ins/Components` |
| macOS | CLAP | `/Library/Audio/Plug-Ins/CLAP`, `~/Library/Audio/Plug-Ins/CLAP` |
| macOS | AAX | `/Library/Application Support/Avid/Audio/Plug-Ins` |

Plus user-added custom folders (settings). Verify paths against current official docs for each format.

**Metadata sources (no binary loading needed):**
- **VST3:** `moduleinfo.json` inside the bundle (`Contents/Resources/moduleinfo.json`; SDK 3.7.5 used `Contents/moduleinfo.json`). JSON5 format. Contains Factory Info (Vendor, URL, E-Mail) and a Classes list (CID, Name, Vendor, Version, Category, Sub Categories). Newer plugins only; older VST3s lack it.
- **AU (macOS):** bundle `Info.plist` `AudioComponents` array (type, subtype, manufacturer, name as "Vendor: Name", version) plus `CFBundleIdentifier`, `CFBundleShortVersionString`.
- **All macOS bundles:** Mach-O header for architecture (arm64 / x86_64 / universal).
- **Windows binaries:** PE version resource (company name, product name, version) and PE header for architecture (32/64-bit).

**Metadata requiring a sandboxed probe (child process, timeout, optional):**
- VST3 without moduleinfo.json: load factory, read PFactoryInfo and PClassInfo.
- CLAP: load and read `clap_plugin_descriptor` (id, name, vendor, url, manual_url, support_url, version).
- VST2: load to get unique ID and vendor string.

Cache results keyed by path + modified time + size; rescan only changed items.

**Reference projects:** Pluginventory (MIT, macOS scanner, bundle-ID identity, FSEvents monitoring), vst3-host crate (moduleinfo.json reader example, probe with timeout), Steinberg VST3 developer portal "ModuleInfo JSON" page, free-audio/clap headers, `clap-info` tool in the free-audio org, JUCE `KnownPluginList` / `PluginDirectoryScanner` (JUCE license: check terms before use).

---

## 7. Knowledge base

Bundled JSON, versioned, updatable online, community-editable on GitHub.

**kb/vendors.json**
```json
{
  "id": "fabfilter",
  "name": "FabFilter",
  "aliases": ["FabFilter Software Instruments"],
  "homepage": "https://www.fabfilter.com",
  "support_url": null,
  "bundle_id_prefixes": ["com.fabfilter"],
  "vst3_factory_vendor_strings": ["FabFilter"],
  "au_manufacturer_codes": ["FabF"],
  "licensing": ["vendor_serial"],
  "notes": null
}
```

**kb/plugins.json**
```json
{
  "id": "fabfilter-pro-q-4",
  "vendor_id": "fabfilter",
  "name": "Pro-Q 4",
  "keys": {
    "vst3_cid": [],
    "vst2_unique_id": [],
    "au": [{"type": "aufx", "subtype": "", "manufacturer": "FabF"}],
    "clap_id": [],
    "aax": []
  },
  "homepage": "https://www.fabfilter.com/products/pro-q-4-equalizer-plug-in",
  "manual_url": null,
  "category": "effect/eq",
  "formats": ["vst3", "au", "aax", "clap"],
  "platforms": ["win", "mac"],
  "apple_silicon_native": true,
  "price_model": "paid",
  "licensing": ["vendor_serial"],
  "status": "active",
  "successor_id": null,
  "free_alternatives": [],
  "last_verified": "2026-09-25"
}
```
(Example values illustrate the schema only; populate from official vendor sites, and fill IDs from fixtures and moduleinfo.json.)

**Enumerations:**
- `licensing`: `none`, `ilok_cloud`, `ilok_dongle`, `ilok_machine`, `vendor_account`, `vendor_serial`, `challenge_response`, `dongle_other`, `subscription`
- `price_model`: `free`, `paid`, `subscription`, `bundled_with_daw`, `freemium`
- `status`: `active`, `discontinued`, `replaced`, `abandoned`

**Sourcing rules:**
- Links only to official vendor pages. Never scrape third-party databases (respect terms of service). Fallback is a search link, not scraped data.
- Every entry has `last_verified`. Entries older than 12 months show "info may be out of date".
- IDs (CIDs, AU codes) come from real installed copies or fixtures, never guessed.

**Homepage link chain:** SPEC-01 Phase 2.

---

## 8. Reader acceptance checklist (every reader)

- [ ] Detects its format from content (renamed-file fixture passes)
- [ ] Handles all crafted fixtures in SPEC-01 section 6 that the DAW supports
- [ ] Outputs valid data-model JSON; unknown fields null
- [ ] Correct instance counts, track assignment, nesting, bypass
- [ ] Stock devices labeled as stock
- [ ] Opens read-only; never writes to the source
- [ ] Streams or bounds memory on large files (test with a 500 MB+ project where possible)
- [ ] Corrupt/truncated input returns a clear error, never crashes (fuzz test)
- [ ] Every outside project consulted is in the license ledger with its class
- [ ] Format notes written to `docs/format-notes/<format>.md`

---

## 9. Detectable data catalog

Everything a scan can find, and where. The report shows all of it (see SPEC-03 for where each item appears), and both exports include all of it (section 10).

### 9.1 Availability legend

| Mark | Meaning |
|---|---|
| Y | Expected to be readable: plain/documented format, or already extracted by existing prior work |
| R | Probably stored, needs reverse-engineering verification with fixtures before shipping |
| H | Heuristic only (string scanning), shown with a heuristic marker |
| - | Not stored in this format, or not applicable |
| ? | Unknown. Research during that reader's phase and update this table |

Columns: RPP = REAPER, ALS = Ableton, DAWP = DAWproject, S1 = Studio One, FL = FL Studio, CPR = Cubase/Nuendo, LGX = Logic, PTT = Pro Tools text export, PTX = Pro Tools binary, BW = Bitwig native.

**This table is a starting hypothesis.** Each reader phase must confirm or correct its column using fixtures, and the table is updated as part of that phase's acceptance.

### 9.2 Project-level facts (from the project file)

| Field | RPP | ALS | DAWP | S1 | FL | CPR | LGX | PTT | PTX | BW |
|---|---|---|---|---|---|---|---|---|---|---|
| DAW name and version saved with | Y | Y | Y | R | Y | Y | Y | R | R | ? |
| Project title / artist / genre / comments metadata | R | - | Y | R | Y | ? | ? | - | ? | ? |
| Tempo (initial) | Y | Y | Y | R | Y | ? | Y | ? | ? | ? |
| Tempo changes / tempo automation | Y | Y | Y | ? | R | ? | R | - | ? | ? |
| Time signature(s) and changes | Y | Y | Y | R | Y | ? | Y | ? | ? | ? |
| Key / scale | - | R | - | ? | - | ? | Y | - | ? | ? |
| Project sample rate | Y | ? | - | ? | - | ? | R | Y | Y | ? |
| Bit depth | ? | - | - | ? | - | ? | R | Y | R | ? |
| Arrangement length / song end | Y | Y | Y | R | R | ? | R | R | R | ? |
| Markers / locators / cue points | Y | Y | Y | R | Y | ? | R | Y | R | ? |
| Loop region | Y | Y | ? | ? | ? | ? | ? | - | ? | ? |
| Alternatives / versions inside the project | - | - | - | - | - | - | Y | - | - | - |

### 9.3 Track-level facts

| Field | RPP | ALS | DAWP | S1 | FL | CPR | LGX | PTT | PTX | BW |
|---|---|---|---|---|---|---|---|---|---|---|
| Track names | Y | Y | Y | R | Y | R | H | Y | Y | H |
| Track type (audio/MIDI/instrument/bus/return/master/folder) | Y | Y | Y | R | Y | R | R | R | Y | ? |
| Hierarchy (folders, groups, nesting) | Y | Y | Y | R | R | ? | ? | - | ? | ? |
| Track color | Y | Y | Y | R | Y | ? | ? | - | ? | ? |
| Mute / solo / arm state | Y | Y | Y | R | R | ? | ? | R | ? | ? |
| Volume / pan | Y | Y | Y | R | Y | ? | ? | - | ? | ? |
| Output routing, sends, receives | Y | Y | Y | R | R | R | ? | R | ? | ? |
| Sidechain connections | Y | Y | R | ? | R | ? | ? | - | ? | ? |
| Frozen / flattened state | Y | Y | - | ? | - | ? | ? | - | ? | ? |
| Clip / region count per track | Y | Y | Y | R | Y | ? | R | Y | Y | ? |
| MIDI note count and pitch range | Y | Y | Y | ? | Y | ? | R | - | Y | ? |
| Automation lanes present (what is automated) | Y | Y | Y | ? | R | ? | ? | - | ? | ? |

### 9.4 Plugin-level facts

| Field | RPP | ALS | DAWP | S1 | FL | CPR | LGX | PTT | PTX | BW |
|---|---|---|---|---|---|---|---|---|---|---|
| Plugin name, vendor | Y | Y | Y | R | Y | Y | R | Y | R | H |
| Format (VST2/VST3/AU/AAX/CLAP) | Y | Y | Y | R | Y | Y | Y | R | R | H |
| Exact identity (CID / unique ID / AU codes / CLAP id) | Y | Y | Y | R | Y | Y | R | - | R | H |
| Track, slot position | Y | Y | Y | R | Y | R | R | Y | R | - |
| Instrument vs effect role | Y | Y | Y | R | Y | R | R | R | R | - |
| Bypassed / disabled | Y | Y | Y | R | R | Y | ? | R | R | - |
| Nested in rack / container / chain | Y | Y | Y | R | - | ? | ? | - | ? | - |
| Plugin version stored in project | ? | ? | R | ? | ? | ? | ? | - | ? | - |
| Preset / program name | R | R | - | ? | R | ? | R | - | ? | - |
| Plugin parameters automated | Y | Y | Y | ? | R | ? | ? | - | ? | - |
| Plugin state size (bytes) | Y | Y | Y | R | R | ? | ? | - | ? | - |
| Stock / built-in devices | Y | Y | Y | R | Y | R | R | R | R | H |

### 9.5 Media and content

| Field | RPP | ALS | DAWP | S1 | FL | CPR | LGX | PTT | PTX | BW |
|---|---|---|---|---|---|---|---|---|---|---|
| Referenced audio files (paths) | Y | Y | Y | Y | Y | R | Y | Y | Y | H |
| Referenced video files | Y | Y | ? | R | - | ? | ? | R | ? | ? |
| Samples inside sampler instruments (Simpler/Sampler, Slicex, EXS, ReaSamplOmatic) | R | Y | - | ? | Y | ? | R | - | - | ? |
| Max for Live devices (.amxd) | - | Y | - | - | - | - | - | - | - | - |
| External hardware devices (external instrument, hardware inserts) | R | Y | ? | ? | R | ? | ? | R | ? | ? |
| Third-party content libraries (Kontakt, Omnisphere, etc.) inside plugin state | H | H | H | H | H | H | H | - | H | - |

### 9.6 Facts from the filesystem (all formats)

These don't depend on the DAW format, so they are available for every scan where the files are present:

- Project file size, created and modified time
- Project folder total size and file count
- For each referenced media file: exists / missing, inside or outside the project folder, size, and header info read from the audio file itself (format, sample rate, bit depth, channels, duration)
- Media sample rate mismatches against the project sample rate
- Unused files: audio files in the project folder that the project doesn't reference
- Duplicate media (same content hash under different names)
- Backup and autosave files present (count, newest date)
- Source hints from media paths (e.g. paths containing Splice, Loopcloud, Downloads, Desktop, a USB volume), marked heuristic

### 9.7 Facts from enrichment (not in the project file)

Listed here so the catalog is complete. Sources defined in sections 5 to 7.

- Resolution state (installed same format, installed other format, missing, stock, unknown)
- Installed version, installed path, installed architecture
- Homepage, manual, support links, and which source each link came from
- Licensing system, price model, platforms, formats available, Apple Silicon status, status (active/discontinued), free alternatives
- KB `last_verified` date

### 9.8 Derived facts (computed by the report builder)

- Counts: tracks by type, unique plugins, plugin instances, missing plugins, stock devices, heuristic results
- Most-used plugin in the project
- Platform compatibility ("opens on Windows?", "opens on Mac?")
- Send-ready score (SPEC-01 section 8) with the reasons behind it
- Warnings list (codes in section 10.4)

---

## 10. Report export formats

Two formats, both containing everything from section 9 that the scan found. Users pick from the Export menu (SPEC-03 section 6).

### 10.1 General rules

- UTF-8 everywhere.
- Unknown values: `null` in JSON, empty cell in CSV. Never guess.
- A field the reader **can't** read for this format is different from a field that was read and is empty. The JSON lists unreadable fields in `unavailable_fields`; the CSV project row lists them in the `project_unavailable_fields` column.
- Timestamps in ISO 8601 with offset (e.g. `2026-09-25T14:32:00-07:00`).
- IDs are stable within a report (`t1`, `p1`, `m1`...) so rows can be cross-referenced.
- **Redact paths option** (off by default): replaces the user's home folder with `~` and drops absolute paths outside the project folder, for when the report is shared.
- Default filenames: `<ProjectName>_rackcheck_<YYYY-MM-DD_HHMM>.json` and `.csv`.

### 10.2 JSON (full report)

Published as a JSON Schema at `schemas/report-v1.schema.json`. Schema is versioned; additive changes bump minor, breaking changes bump major. The app can reopen a JSON report and display it without the original project, so a collaborator can view a report someone sent them.

```json
{
  "schema_version": "1.0.0",
  "generated_at": "2026-09-25T14:32:00-07:00",
  "app": { "name": "Rackcheck", "version": "1.0.0", "kb_version": "2026.09.20" },
  "machine": { "os": "macOS 15.6", "arch": "arm64", "inventory_scanned_at": "..." },
  "options": { "redact_paths": false },

  "source": {
    "path": "...", "file_size_bytes": 0, "created_at": "...", "modified_at": "...",
    "format": "ableton_als", "detection_confidence": "confirmed", "detection_reason": "...",
    "daw_name": "Ableton Live", "daw_version": "12.1.5", "reader_version": "1.0.0"
  },

  "project": {
    "name": "...", "title": null, "artist": null, "genre": null, "comments": null,
    "tempo_bpm": 128.0, "tempo_changes": [{ "position_beats": 0, "bpm": 128.0 }],
    "time_signatures": [{ "position_beats": 0, "value": "4/4" }],
    "key": null, "sample_rate": 48000, "bit_depth": null,
    "length_seconds": null, "length_bars": null,
    "markers": [{ "name": "Drop", "position_beats": 64 }],
    "loop": { "start_beats": null, "end_beats": null },
    "alternatives": [],
    "folder": { "path": "...", "total_size_bytes": 0, "file_count": 0,
                "backup_count": 0, "newest_backup_at": null },
    "unavailable_fields": ["key", "bit_depth"]
  },

  "tracks": [{
    "id": "t1", "name": "Bass", "type": "instrument", "parent_id": null,
    "color": "#a2eabf", "muted": false, "solo": false, "armed": false, "frozen": false,
    "volume_db": null, "pan": null,
    "output": "Master", "sends": [{ "target_id": "t9", "level_db": null }],
    "sidechain_sources": [], "clip_count": 4,
    "midi": { "note_count": 212, "lowest": "E1", "highest": "G2" },
    "automated_parameters": ["Volume", "p1:Cutoff"],
    "device_ids": ["p1", "p2"]
  }],

  "plugins": [{
    "id": "p1", "track_id": "t1", "slot_index": 0, "nested_in": null,
    "role": "instrument", "format": "vst3", "name": "Serum", "vendor": "Xfer Records",
    "identity": { "vst3_cid": "...", "vst2_unique_id": null, "au": null,
                  "clap_id": null, "aax": null, "file_hint": null },
    "bypassed": false, "version_in_project": null, "preset_name": null,
    "automated": true, "state_size_bytes": 184320,
    "confidence": "confirmed",
    "resolution": {
      "state": "installed_same_format",
      "matched_by": "vst3_cid",
      "installed": { "version": "1.368", "path": "...", "arch": "arm64" },
      "other_formats_installed": ["vst2"]
    },
    "kb": {
      "kb_id": "xfer-serum", "category": "instrument/synth",
      "licensing": ["vendor_serial"], "price_model": "paid",
      "platforms": ["win", "mac"], "formats_available": ["vst2", "vst3", "au", "aax"],
      "apple_silicon_native": true, "status": "active", "successor_id": null,
      "free_alternatives": ["vital"], "last_verified": "2026-09-01"
    },
    "links": {
      "homepage": { "url": "...", "source": "kb_plugin" },
      "manual": { "url": null, "source": null },
      "support": { "url": null, "source": null }
    },
    "flags": ["vst2_only", "ilok", "intel_only", "32_bit", "discontinued", "stock", "heuristic"]
  }],

  "plugin_summary": [{
    "key": "xfer-serum", "name": "Serum", "vendor": "Xfer Records",
    "instances": 3, "track_ids": ["t1", "t4", "t7"], "bypassed_instances": 1,
    "resolution_state": "installed_same_format"
  }],

  "media": [{
    "id": "m1", "path": "...", "type": "audio", "referenced_by": ["t2"],
    "exists": true, "inside_project_folder": false, "size_bytes": 0, "sha256": "...",
    "audio": { "format": "wav", "sample_rate": 44100, "bit_depth": 24,
               "channels": 2, "duration_seconds": 3.2 },
    "sample_rate_mismatch": true, "duplicate_of": null,
    "source_hint": { "value": "splice", "confidence": "heuristic" }
  }],
  "unused_media": [{ "path": "...", "size_bytes": 0 }],

  "special_content": [{
    "type": "max_for_live | sampler_sample | external_hardware | content_library",
    "name": "...", "track_id": "t3", "plugin_id": null, "path": null,
    "confidence": "confirmed"
  }],

  "summary": {
    "track_counts": { "audio": 0, "midi": 0, "instrument": 0, "return": 0, "group": 0, "master": 1 },
    "unique_plugins": 0, "plugin_instances": 0, "missing_plugins": 0,
    "stock_devices": 0, "heuristic_results": 0,
    "media_files": 0, "missing_media": 0, "media_outside_folder": 0,
    "opens_on": { "windows": true, "mac": true },
    "send_ready": { "score": "yellow", "reasons": ["2 plugins missing", "..."] }
  },

  "warnings": [{
    "code": "PLUGIN_MISSING", "severity": "error | warning | info",
    "message": "Serum is not installed on this computer",
    "related_ids": ["p1"]
  }]
}
```

### 10.3 CSV (full report, single file)

One CSV file containing everything, so it opens in Excel, Numbers or Google Sheets and can be filtered by the `record_type` column.

**File rules:** RFC 4180 quoting, comma delimiter, UTF-8 **with BOM** (so Excel shows accents and non-Latin names correctly), CRLF line endings, one header row. Multi-value cells are joined with `; `. Booleans are `TRUE` / `FALSE`.

**Row types** (in this order in the file):

| record_type | Rows |
|---|---|
| `project` | 1 |
| `summary` | 1 |
| `warning` | 1 per warning |
| `track` | 1 per track |
| `plugin` | 1 per plugin instance |
| `plugin_summary` | 1 per unique plugin |
| `media` | 1 per referenced media file |
| `unused_media` | 1 per unused file |
| `special_content` | 1 per item |

**Columns:** every row has the common columns; each row type fills only its own prefixed columns and leaves the rest empty.

Common: `record_type, id, parent_id, name, report_generated_at, source_file, daw, daw_version`

Project: `project_title, project_artist, project_genre, project_tempo_bpm, project_tempo_changes, project_time_signatures, project_key, project_sample_rate, project_bit_depth, project_length_seconds, project_length_bars, project_markers, project_file_size_bytes, project_modified_at, project_folder_size_bytes, project_backup_count, project_unavailable_fields`

Summary: `summary_tracks_audio, summary_tracks_midi, summary_tracks_instrument, summary_tracks_return, summary_tracks_group, summary_unique_plugins, summary_plugin_instances, summary_missing_plugins, summary_stock_devices, summary_heuristic_results, summary_media_files, summary_missing_media, summary_media_outside_folder, summary_opens_on_windows, summary_opens_on_mac, summary_send_ready_score, summary_send_ready_reasons`

Warning: `warning_code, warning_severity, warning_message, warning_related_ids`

Track: `track_type, track_color, track_muted, track_solo, track_armed, track_frozen, track_volume_db, track_pan, track_output, track_sends, track_sidechain_sources, track_clip_count, track_midi_note_count, track_midi_range, track_automated_parameters, track_plugin_names`

Plugin: `plugin_track_name, plugin_slot, plugin_nested_in, plugin_role, plugin_format, plugin_vendor, plugin_identity, plugin_bypassed, plugin_version_in_project, plugin_preset_name, plugin_automated, plugin_state_size_bytes, plugin_confidence, plugin_resolution_state, plugin_installed_version, plugin_installed_path, plugin_installed_arch, plugin_other_formats_installed, plugin_category, plugin_licensing, plugin_price_model, plugin_platforms, plugin_formats_available, plugin_apple_silicon_native, plugin_status, plugin_free_alternatives, plugin_homepage, plugin_homepage_source, plugin_manual_url, plugin_support_url, plugin_flags, plugin_kb_last_verified`

Plugin summary: `ps_vendor, ps_instances, ps_bypassed_instances, ps_tracks, ps_resolution_state, ps_homepage`

Media: `media_path, media_type, media_referenced_by, media_exists, media_inside_project_folder, media_size_bytes, media_format, media_sample_rate, media_bit_depth, media_channels, media_duration_seconds, media_sample_rate_mismatch, media_duplicate_of, media_source_hint`

Unused media: `unused_path, unused_size_bytes`

Special content: `special_type, special_track_name, special_plugin_id, special_path, special_confidence`

Any field added to the JSON schema later must get a matching CSV column in the same release (tested in CI by comparing the two).

### 10.4 Additional quick exports

- **Plugin list CSV:** one row per unique plugin: `name, vendor, format, instances, tracks, resolution_state, homepage, licensing, price_model`. For people who just want the shopping list.
- **Missing plugins only CSV:** same columns, filtered.
- **HTML report (optional, Phase 2+):** a single self-contained file that looks like the in-app report, easy to email.
- **Library scan (Phase 6):** one JSON per project in a folder, plus one combined CSV with a `project` column added to every row.

### 10.5 Warning codes (initial set)

| Code | Severity | Trigger |
|---|---|---|
| `PLUGIN_MISSING` | error | Plugin not installed in any format |
| `PLUGIN_OTHER_FORMAT` | warning | Installed, but in a different format than the project uses |
| `PLUGIN_UNKNOWN` | warning | Couldn't identify the plugin |
| `PLUGIN_VERSION_OLDER` | warning | Installed version older than the one saved in the project |
| `PLUGIN_VST2_ONLY` | info | Plugin only available as VST2 |
| `PLUGIN_MAC_ONLY` / `PLUGIN_WIN_ONLY` | warning | Plugin limits which OS can open the project |
| `PLUGIN_INTEL_ONLY` | warning | Needs Rosetta on Apple Silicon |
| `PLUGIN_32BIT` | warning | 32-bit plugin, won't load in most modern DAWs |
| `PLUGIN_DISCONTINUED` | info | KB marks it discontinued |
| `PLUGIN_DRM_ILOK` | info | Collaborator needs an iLok license |
| `STOCK_DEVICE_DAW` | info | Project depends on DAW-specific built-in devices |
| `MEDIA_MISSING` | error | Referenced file not found |
| `MEDIA_OUTSIDE_FOLDER` | warning | Referenced file lives outside the project folder |
| `MEDIA_SR_MISMATCH` | info | File sample rate differs from project |
| `MEDIA_UNUSED` | info | Unreferenced files in project folder (with total size) |
| `EXTERNAL_HARDWARE` | warning | Project uses external hardware |
| `SIDECHAIN_PRESENT` | info | Sidechain routing a collaborator must recreate |
| `THIRD_PARTY_CONTENT` | info | Content library detected inside a plugin (heuristic) |
| `HEURISTIC_RESULTS` | info | Some results are from string scanning |
| `DAW_VERSION_NEWER` | warning | Project saved in a newer DAW version than installed (when detectable) |
