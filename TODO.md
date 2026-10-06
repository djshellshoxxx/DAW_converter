# TODO: Iteration 2026-10-06

## Completed (Phase 0 + Phase 1 + Phase 2 Core)

**Phase 0 foundations (v0.1):**
- Repository structure, CI (GitHub Actions, tox, pytest)
- Common data model (ScanResult, PluginRef, TrackRef) with JSON serialization
- Format detector: magic bytes + content analysis covering REAPER, Ableton, DAWproject, Studio One, FL Studio, Cubase, Logic, Pro Tools
- Input handling: single files, folders, zips, macOS bundles
- Safety hardening: zip bombs/slip, gzip bombs, XML entity attacks
- CLI: `rackcheck scan <path> [--json]`
- Reader interface and base class

**Phase 1 readers (completed 2026-09-29):**
- REAPER .rpp reader: plugin extraction, media refs, nested sections, bypass state, RECORD_PATH
- Ableton .als reader: gzip + XML parsing, PluginDevice extraction, VST2/VST3/AU identity, racks with nesting, Max for Live detection
- DAWproject .dawproject reader: ZIP + XML parsing, VST2/VST3/CLAP/AU plugin detection, deviceID extraction

**Phase 2 core (completed 2026-09-29):**
- Installed plugin inventory scanner: Windows + macOS, VST3/VST2/AU/CLAP/AAX, moduleinfo.json, Info.plist, Mach-O arch detection
- Knowledge base v1: vendors.json + plugins.json schema, 41 vendors/37 plugins seed data (unverified)
- Plugin identity resolver: 5 match tiers (exact key → file hint → KB alias → normalized name → name only), cross-format matching
- Report builder: SourceInfo + project facts + enrichment into JSON report (SPEC-02 Section 10.2)
- Exports: JSON full report, CSV full report + plugin list (SPEC-02 Section 10.3-4), CSV injection prevention
- GUI v1 (pywebview + HTML/CSS/TypeScript): home (drop zone, recent scans), scanning progress, report view (tabs: Plugins/Tracks/Media/Project/Raw), plugin detail panel, export JSON/CSV, settings (plugin folders)
- Engine API bridge: 7 public methods (detect, start_scan, cancel_job, get_report, get_plugin_folders, get_log_folder, export_*), path authorization (native dialogs, drop zone, recent reopens, settings storage)
- Test suite: 278 tests passing (including ZIP detection safety regression)

---

## Next (Ordered by Priority)

### 1. Human verification: Real-window GUI check
- Launch rackcheck-gui on Windows with pywebview rendering
- Drop test projects (REAPER, Ableton, DAWproject) to verify UI responsiveness, tab rendering, export functionality
- Confirm drag-drop paths are correctly authorized and scans complete
- Timeline: 1-2 hours (before Phase 1 fixture handoff to beta)

### 2. Create real crafted fixtures (Phase 1 DAWs)
- In REAPER 7.x: create four projects (empty, one-VST3-insert, same-plugin-x3, bypassed) using Surge XT/Vital as test plugins
- In Ableton Live 12: create four projects (empty, VST2/VST3 racks, nested racks, Max for Live device) with TDR Nova
- In Bitwig Studio 7.x: create DAWproject exports (from above) to validate reader on cross-DAW files
- Export all as .rpp/.als/.dawproject files with hashes logged
- Timeline: 3-4 hours (needs licenses; Bitwig uses DAWproject export path, no native reader needed yet)

### 3. Expand KB to ~100 vendors with human verification
- Current seed: 41 vendors (unverified). Target: ~100 top audio vendors (Splice, KVR, user surveys)
- Format: vendors.json (id, name, aliases, website) + plugins.json (id, vendor_id, name, aliases, platform_support, vst2_only, discontinued, verified: true)
- Verification workflow: research each vendor's official site, GitHub, KVR Audio, manual plugin format checks
- Build tool: compile to signed kb-bundle.json + manifest (Phase 2)
- Timeline: 8-12 hours (human effort, can be parallelized)

### 4. Implement missing warning codes
- EXTERNAL_HARDWARE: scan project config for hardware inserts (not yet parseable from Ableton/REAPER APIs)
- SIDECHAIN_PRESENT: track routing analysis (REAPER .rpp has routing data, Ableton XML has send tracks)
- THIRD_PARTY_CONTENT: project file hash / license marker detection (Phase 6 feature)
- DAW_VERSION_NEWER: DAW export header version check (REAPER version in .rpp, Ableton version in .als XML)
- Timeline: 2-3 hours (after fixture validation confirms reader output correctness)

### 5. Phase 2 release: Signing, packaging, and build pipeline (SPEC-05)
- Windows: Inno Setup installer + Azure Artifact Signing (EV code signing cert needed)
- macOS: signed .dmg + notarization (Apple Developer Program cert needed, ~USD 99/year)
- CI: test → build → sign → smoke-test → publish (GitHub Actions)
- Version: v1.0.0 (semantic versioning)
- THIRD_PARTY_NOTICES and LICENSE-LEDGER regenerated
- Timeline: 6-8 hours (+ cert procurement time, can be parallelized with KB verification)

