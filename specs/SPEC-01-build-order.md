# SPEC-01: Build Order

**Project:** Plugin Dependency Scanner (working name: "Rackcheck")
**Companion specs:** SPEC-02-file-format-readers.md (how each project file is read, everything detectable, export formats), SPEC-03-gui-and-engine-integration.md (GUI and how it talks to the engine)
**Status:** Draft v1, September 2026

---

## 1. What we're building

A desktop app where a user drops in any supported DAW project file (or a folder, or a zip) and gets back:

1. Every plugin the project uses, grouped by track.
2. For each plugin: vendor, format, version, a link to the plugin's homepage, and anything else the user should know (installed or missing, licensing system, platform support, etc.).
3. A project summary with other useful facts (see section 8).

The user should never have to know what format their project is in, where their plugins live, or what a VST3 class ID is. Drop file, read report.

---

## 2. Design principles (apply to every phase)

**P1. One action for the user.** Drag and drop a file, folder, or zip. The app figures out the rest. No format picker, no settings needed for a first scan.

**P2. Detect by content, not extension.** Identify formats by magic bytes and internal structure (see SPEC-02 section 2). Extensions are a hint only. This handles renamed files, backups (.rpp-bak, .als backups, FL autosaves), and zipped projects.

**P3. Never modify the user's project.** Open everything read-only. Copy to a temp location if a library needs a writable path.

**P4. Never guess.** Every extracted fact carries a confidence level: `confirmed` (parsed from a documented or well-verified structure), `probable` (parsed from a reverse-engineered structure verified against fixtures), or `heuristic` (found by string scanning). The UI shows heuristic results with a visible marker. If a field can't be read reliably, leave it empty rather than filling it with a guess.

**P5. Offline first.** Scans must work with no internet. Online lookups (knowledge base updates, version checks) are optional enrichment.

**P6. Never load plugin binaries in the main process.** When scanning installed plugins, read metadata files first (moduleinfo.json, Info.plist). If a binary must be loaded to get info, do it in a separate sandboxed child process with a timeout, because broken plugins crash hosts.

**P7. Privacy.** Project files never leave the user's machine. Any telemetry or "report unknown plugin" feature is opt-in and sends only plugin identity fields, never file paths or project names.

---

## 3. Recommended architecture

```
+-------------------------------------------------------------+
|  GUI (drag & drop, report view, export)                     |
+-------------------------------------------------------------+
|  Report builder (grouping, warnings, summary, export)       |
+-------------------------------------------------------------+
|  Enrichment layer                                           |
|   - Plugin identity resolver (cross-format matching)        |
|   - Knowledge base (vendor/plugin DB, links, licensing)     |
|   - Installed plugin inventory (local machine scan)         |
+-------------------------------------------------------------+
|  Format detector  ->  Reader modules (one per DAW format)   |
+-------------------------------------------------------------+
|  Common data model (ScanResult, PluginRef, TrackRef, ...)   |
+-------------------------------------------------------------+
```

**Recommended stack:** Python 3.12 for the core engine. Reason: most of the reference projects we can learn from are in Python (PyFLP, rpp, dawproject-py, logicx-analyzer, CubaseTools), and a pure-stdlib core packs easily. GUI via pywebview (HTML/JS front end inside a native window) or PySide6. Package with PyInstaller for Windows and macOS.

**Alternative worth evaluating in Phase 0:** bravoh-daw (Rust, MIT) already parses Ableton, FL Studio, Logic and REAPER into one schema including plugins. If it proves accurate on our fixtures, the core could be Rust with a Tauri GUI instead. Decide in Phase 0 after testing both against the fixture set. Do not mix the two long-term.

The core must also run as a CLI (`rackcheck scan <path> --json`). The GUI calls the same engine. The CLI makes testing and fixture regression easy.

---

## 4. License policy (read before using any outside code)

Every outside project used or consulted gets an entry in `docs/LICENSE-LEDGER.md` with: name, URL, license, version/commit checked, and one of these usage classes:

| Class | Licenses | What we may do |
|---|---|---|
| **A: Use code** | MIT, BSD, Apache-2.0, ISC | Copy or depend on it. Keep the copyright notice in `THIRD_PARTY_NOTICES` |
| **B: Link only** | LGPL | Use only as a separately linked library (DLL/.so/.dylib or separate Python package that users could replace). Publish any changes we make to that library |
| **C: Reference only** | GPL, AGPL, non-commercial, "NO-AI" variants, unknown/no license | Read for format knowledge only. Do not copy code. Write our own implementation from notes (clean-room process below) |

