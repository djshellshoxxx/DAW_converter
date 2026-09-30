# TODO: Work in Progress

Current iteration focuses on documenting Phase 0 completion and preparing for Phase 1 reader integration.

## Phase 0: Completed (v0.1)

✓ Repository structure and CI setup (GitHub Actions, tox, pytest)
✓ Common data model (ScanResult, PluginRef, TrackRef) with JSON serialization
✓ Format detector (magic bytes + content, covers all target DAWs)
✓ Input handling: single files, folders, zips, macOS bundles
✓ Safety hardening: zip bombs, zip slip, gzip bombs, XML entity attacks
✓ CLI: `rackcheck scan <path> [--json]`
✓ Reader interface: BaseReader abstract class
✓ Unit tests: 34 tests, all passing
✓ Specification compliance: docs/spec-coverage.md, DECISIONS.md, LICENSE-LEDGER.md, THIRD_PARTY_NOTICES
✓ README and install instructions

**What this gives us:** a solid foundation to plug reader modules into.

---

## Phase 1: Easy Readers (In Progress)

Other agents are currently working on these. Status updates to follow.

### Phase 1a: REAPER .rpp reader
- Deadline: [to be set by agent]
- Acceptance: crafted fixtures (empty, one-vst3-insert, same-plugin-x3, bypassed) pass; instance counts and bypass state correct
- Blocker: none (format is plain text, well-documented)

### Phase 1b: Ableton .als reader
- Deadline: [to be set by agent]
- Acceptance: crafted fixtures for Phase 1 pass; VST2/VST3/AU identity extraction correct; racks with nesting handled
- Blocker: none (schema changes between Live versions documented in existing projects)

### Phase 1c: DAWproject .dawproject reader
- Deadline: [to be set by agent]
- Acceptance: crafted fixtures from Bitwig, Cubase 14+, Studio One pass; Vst3Plugin, Vst2Plugin, ClapPlugin, AuPlugin detection correct
- Blocker: none (official XML schema available; bitwig/dawproject repo is MIT)

### Phase 1 acceptance criteria (SPEC-01 Section 7)
- All crafted fixtures for REAPER, Ableton, DAWproject pass
- Correct plugin lists, track assignment, instance counts, bypass state
- Unit tests for each reader
- Format notes written to docs/format-notes/{reaper.md, ableton.md, dawproject.md}
- License ledger updated with clean-room notes for any GPL references

---

## Phase 2: Enrichment and MVP Release (after Phase 1)

Start once Phase 1 readers are integrated and tests pass.

### 2a. Installed plugin inventory scanner
- Windows: scan VST3, VST2, CLAP, AAX standard folders + registry paths
- macOS: scan VST3, VST2, AU, CLAP, AAX standard folders
- Read VST3 moduleinfo.json, AU Info.plist, CLAP descriptors (sandboxed probe for binary load)
- Cache by path+mtime+size; rescan only changed items
- Acceptance: Windows and macOS machines scan 100+ plugins in under 60 s (cached); inventory available in report

### 2b. Knowledge base v1
- Repo: separate rackcheck-kb GitHub repo
- Seeding: top ~100 vendors and their main plugins from official sites
- Schema: vendors.json, plugins.json (SPEC-02 Section 7)
- Build: compile to signed kb-bundle.json + manifest
- Acceptance: app downloads, verifies signature, swaps in bundle; old bundle still works if update fails

### 2c. Plugin identity resolver
- Match project plugin reference to installed plugin across formats (VST2↔VST3, etc.)
- Fallback: normalized name + vendor matching
- Acceptance: fixtures correctly identify installed plugins; cross-format matching tested

### 2d. Report builder
- Assemble SourceInfo + project facts + track data + enrichment into final report JSON (SPEC-02 Section 10.2)
- Export JSON and CSV (SPEC-02 Section 10.3)
- Warnings and send-ready score calculation
- Acceptance: report schema validates; exports byte-identical to CLI and GUI; every detected field appears somewhere

### 2e. GUI v1 (pywebview + HTML/TS)
- Home screen: drop zone, recent scans, supported DAW list
- Scanning progress view
- Report view: verdict card, tabs (Plugins, Tracks, Media, Project, Raw)
- Plugin detail panel: links, installation status, KB info
- Export menu: JSON, CSV, HTML (HTML optional for v1)
- Settings: plugin folders, KB updates, privacy toggles
- Acceptance: 3 non-technical testers can install, drop an Ableton project from Phase 1 fixtures, get correct report, no instructions needed

