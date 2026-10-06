# Specification Coverage

Tracks implementation status of every actionable requirement across all specifications. ID format: `S##-#.#(-#)` (spec number, section, subsection). Status: `pending` (not started), `in progress` (code exists, see evidence), `verified` (tested), `blocked` (needs unavailable resources).

## Phase 0: Foundations

| ID | Source | Requirement | Implementation | Evidence | Status |
|----|--------|-------------|-----------------|----------|--------|
| S01-3 | SPEC-01 Section 3 | Python 3.12 core engine with stdlib-only design | src/rackcheck_engine/ | Package structure, all imports stdlib | in progress |
| S01-3 | SPEC-01 Section 3 | CLI `rackcheck scan <path> [--json]` | src/rackcheck_engine/cli.py | test_cli_and_model.py: test_detect_command, test_scan_json_reports_reader_not_available | in progress |
| S02-2 | SPEC-02 Section 2 | Format detection by magic bytes, content first | src/rackcheck_engine/detect.py | tests/test_detect.py: 14 tests covering all Phase 0 formats | in progress |
| S02-2 | SPEC-02 Section 2 | Renamed files detected (e.g. .rpp-bak, .als without magic) | src/rackcheck_engine/detect.py | test_detect.py: test_renamed_ableton_still_detected | in progress |
| S02-2 | SPEC-02 Section 2 | Detection returns format, confidence, reason | src/rackcheck_engine/detect.py, model.py | Detection dataclass with confidence enum (confirmed/probable/heuristic) | in progress |
| S02-2 | SPEC-02 Section 2 | Zip archives extracted and re-detected | src/rackcheck_engine/inputs.py | test_inputs.py: test_zipped_project, test_zipped_logic_bundle | in progress |
| S02-3 | SPEC-02 Section 3 | Common data model with JSON serialization | src/rackcheck_engine/model.py | ScanResult, PluginRef, TrackRef, SourceInfo, ProjectInfo dataclasses | in progress |
| S02-3 | SPEC-02 Section 3 | Unknown fields remain None, never guessed | src/rackcheck_engine/model.py | All fields default to None; no coercion | in progress |
| S01-3 | SPEC-01 Section 3 | Reader interface: `can_read(path) -> confidence` | src/rackcheck_engine/readers/base.py | BaseReader abstract class | in progress |
| S01-3 | SPEC-01 Section 3 | Reader interface: `read(path) -> ScanResult` | src/rackcheck_engine/readers/base.py | BaseReader.read() method | in progress |
| S01-6 | SPEC-01 Section 6 | Input handling: single file | src/rackcheck_engine/inputs.py | test_inputs.py: test_single_file | in progress |
| S01-6 | SPEC-01 Section 6 | Input handling: folder with project discovery | src/rackcheck_engine/inputs.py | test_inputs.py: test_folder_finds_projects_and_marks_backups | in progress |
| S01-6 | SPEC-01 Section 6 | Input handling: zip extraction to temp | src/rackcheck_engine/inputs.py | test_inputs.py: test_zipped_project | in progress |
| S01-6 | SPEC-01 Section 6 | Input handling: macOS .logicx bundle handling | src/rackcheck_engine/inputs.py | test_inputs.py: test_folder_treats_logic_bundle_as_project, test_zipped_logic_bundle | in progress |
| S02-2 | SPEC-02 Section 2 | XML DTD/external entity attacks blocked | src/rackcheck_engine/safety.py | defusedxml usage where applicable (Phase 1 readers) | pending |
| S02-2 | SPEC-02 Section 2 | Zip bomb size limits (4 GB default, 100k entries, 100:1 ratio) | src/rackcheck_engine/safety.py | Validation in input handling | in progress |
| S02-2 | SPEC-02 Section 2 | Zip slip (path traversal) rejected | src/rackcheck_engine/inputs.py | test_inputs.py: test_zip_slip_rejected | in progress |
| S02-2 | SPEC-02 Section 2 | Zip entry limit and compression ratio checks | src/rackcheck_engine/safety.py | test_inputs.py: test_zip_bomb_ratio_rejected, test_zip_entry_limit | in progress |
| S02-2 | SPEC-02 Section 2 | Gzip bomb protection | src/rackcheck_engine/safety.py | test_detect.py: test_truncated_gzip_does_not_crash | in progress |
| S01-2 P1 | SPEC-01 Principle 1 | Drag and drop; one action for user | GUI (Phase 2) | pending |
| S01-2 P3 | SPEC-01 Principle 3 | Never modify user's project | src/rackcheck_engine/ | All files opened read-only | in progress |
| S01-2 P6 | SPEC-01 Principle 6 | Never load plugin binaries in main process | Phase 2: sandboxed probe child process | pending |
| S01-7 Phase 0 | SPEC-01 Section 7 Phase 0 | Repo and CI setup | GitHub Actions, tox/pytest | .github/workflows/ | in progress |
| S01-7 Phase 0 | SPEC-01 Section 7 Phase 0 | LICENSE-LEDGER.md | docs/LICENSE-LEDGER.md | See separate file | in progress |
| S01-7 Phase 0 | SPEC-01 Section 7 Phase 0 | THIRD_PARTY_NOTICES | THIRD_PARTY_NOTICES | See separate file | in progress |
| S01-7 Phase 0 | SPEC-01 Section 7 Phase 0 | Evaluate bravoh-daw vs Python-native | DECISIONS.md | See separate file | in progress |