**Clean-room process for Class C:**
1. One session reads the Class C source and writes plain-English notes on the format (offsets, field meanings, structure). No code in the notes.
2. A separate session writes our implementation from the notes only, with the Class C source closed.
3. Notes are saved in `docs/format-notes/<format>.md` as proof of process.

When using Claude Code: give it the notes file, not the GPL repo, when writing the parser.

**Always re-check the license on the exact version you use.** Several projects have changed license over time (PyFLP 1.x was GPL-3.0; its changelog says 2.0 switched to MIT; verify the LICENSE file in the release you pin).

Get a lawyer to review the ledger before any paid release. Reverse engineering for interoperability is generally permitted in Canada and the US, but the Pro Tools XOR scheme should be specifically reviewed.

---

## 5. Research protocol (how to find prior work for any phase)

Before writing any reader, spend time finding existing work. Search in this order:

1. **GitHub code and repo search.** Queries: `<extension> parser`, `<DAW name> project file`, `<DAW name> reverse engineer`, `<extension> plugins`. Also check GitHub Topics pages for the DAW name.
2. **Package indexes.** PyPI, crates.io / docs.rs, npm, pkg.go.dev. Search the extension and DAW name.
3. **Converter projects.** They have to parse formats to convert them, and often document the format: DawVert (GPL, reference only), dawtool, DAWproject converters, daw2logic.
4. **Forums.** KVR Audio developer forum and the DAW-specific KVR subforum, Gearspace, the DAW's official forum, REAPER forum (Cockos), Reddit (r/ableton, r/FL_Studio, r/Logic_Studio, r/reaper, r/protools, r/cubase, r/edmproduction).
5. **Vendor developer docs.** Steinberg VST3 developer portal, CLAP repo (free-audio/clap), Apple Audio Unit docs, Bitwig dawproject repo.
6. **Conference talks.** Audio Developer Conference (ADC) videos. Example: dawtool's author presented at ADC 2020.

For every project found, record in the ledger: what it extracts, what DAW versions it was tested on, last commit date, and license class.

---

## 6. Test fixture strategy

Parsers are only as good as the test files behind them. Build a fixture library in `fixtures/<daw>/<version>/`.

**Crafted fixtures (the core method used by ptformat, logicxkit and others):** create minimal projects that differ by one change each:
- `empty` : new project, saved
- `one-vst3-insert`, `one-vst2-insert`, `one-au-insert`, `one-clap-insert`
- `one-instrument` (synth on an instrument track)
- `same-plugin-x3` (instance counting)
- `bypassed-plugin`
- `plugin-on-return-bus`, `plugin-on-master`, `plugin-in-group/rack/container`
- `missing-plugin` (saved with a plugin, then plugin uninstalled)
- `sidechain`
- `unicode-names` (track and plugin names with non-Latin characters)

Use a few free, cross-format plugins so fixtures can be made in every DAW. Good candidates: Surge XT (VST3/AU/CLAP, open source), Vital, TDR Nova, Valhalla Supermassive. Record the exact plugin versions used.

**Real-world fixtures:** ask beta users to donate projects (opt-in, with consent) to catch cases crafted fixtures miss. Store separately, never commit to a public repo.

**Regression rule:** every reader ships with fixtures and expected JSON output. CI runs all fixtures on every commit.

**Version coverage:** for each DAW, fixtures from at least the current major version and one older major version.

---

## 7. Build phases

Each phase ends with a working, testable result. Don't start a phase until the previous one's acceptance criteria pass.

### Phase 0: Foundations
**Goal:** the skeleton everything else plugs into.

Deliverables:
- Repo, CI, `LICENSE-LEDGER.md`, `THIRD_PARTY_NOTICES`
- Common data model (SPEC-02 section 3) as code with JSON serialization
- Format detector (SPEC-02 section 2) returning `format`, `confidence`, `reason`
- Input handling: single file, folder (find project files inside), zip (extract to temp, then detect), macOS package bundles (.logicx is a folder)
- CLI: `rackcheck scan <path> [--json]`
- Reader interface: each reader is a module with `can_read(path) -> confidence` and `read(path) -> ScanResult`
- Evaluate bravoh-daw vs Python-native approach against the first fixtures; record decision in `docs/DECISIONS.md`

Acceptance: detector correctly identifies one fixture of every target format, including a renamed file and a zipped project.