### 6. Phase 3 readers (after v1.0.0 ships)
- Studio One .song reader (ZIP + XML, free + paid versions have different schemas)
- FL Studio .flp reader (binary event stream, reverse-engineered from PyFLP)
- Cubase .cpr reader (proprietary RIFF-like binary, limited public documentation)
- Timeline: Phase 3 starts after Phase 2 release

---

## Blockers

### Critical (blocks shipping v1.0.0)

1. **Real DAW-saved fixtures:** Tests use synthetic projects only; reader acceptance criteria (SPEC-01 Section 6) require fixtures created in each DAW and saved to disk. No real Ableton/REAPER/Bitwig projects available yet. Phase 1 agents created readers blind (no real fixtures to validate against). Fix: coordinate with beta testers to create and donate crafted projects, or build fixtures locally during Phase 1 fixture handoff.

2. **Code-signing certificates:**
   - Windows: Azure Artifact Signing (or OV code signing cert) not yet purchased; required for Inno Setup installer signing. Cost ~USD 150/year or one-time.
   - macOS: Apple Developer Program membership not set up; required for code signing and notarization. Cost USD 99/year. Alternative: use GitHub Actions macOS runners (slower, requires CI setup).

3. **Legal review for Pro Tools .ptx decryption:** Phase 5b reader requires XOR decryption (published in ptformat's LGPL code). Canadian/US law allows reverse engineering for interoperability, but must be reviewed by a lawyer before shipping. Timeline: deferred to Phase 5, but budget must include legal hours (SPEC-09).

### High (blocks Phase 2 readers)

4. **macOS test machine:** Logic Pro (Phase 4) and GarageBand readers require a Mac for format analysis and fixture creation. AU plugin identity resolution also needs macOS. Alternative: use GitHub Actions macOS runners (acceptable if not on critical path during Phase 1).

5. **DAW licenses for fixture creation:** Building real crafted fixtures requires current (and prior major) versions of REAPER, Ableton, DAWproject (via Bitwig), Studio One, FL Studio, Cubase, Logic Pro. REAPER/Bitwig are affordable; others require vendor site licenses or NFR programs. Budget item in SPEC-09 Section 10.

### Medium (docs, not code)

6. **Format notes for GPL references:** Clean-room research notes (docs/format-notes/*.md) not yet written for PyFLP, bravoh-daw refs. Required for DECISIONS.md license compliance audit before public release.

---

## End-of-Iteration Summary (2026-09-30)

**Iteration goal:** Complete Phase 0 skeleton and integrate Phase 1 readers to verify the architecture works.

**Status:** Phase 0 + Phase 1 + Phase 2 core complete. 278 tests passing (synthetic fixtures only).

**Completed:**
- 6 readers: format detection, Phase 1 readers (REAPER, Ableton, DAWproject), Phase 0 foundations
- Installed inventory scanner (Windows + macOS), KB v1 seed (41 vendors), identity resolver, report builder, GUI v1
- 3,500+ lines of engine code, 2,000+ lines of test code, 1,500+ lines of GUI code
- Full integration: CLI and GUI both use shared scan_candidate() function
- All SPEC-01/02/03 requirements for Phase 0-2 core addressed

**Known limitations:**
- Synthetic fixtures only; real DAW acceptance criteria blocked by unavailable real projects
- KB seed is unverified (41/~100 target vendors)
- 4 warning codes not implemented (EXTERNAL_HARDWARE, SIDECHAIN_PRESENT, THIRD_PARTY_CONTENT, DAW_VERSION_NEWER)
- HTML export deferred to v1.1 (low user impact)
- No backup-scan offer, KB auto-update, privacy opt-ins (v1.1 features)
- GUI not tested in real window (visual rendering not verified)

**Shipped for beta:**
- CLI: `rackcheck scan <path> [--json]` works end-to-end on REAPER, Ableton, DAWproject projects
- GUI: pywebview bridge ready; requires Windows native window test before beta handoff
- Installers: not yet built (signing certs not procured)

**Next iteration (Phase 2 Release):**
1. Real-window GUI verification (human tester, 1-2 hours)
2. Crafted fixtures in REAPER/Ableton/Bitwig (3-4 hours, licenses needed)
3. KB expansion to ~100 vendors + verification (8-12 hours, human research)
4. Implement 4 missing warnings (2-3 hours)
5. Build + sign installers (6-8 hours, certs + CI setup)
6. v1.0.0 release and beta launch

**Risks/Dependencies:**
- Fixture creation blocked by DAW licenses (defer to beta if partner provides projects)
- Signing certs blocked by procurement (budget needs approval)
- macOS builds blocked by test machine (can use CI runners as workaround)

---

**Last updated:** 2026-10-06 11:45 UTC  
**Contributors:** Sheldon Davidson (automation, Phase 0-2 core); phase 1 agents (REAPER/Ableton/DAWproject readers)