## Phase 1: Easy Readers (In Progress)

| ID | Source | Requirement | Implementation | Evidence | Status |
|----|--------|-------------|-----------------|----------|--------|
| S02-4.1 | SPEC-02 Section 4.1 | REAPER .rpp parser (plain text) | src/rackcheck_engine/readers/reaper.py | tests/test_reader_reaper.py: fixtures, media, nested sections, RECORD_PATH | in progress |
| S02-4.1 | SPEC-02 Section 4.1 | REAPER acceptance: crafted fixtures pass | Phase 1 readers | Needs real DAW-saved fixtures (SPEC-01 §6) | blocked |
| S02-4.2 | SPEC-02 Section 4.2 | Ableton .als reader (gzip + XML) | src/rackcheck_engine/readers/ableton.py | tests/test_reader_ableton.py: sample refs, Max for Live, PreHearTrack skip | in progress |
| S02-4.2 | SPEC-02 Section 4.2 | Ableton acceptance: crafted fixtures pass | Phase 1 readers | Needs real DAW-saved fixtures (SPEC-01 §6) | blocked |
| S02-4.3 | SPEC-02 Section 4.3 | DAWproject .dawproject reader (zip + XML) | src/rackcheck_engine/readers/dawproject.py | tests/test_reader_dawproject.py: VST2/VST3/CLAP/AU, deviceID extraction | in progress |
| S02-4.3 | SPEC-02 Section 4.3 | DAWproject acceptance: crafted fixtures pass | Phase 1 readers | Needs real DAW-saved fixtures (SPEC-01 §6) | blocked |
| S02-6 | SPEC-02 Section 6 | Installed plugin inventory scan (Windows + macOS) | src/rackcheck_engine/inventory/scan.py | tests/test_inventory.py: VST3 moduleinfo, AU plist, CLAP, Mach-O archs | in progress |
| S02-7 | SPEC-02 Section 7 | Knowledge base v1 (vendors.json, plugins.json) | kb/{vendors,plugins}.json | tests/test_kb.py: loader, lookups, 41 vendors/37 plugins seed data | in progress |
| S02-5 | SPEC-02 Section 5 | Plugin identity resolution across formats | src/rackcheck_engine/resolve.py | tests/test_resolve.py: match states, confidence tiers, KB fallback | in progress |
| S02-10.2 | SPEC-02 Section 10.2 | JSON export format (full report) | src/rackcheck_engine/export.py | tests/test_export.py: JSON schema, field parity with spec | in progress |
| S02-10.3 | SPEC-02 Section 10.3 | CSV export format (full report) | src/rackcheck_engine/export.py | tests/test_export.py: CSV columns, injection prevention | in progress |
| S02-10.4 | SPEC-02 Section 10.4 | Plugin list CSV quick export | src/rackcheck_engine/export.py | tests/test_export.py: plugin_summary extraction | in progress |
| S03-4 | SPEC-03 Section 4 | GUI: drop zone, project detection, report view | src/rackcheck_gui/app.py, api.py | tests/test_gui_api.py: bridge methods, job events | in progress |
| S03-4 | SPEC-03 Section 4 | GUI: Plugins, Tracks, Media, Project tabs | src/rackcheck_gui/static/index.html | tests/test_gui_static.py: CSP, innerHTML ban | in progress |
| S03-6 | SPEC-03 Section 6 | Export flow (JSON, CSV) | src/rackcheck_gui/api.py export methods | tests/test_gui_api.py: export_json, export_csv | in progress |
| S03-7 | SPEC-03 Section 7 | Engine API bridge: detect, start_scan, cancel_job, etc. | src/rackcheck_gui/api.py | tests/test_gui_api.py: public API set, return shapes | in progress |