Research sources: bravoh-daw on docs.rs (MIT, unified schema, "omit rather than guess" doctrine worth copying).

### Phase 1: Easy readers
**Goal:** plugin lists from the three easiest sources.

Deliverables:
- REAPER .rpp reader (plain text)
- Ableton .als reader (gzipped XML)
- DAWproject .dawproject reader (zip + XML). This gives Bitwig, Cubase 14+, and Studio One coverage when users export DAWproject

Acceptance: all crafted fixtures for these three produce correct plugin lists, track assignment, instance counts, and bypass state.

Research sources: see SPEC-02 sections 4.1 to 4.3 (Perlence/rpp BSD-3, rppxml, reaproj; Pluginventory MIT, als-tools, als-parser; bitwig/dawproject MIT, dawproject-py MIT).

### Phase 2: Enrichment and first release (MVP)
**Goal:** the report the user actually wants. After this phase the app is shippable for REAPER, Ableton, and DAWproject users.

Deliverables:
- **Installed plugin inventory** (Windows + macOS): scan standard plugin folders, read VST3 `moduleinfo.json`, AU `Info.plist`, CLAP descriptors (sandboxed), VST2 binaries (name from filename + sandboxed probe if needed). See SPEC-02 section 6.
- **Plugin identity resolver:** matches a plugin reference from a project to an installed plugin and to the knowledge base, across formats (SPEC-02 section 5).
- **Knowledge base v1:** `kb/vendors.json` and `kb/plugins.json` (schema in SPEC-02 section 7). Seed with the top ~100 vendors. Community-editable via GitHub pull requests. App ships a bundled copy and optionally fetches updates.
- **Homepage link resolution chain** (first hit wins):
  1. Knowledge base entry for the exact plugin
  2. VST3 `moduleinfo.json` Factory Info URL, or CLAP descriptor `url` (from the installed copy)
  3. Knowledge base vendor homepage
  4. Reverse-domain from macOS bundle ID (com.fabfilter.x -> fabfilter.com), marked `heuristic`
  5. A search link (never scraped), e.g. a KVR Audio search URL for the plugin name, marked "search"
- **GUI v1:** built per SPEC-03: drop zone, report view, per-plugin detail panel, missing plugins highlighted
- **Report export:** full-report JSON and CSV exactly as defined in SPEC-02 section 10, plus the quick "plugin list" CSV. HTML/PDF report is optional in this phase
- Installer builds for Windows and macOS

Acceptance: a non-technical tester can install, drop an Ableton project, and get a correct report with working homepage links for every plugin from a top-100 vendor, without reading instructions.

Research sources: Pluginventory (MIT, macOS; publisher website via plist metadata, reverse-domain lookup, and Homebrew cask mappings; bundle-ID keyed identity), Steinberg VST3 developer portal "ModuleInfo JSON" page, free-audio/clap repo (plugin descriptor struct), vst3-host crate on docs.rs (moduleinfo parsing example).

### Phase 3: Studio One native, FL Studio, Cubase native
**Goal:** cover three large user bases without requiring DAWproject export.

Deliverables:
- Studio One / Fender Studio Pro .song reader (zip + XML)
- FL Studio .flp reader (binary event stream)
- Cubase / Nuendo .cpr / .npr reader (binary, RIFF-like)

Acceptance: fixtures pass for current and one previous major version of each.

Research sources: SPEC-02 sections 4.4 to 4.6 (StudioOneTools, SongLens; PyFLP, FLParser, dawtool; fgimian/cubase-project-plugins MIT Go, CubaseTools, omeriko9 Cubase RE).

### Phase 4: Logic Pro and GarageBand
**Goal:** the biggest Mac-only user base.

Deliverables:
- .logicx reader: bundle handling, MetaData.plist, ProjectData chunk walk for plugin (AU) references
- GarageBand .band support (same family, verify)

Acceptance: fixtures from current Logic version pass; AU plugins identified by manufacturer/type/subtype codes and resolved to names.

Note: Logic is further along in public reverse engineering than earlier assumed. Several 2025-2026 projects decode ProjectData (logicx-analyzer, LogicProFormatWriter with a byte-level PROJECTDATA_FORMAT.md, logicxkit). Still undocumented by Apple, so expect breakage when Logic updates.

Research sources: SPEC-02 section 4.7.

### Phase 5: Pro Tools
**Goal:** the most-used DAW in commercial studios.