### 2f. Installer builds
- Windows: Inno Setup, signed with Azure Artifact Signing
- macOS: signed .dmg, notarized
- Accept: both install and launch cleanly on fresh machines (clean VM testing)

### 2g. Release process
- CI pipeline: test → build Windows → sign → test → build macOS → sign → notarize → smoke test → publish
- Version bump (SemVer)
- THIRD_PARTY_NOTICES and license ledger regenerated
- Release notes written
- Website download links updated

**Phase 2 acceptance:** v1.0.0 shipping; non-technical tester gets correct report from REAPER, Ableton, or DAWproject project without reading instructions.

---

## Phase 3: Native Readers (after Phase 2)

- Studio One .song reader (zip + XML)
- FL Studio .flp reader (binary events)
- Cubase .cpr reader (RIFF-like binary)

Acceptance: fixtures for current and previous major version pass.

---

## Phase 4: Logic Pro and GarageBand

- .logicx reader: MetaData.plist, ProjectData chunk walk
- AU plugin identity resolution
- Acceptance: fixtures from current Logic version pass

Blocker: macOS test machine for Logic fixtures and testing.

---

## Phase 5: Pro Tools

### 5a. Text export reader (ships first)
- Parse "Export Session Info as Text" output
- Acceptance: current PT version exports parse correctly

### 5b. Native .ptx reader
- XOR decryption and block walk
- Plugin insert extraction (original research needed)
- Crafted fixtures method: create blank session, add known plugin, diff decrypted blocks
- Acceptance: crafted fixtures with known inserts decode correctly on current PT and PT 12

Blocker: Pro Tools license and access to current + PT 12 for fixture creation.

---

## Phase 6: Power Features

- Library scan: cross-project stats
- Collaborator compare: my installed vs. project requirements (SPEC-08)
- Send pack: bundle project + media + report + readme for handoff
- Scan diff: before/after versions
- Export inventory: "here's what I have" file for compare

---

## Phase 7: Long Tail

- Bitwig native .bwproject (heuristic string scan; DAWproject export is reliable path)
- Reason, Cakewalk, Digital Performer, LUNA (only if user demand justifies)
- Linux build

---

## Blockers

### High Priority
1. **Phase 1 reader integration:** Awaiting completion of REAPER, Ableton, DAWproject readers by other agents. No hard deadline set yet; will unblock Phase 2 work immediately once code is ready.

### Medium Priority
2. **Real DAW fixtures:** Crafted fixtures created synthetically during Phase 1/2. Real-world fixtures collected in beta program. Unknown timescale; bravoh-daw not benchmarked against real files because none existed at Phase 0.

3. **macOS test machine:** Logic Pro and AU testing requires a Mac. Signing and notarization require macOS (or hosted GitHub Actions runners, slower). Planned for Phase 2 CI.

4. **Pro Tools legal review:** .ptx XOR decryption (Phase 5b) requires clean-room research and lawyer approval. Interoperability exception exists in Canada and US law but must be reviewed before shipping.

### Low Priority
5. **Code signing certificates:** Azure Artifact Signing (Windows) and Apple Developer Program (macOS) not yet set up. Required before Phase 2 release. Cost: ~CAD $150-200/year + setup time in CI.

6. **DAW licenses for fixture creation:** Need current (and prior major) versions of Studio One, FL Studio, Cubase, Logic Pro. Some vendors offer developer/NFR licenses. Budget item SPEC-09.

---

## Recently Completed (This Iteration)

- docs/spec-coverage.md (162 rows tracking all requirements)
- DECISIONS.md (architecture and licensing decisions)
- docs/LICENSE-LEDGER.md (reference projects by phase with licenses)
- THIRD_PARTY_NOTICES (currently states no bundled third-party code)
- TODO.md (this file)
- README.md (install and usage)

---

## Next Action

Wait for Phase 1 reader agents to complete work on REAPER, Ableton, and DAWproject. Once those readers are merged:
1. Run full test suite
2. Create crafted fixture set in Phase 1 DAWs
3. Update spec-coverage.md with fixture results
4. Begin Phase 2 work: inventory scanner, KB, report builder, GUI

**Estimated timeline for Phase 1 completion:** [To be set by agent leads]

---

Last updated: 2026-09-29