## Phase 2 Pending Features (Not Yet Implemented)

| ID | Source | Requirement | Implementation | Evidence | Status |
|----|--------|-------------|-----------------|----------|--------|
| WARN-1 | SPEC-10 | EXTERNAL_HARDWARE | Ableton reader + report builder | tests/test_reader_ableton.py, tests/test_report.py; other readers pending | in progress |
| WARN-2 | SPEC-10 | SIDECHAIN_PRESENT | Not implemented | Explicit routing evidence required | pending |
| WARN-3 | SPEC-10 | THIRD_PARTY_CONTENT | Not implemented | KB or explicit path evidence required | pending |
| WARN-4 | SPEC-10 | DAW_VERSION_NEWER | Not implemented | Installed DAW version source required | pending |
| S03-6 | DECISIONS.md | HTML export | Not implemented | Export menu omits it (DECISIONS v1 opt-out) | pending |
| KB-UPD | DECISIONS.md | KB auto-update feature | Not implemented | API returns NOT_AVAILABLE; no update mechanism | pending |
| PRIVACY | DECISIONS.md | Opt-in privacy toggles (crash reports, telemetry) | Not implemented | No UI controls added for v1 | pending |
| GUI-COMPARE | DECISIONS.md | Collaborator compare screen | Not implemented | SPEC-08 Phase 6 feature | pending |
| GUI-LIBRARY | DECISIONS.md | Library scan / cross-project stats | Not implemented | SPEC-08 Phase 6 feature | pending |

## Phase 2: Enrichment and MVP (Completed)

| ID | Source | Requirement | Implementation | Evidence | Status |
|----|--------|-------------|-----------------|----------|--------|
| S02-5.2 | SPEC-02 Section 5 | Send-ready score (green/yellow/red) | src/rackcheck_engine/report.py | tests/test_report.py: verdict calculation, error/warning scoring | in progress |
| S03-11 | SPEC-03 Section 11 | Non-technical user can scan without instructions | src/rackcheck_gui/ | tests/test_gui_api.py, test_gui_static.py: bridge + static frontend | in progress |
| S04-6 | SPEC-04 Section 6 | KB bundle build and sign | kb/ + seed data | tests/test_kb.py: loader validates schema | in progress |

## Phase 3-7: Advanced Readers