Deliverables, in this order:
- **5a. Text export reader:** parse Pro Tools "Export Session Info as Text" output (with the plugin list option enabled). Ships first; works on every PT version.
- **5b. Native .ptx reader:** XOR decryption and block walk (documented by ptformat), then plugin insert extraction, which has no known public solution and needs original research using crafted fixtures.
- AAX plugin identity: map AAX IDs to vendor/product (knowledge base).

Acceptance 5a: text exports from current PT parse correctly. Acceptance 5b: crafted .ptx fixtures with known inserts decode correctly on current PT and PT 12.

Research sources: SPEC-02 section 4.8. Legal review of XOR decryption before release.

### Phase 6: Power features
- **Library scan:** point at a folder of projects, get cross-project stats (most used plugins, which projects break if you uninstall X)
- **Collaborator compare:** export "my installed plugins" file, share it; the scanner compares a project against someone else's inventory ("these 3 plugins are missing on Alex's machine")
- **Scan diff:** compare two versions of the same project (plugins added/removed)
- **Send-ready checklist:** see section 8
- Nested content detection: Kontakt library names, Omnisphere patches, etc. inside plugin state (stretch goal, per-plugin work)

### Phase 7: Long tail
- Bitwig native .bwproject (currently string-scan only; DAWproject export is the reliable path)
- Reason, Cakewalk/Sonar, Digital Performer, LUNA: only if user demand justifies it
- Linux build

---

## 8. Report contents

This section is the user-facing summary. The complete list of everything a scan can detect, with per-DAW availability, is in SPEC-02 section 9. The export formats are in SPEC-02 section 10. The report must show every detected field somewhere (summary, tabs, or detail panels) and every detected field must appear in the JSON and CSV exports.

### Per plugin
| Field | Source |
|---|---|
| Name, vendor | Project file, then installed inventory, then KB |
| Format used in project (VST2/VST3/AU/AAX/CLAP/stock) | Project file |
| Version saved in project (if stored) vs installed version | Project file vs inventory |
| Installed on this machine? (yes / no / different format available) | Inventory |
| Tracks it's used on, instance count, bypassed instances | Project file |
| Instrument or effect | Project file / plugin category |
| Homepage, manual, support links | Link chain (Phase 2) |
| Licensing system (iLok, vendor account, dongle, none) | KB |
| Price model (free, paid, subscription, bundled with DAW) | KB |
| Platforms (Win/Mac/Linux) and formats available | KB |
| Apple Silicon native / Intel only | Inventory (macOS binary arch), KB |
| Status flags: VST2-only (deprecated format), discontinued, 32-bit | KB + inventory |
| Stock plugin warning ("Ableton stock device; collaborator needs Ableton") | Reader |
| Free alternative suggestion (optional) | KB |

### Project summary
- DAW and version the project was saved with
- Tempo, time signature, key (where stored), length, sample rate
- Track counts by type
- Plugin totals: unique, instances, missing, heuristic-confidence count
- Referenced audio files: count, missing files, files outside the project folder (a common cause of "missing media" for collaborators), total media size
- Third-party content libraries detected (Phase 6)
- External hardware / MIDI devices referenced (where stored)
- Sidechain routing present (collaborator must recreate if converting)

### Warnings (plain language, top of report)
- "4 plugins are not installed on this computer"
- "This project uses AU plugins, which only work on Mac"
- "2 plugins are VST2 only; some DAWs are dropping VST2"
- "3 plugins use iLok; your collaborator needs licenses for them"
- "12 audio files are outside the project folder and won't be included if you send the folder"
- "Consider freezing or printing these tracks before sending: <plugins the collaborator lacks>"

### Send-ready score (Phase 6)
One simple indicator (green / yellow / red) answering "if I send this project to someone, will it open correctly?"

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| DAW updates break binary readers (Logic, Pro Tools, Cubase, FL) | Fixture regression per version; graceful degradation to heuristic string scan with clear marking; fast release process |
| License contamination from GPL references | License ledger + clean-room process (section 4) |
| Knowledge base goes stale | Community PRs, remote updates, "report missing/incorrect info" button (opt-in) |
| Plugin scanning crashes the app | Sandboxed child process with timeout (P6) |
| Vendor objections to linking/metadata | Link only to official vendor pages; never redistribute plugin binaries or presets |
| Existing competitor (Pluginventory: macOS, Ableton-only, MIT) | Our differentiators: cross-platform, many DAWs, collaboration features |