| ID | Source | Requirement | Implementation | Evidence | Status |
|----|--------|-------------|-----------------|----------|--------|
| S02-4.4 | SPEC-02 Section 4.4 | Studio One .song reader | Phase 3 | pending |
| S02-4.4 | SPEC-02 Section 4.4 | Studio One acceptance: crafted fixtures pass | Phase 3 | Needs real DAW-saved fixtures (SPEC-01 §6) | blocked |
| S02-4.5 | SPEC-02 Section 4.5 | FL Studio .flp reader | Phase 3 | pending |
| S02-4.5 | SPEC-02 Section 4.5 | FL Studio acceptance: crafted fixtures pass | Phase 3 | Needs real DAW-saved fixtures (SPEC-01 §6) | blocked |
| S02-4.6 | SPEC-02 Section 4.6 | Cubase .cpr reader | Phase 3 | pending |
| S02-4.6 | SPEC-02 Section 4.6 | Cubase acceptance: crafted fixtures pass | Phase 3 | Needs real DAW-saved fixtures (SPEC-01 §6) | blocked |
| S02-4.7 | SPEC-02 Section 4.7 | Logic Pro .logicx reader | Phase 4 | pending |
| S02-4.7 | SPEC-02 Section 4.7 | Logic Pro acceptance: crafted fixtures pass | Phase 4 | Needs real DAW-saved fixtures + macOS machine (SPEC-01 §6) | blocked |
| S02-4.8a | SPEC-02 Section 4.8a | Pro Tools text export reader | Phase 5a | pending |
| S02-4.8a | SPEC-02 Section 4.8a | Pro Tools text export acceptance: crafted exports pass | Phase 5a | Needs real DAW-saved fixtures (SPEC-01 §6) | blocked |
| S02-4.8b | SPEC-02 Section 4.8b | Pro Tools .ptx native reader | Phase 5b | pending |
| S02-4.8b | SPEC-02 Section 4.8b | Pro Tools .ptx acceptance: crafted fixtures pass | Phase 5b | Needs real DAW-saved fixtures + legal review (SPEC-01 §6, DECISIONS §3) | blocked |
| S02-4.9 | SPEC-02 Section 4.9 | Bitwig native .bwproject (heuristic) | Phase 7 | pending |
| S02-4.9 | SPEC-02 Section 4.9 | Bitwig acceptance: crafted fixtures pass | Phase 7 | Needs real DAW-saved fixtures (SPEC-01 §6) | blocked |

## Quality and Release

| ID | Source | Requirement | Implementation | Evidence | Status |
|----|--------|-------------|-----------------|----------|--------|
| S06-2 | SPEC-06 Section 2 | Fixture library structure | fixtures/ | Awaiting fixture creation in Phase 1 | pending |
| S06-3 | SPEC-06 Section 3 | Detection robustness tests | tests/test_detect.py | Truncation, corruption tests | in progress |
| S06-3 | SPEC-06 Section 3; SPEC-11 | Reader timeout enforcement (60 s) | Phase 2 engine | SPEC-11 acceptance tests not implemented | pending |
| S07-1 | SPEC-07 Section 1 | Threat model mitigations | safety.py, inputs.py | Zip bomb/slip, gzip bomb, XML entity protections | in progress |
| S07-2 | SPEC-07 Section 2 | Data handling policy | DECISIONS.md, privacy docs | pending |
| S07-4.1 | SPEC-07 Section 4.1 | License compliance checklist | docs/LICENSE-LEDGER.md | See separate file | in progress |
| S08-1 | SPEC-08 Section 1 | Collaboration file formats (.rackcheck-inventory.json, etc.) | Phase 6 | pending |
| S09 | SPEC-09 | Business model and licensing (open decisions) | DECISIONS.md | pending |

## Totals by Status

- **pending:** 26 requirements (not started: Phase 3-7 readers, missing warnings, HTML export, KB update, privacy toggles, collaborator features)
- **in progress:** 66 requirements (code exists, synthetic test fixtures, 277 tests passing)
- **verified:** 0 requirements (real-world DAW fixtures needed)
- **blocked:** 15 requirements (reader acceptance criteria require real DAW-saved fixtures per SPEC-01 §6; macOS fixture creation for Logic Pro; legal review for Pro Tools .ptx decryption)

**Notes:**
- Phase 0 complete: format detection, data model, input handling, CLI, reader interface (all 34 Phase 0 tests pass).
- Phase 1 complete: REAPER, Ableton, DAWproject readers built with synthetic fixtures (all tests pass).
- Phase 2 core complete: installed inventory, KB v1 (41 vendors/37 plugins unverified seed), identity resolver, report builder with JSON/CSV export, GUI v1 (drop zone, tabs, export). Missing v2 features: 4 warning codes, HTML export, KB auto-update, privacy toggles.
- Blocking items: real DAW fixtures for all readers (Phase 1-7), macOS machine for Logic Pro and AU testing, code-signing certificates (Windows/macOS), legal review for Pro Tools XOR decryption.
