# Key Decisions and Resolutions

Record of architectural and process decisions made during development. Decisions are recorded when made to establish precedent and make trade-offs explicit.

## Build Stack: Python-Native Core (Phase 0)

**Decision:** Use Python 3.12 with stdlib-only core engine, not bravoh-daw (Rust unified parser).

**Rationale:**
- Existing Python reference projects (PyFLP, rpp, dawproject-py, logicx-analyzer, CubaseTools) provide well-tested format knowledge.
- Stdlib-only design (no binary compile step) makes packaging simpler: PyInstaller bundles work on Windows and macOS without a Rust toolchain or pre-built binaries.
- Matches the single-developer shipping model better than a Rust rewrite.
- Easier to debug format issues when the core reads DAW files at a high level.

**Alternative evaluated:** bravoh-daw (MIT, Rust, unified schema for Ableton/FL/Logic/REAPER).
- **Not evaluated against real fixtures** because no real DAW project fixtures were available at Phase 0 (fixtures are normally collected by visiting studios or from donated projects in the beta program).
- Decision to test only against synthetic test data means we could not verify accuracy on real files; this is a known limitation.
- Rust/Tauri would require developers to know Rust and maintain a C++ bridge to the GUI; the Python stack keeps tooling lightweight.
- Revisit if Python readers prove too slow on large projects (Phase 2 performance testing) or if a critical Rust format reader emerges.

**GUI Stack:** pywebview (Python-to-native-window bridge) + HTML/CSS/TypeScript front-end. Chosen because:
- Keeps the core and GUI in one Python repo with a clean bridge (no separate IPC server).
- JavaScript bundle is small and bundled offline; web stack is familiar.
- Alternative (Tauri) makes sense only if the core switches to Rust.

**CLI:** `rackcheck scan <path> [--json]`. Implemented in Phase 0; both CLI and GUI call the same engine methods.

**Schema:** Common data model (SPEC-02 Section 3) in Python dataclasses, JSON-serializable. No ORM; straight dict serialization with custom types.

## File Format Detection (SPEC-02 Section 2)

**Decision:** Magic byte + content checks; extension is only a hint (SPEC-01 P2).

**Rationale:** Handles renamed files (.rpp-bak, .als backups, autosaves, misnamed zips), which is common in production workflows.

**Implementation:** detect.py checks formats in the order defined in SPEC-02 Section 2 table; first confident match wins. Returns (format, confidence, reason) so failures are explainable.

**Safety mitigations in place:**
- Zip bombs: size limit (4 GB default), entry count (100k), compression ratio (100:1).
- Zip slip (path traversal): reject entries with `..`, absolute paths, drive letters, symlinks.
- Gzip bombs: same size limits while decompressing.
- XML attacks: defusedxml to disable DTDs and external entities (Phase 1 readers for .als, .song, .dawproject).
- Never follows symlinks when scanning project folders.

## Readers: Modular Architecture

**Decision:** One reader module per DAW format. Readers implement BaseReader interface (can_read, read).

**Rationale:**
- Decouples format-specific parsing from the common engine.
- Readers are optional; app gracefully degrades if a reader isn't available.
- Easy to unit-test each reader in isolation.
- Phase 1 readers (REAPER, Ableton, DAWproject) written by separate agents; integration happens later.

**Reader test fixtures:**
- Crafted fixtures (minimal projects with one change each) created in each supported DAW.
- Free, cross-format plugins (Surge XT, Vital, TDR Nova) used so fixtures work in every DAW.
- Real-world fixtures collected from beta users with consent; never committed to public repos.

## License Compliance: Clean-Room Process

**Decision:** For GPL/AGPL references (Class C in SPEC-01 Section 4), use a clean-room process:
1. Read the GPL source, write plain-English format notes (no code).
2. Close the GPL source; write our implementation from notes only.
3. Keep notes in docs/format-notes/<format>.md as proof of process.

**Rationale:**
- Reverse engineering for interoperability is generally legal in Canada and the US.
- Clean-room process creates an auditable trail for a lawyer review before paid release.
- This applies to: FL Studio (PyFLP GPL history), Cubase (no public format spec), Pro Tools XOR decryption (ptformat LGPL).

**License ledger:** docs/LICENSE-LEDGER.md lists every reference project with class (A/B/C), license, and notes. Regenerated before each release.

## Third-Party Code: None Yet

**Current state:** All Phase 0 code is original. External libraries used only from stdlib (zipfile, gzip, dataclasses, pathlib, enum, json).

**THIRD_PARTY_NOTICES:** States "No third-party code is bundled yet." Updated as dependencies are added.

**Phase 1 readers:** May use MIT-licensed libraries (e.g. dawproject-py for DAWproject, elements of PyFLP if MIT confirmed). Each will be added to the license ledger before merge.

## Open Decisions for Phase 2+

See SPEC-09 for business model options that still need deciding:
- [ ] Free + Pro split (recommendation: free core, Pro for collaboration).
- [ ] Business structure (sole proprietor or incorporate).
- [ ] Payment provider and licensing service.
- [ ] Activation limits and offline activation support.
- [ ] Refund policy.

These do not block Phase 1 readers but affect the engine's entitlements module architecture (SPEC-09 Section 5).

## Known Limitations and Workarounds

1. **No real DAW fixtures yet:** Tests use synthetic projects created programmatically. Bravoh-daw was not benchmarked against real projects because none were available. Real fixtures will be created during Phase 1 in partnership with beta testers.

2. **macOS testing:** Logic Pro and GarageBand readers (Phase 4) need a Mac. Signing and notarization (Phase 2) also need macOS hardware or hosted runners. Currently this is planned to run in CI; local testing requires a Mac.

3. **Pro Tools legal review pending:** The .ptx native reader (Phase 5b) requires decryption (XOR, published in ptformat's LGPL code). Clean-room notes will be written during Phase 5a, then reviewed by a lawyer before shipping 5b.

4. **DAW license availability:** Building fixtures for all supported DAWs requires licenses for each. Some vendors offer developer/NFR licenses; others don't. This is built into the Phase 2 budget (SPEC-09 Section 10).

5. **Code signing certificates:** Signed installers and notarized macOS builds (Phase 2) require:
   - Apple Developer Program membership (yearly fee) for macOS.
   - Azure Artifact Signing or an OV code signing certificate (monthly or one-time) for Windows.
   - Both need to be set up in CI before the first release.

## Precedence

1. All SPEC-*.md files are authoritative.
2. SPEC-01 section 4 (license policy) and section 7 (build phases) define the work order.
3. PROMPT.md (autonomous build instructions) governs the iteration process.
4. Contradictions between specs are resolved by flag as bugs in this file; no requirement is silently narrowed.

---

**Last updated:** 2026-09-29  
**Next review:** Before Phase 2 release (when Phase 1 readers integrate)

## Phase 2 Report, Resolver, Links and Exports (2026-09-29)

Where SPEC-01/02 were ambiguous the simplest defensible option was chosen:

- **Resolution states:** `installed_same_format`, `installed_other_format`, `not_installed`, `stock`, `unknown` (no name and no identity keys), plus `inventory_unavailable` (added: no inventory supplied, so install status is never claimed; no PLUGIN_MISSING is raised). REAPER `js` plugins count as `stock`. Match confidence is capped by the reader's confidence for the reference.
- **Match tiers:** exact identity key (confirmed) > file hint equal to installed file name (probable) > KB alias keys (confidence of the KB match) > normalized name + vendor, vendors compared via KB vendor ids/aliases (probable) > name only, only if the vendor is unknown on one side and the name is unambiguous (heuristic). Same name with a different vendor is never a match. Numbers in product names ("Pro-Q 4") are kept during normalization; only dotted/`vN` version suffixes are stripped.
- **Unverified KB data makes no claims:** KB-derived warnings/flags (VST2-only, Mac/Win-only, discontinued, iLok) and `apple_silicon_native` are only emitted for records with `verified: true`. The bundled seed KB is entirely unverified, so it currently yields links/categories but no such warnings. Intel-only is inferred from the installed Mach-O architectures (POSIX paths only); 32-bit from an `i386`-only binary.
- **PLUGIN_UNKNOWN** = no KB record and no installed match. It can co-occur with PLUGIN_MISSING.
- **Aggregation:** plugin warnings are emitted once per unique plugin (all instance ids in `related_ids`); media warnings once per code with all media ids, so a 500-sample project does not produce 500 warnings.
- **Additive warning codes:** `INVENTORY_UNAVAILABLE` (info) and `READER_NOTE` (info, passes reader warnings through). Not implemented because the data is not readable yet: `EXTERNAL_HARDWARE`, `SIDECHAIN_PRESENT`, `THIRD_PARTY_CONTENT`, `DAW_VERSION_NEWER`.
- **Send-ready:** red if any error-severity warning, yellow if any warning-severity warning or the inventory was not checked, else green. `opens_on` is `false` only for known blockers (AU plugins or Logic projects block Windows; verified KB platform limits), otherwise `true`.
- **Counts:** `unique_plugins` and `plugin_instances` exclude stock devices; `stock_devices` counts them; `plugin_summary` includes stock entries. Instances are grouped across formats when the KB identifies them as the same plugin.
- **Unavailable data:** the common model does not carry track colour/mute/routing, preset names, markers, etc. They are `null`/empty and listed in `project.unavailable_fields` (prefixed `tracks.`/`plugins.`). Only the initial tempo and time signature are emitted (as one-entry lists); `tempo_changes_after_start` and `time_signature_changes_after_start` are listed as unavailable. `installed.arch` is the architectures joined with `/`.
- **JSON/CSV additions (parity rule in 10.3):** JSON adds `resolution.confidence`, `kb.matched_by/confidence/verified/provenance`, `identity.vst2_ascii` and `summary.most_used_plugin` (SPEC-02 9.8). Matching CSV columns are appended after each group: `summary_most_used_plugin`, `plugin_resolution_matched_by`, `plugin_resolution_confidence`, `plugin_kb_id`, `plugin_kb_matched_by`, `plugin_kb_confidence`, `plugin_kb_verified`. All spec columns remain in spec order.
- **CSV injection:** neither SPEC-02 nor SPEC-07 requires it; text cells beginning with `= + - @` TAB or CR get a leading apostrophe. Numbers (including negatives) and booleans are not altered.
- **Redaction** is applied at export time (`redact_report`), leaving the cached report intact, per SPEC-03 9: home folder becomes `~`, media inside the project folder become relative, media outside keep only the file name, installed plugin paths are dropped.
- **Folder facts:** total size/file count/backups/unused media are skipped (null) when the project sits directly in the home folder, Desktop/Documents/Downloads/Music or a drive root, or holds more than 200,000 files, because "unused files in the folder" would be meaningless. Media are SHA-256 hashed up to 512 MB each. Audio headers are read for WAV, FLAC and AIFF only; other formats show only the extension.
- **KVR search URL** (`https://www.kvraudio.com/plugins/search?q=`) is a best-effort pattern that has not been checked against the live site; the link source is marked `search`.
- **CLI:** `rackcheck scan` prints a text summary by default; `--json` prints `{"engine_version", "scans": [{"detection", "report" | "error"}]}` (the per-scan `result` key was replaced by the full `report`). A missing or unreadable `--inventory` file is an error (`INVENTORY_UNREADABLE`), never an empty inventory. Without `--inventory`/`--no-inventory` the machine is scanned. With several projects, `--csv`/`--plugin-list` paths get `_1`, `_2`... suffixes.
- **Inventory:** `InstalledPlugin.bundle_id` (CFBundleIdentifier) added and populated from `Info.plist` for the reverse-domain link step.

## GUI v1 (2026-09-29)

- **Package and shell:** `src/rackcheck_gui/` (`api.py` bridge, `storage.py`, `app.py` window glue, `static/`). pywebview is the optional extra `gui`; script `rackcheck-gui` (a gui-script) and `python -m rackcheck_gui`. The window serves `static/` through pywebview's built-in local HTTP server (`http_server=True`) so the page has a real `http://127.0.0.1` origin and a strict CSP (`default-src 'self'`, no inline script/style, no eval) can work. The front end is plain JS/CSS with no build step (SPEC-03 allows "plain" front ends; no framework was warranted for v1). All project text is inserted with `textContent`; a test bans `innerHTML`, `eval`, `fetch` and remote URLs.
- **Shared engine path:** `_scan_candidate` moved from `cli.py` to `rackcheck_engine/service.py` as `scan_candidate` (with an optional stage callback that can raise to cancel). The CLI imports it, so CLI and GUI build reports through one function. Bridge-only error codes were added to `errors.py`.
- **Bridge contract:** all SPEC-03 section 7 methods exist except the Phase 6 ones (`library_scan`, `export_inventory`, `import_inventory`). `update_kb` exists but returns `NOT_AVAILABLE` because the engine has no update/download mechanism; the UI has no update button. Extra public methods the screens need: `choose_files`, `choose_folder`, `choose_export_path`, `choose_bundle_path` (native dialogs; they are how paths get authorised), `clear_recent`, `get_plugin_folders`, `get_log_folder`. Everything else is `_`-prefixed so pywebview does not expose it; a test pins the public set.
- **Path authorisation (SPEC-07):** JS-supplied paths are only accepted if the user chose them: native dialog result, a window drop (the Python drop handler reads the real paths, JS never supplies them), a recent-report reopen (its source/input paths), or a folder saved in settings from an earlier session. `reveal_path` additionally accepts paths that appear in a report the user has open. `open_url` only allows http/https with a host.
- **Return shapes that extend SPEC-03:** `get_report` returns `{report_id, report, imported, stale, source_path, input_path, rel_path, plugin_keys}` (report plus GUI metadata; `plugin_keys` maps plugin id to the engine's grouping key so the UI groups instances exactly as `plugin_summary` does). `job.*` events carry an extra `kind` (`scan` or `inventory`); `job.done` carries `report_ids` and `errors` for multi-project scans. Start of a scan takes `options.projects` (relative paths from `detect().projects_found[].rel_path`) so a folder or zip with several projects can be scanned selectively; without it, several projects give `MULTIPLE_PROJECTS` with the list.
- **Progress stages:** the report builder runs resolve, inventory match, enrich, media and build as one step, so the bridge emits `detect`, `read` and `build` (indices from the fixed SPEC-03 list) and the UI shows three honest steps instead of the six-step list. Percent is `null` for single-project scans. Cancellation is cooperative at stage boundaries (a reader already running is not interrupted). No `job.partial` events yet.
- **Storage:** settings, recent-report index and cached inventory are JSON files in the app-data folder (SPEC-03 names SQLite for the inventory cache and index; JSON was chosen for v1 because nothing queries them; a migration is trivial later). Reports are cached unredacted and redacted only on export, as specified. Recent list capped at 50. Logs: daily rolling file, 7 days, kept in `logs/`; only exceptions and folder paths are logged, never project contents.
- **Inventory:** scanned per (format, folder) so progress and cancel work between folders and one failing folder is logged and skipped. The result is cached; scans use the cached inventory (`use_inventory` true) and, when none exists, the report says install status is unknown. When an inventory scan finishes while a non-imported report is open, the app re-runs that scan in place so the report shows install status (SPEC-03 "updates live"). Custom folders are scanned for every plugin format.
- **Settings not offered because the feature does not exist:** KB auto-update toggle, "report unknown plugins" and crash-report opt-ins, "Report it" footer in the plugin panel, HTML export (Export menu omits it; API returns `NOT_AVAILABLE`), "Share with collaborator", Compare and Library screens. No dummy controls were added.
- **Imported reports** (`.json` exports) are validated for required keys/types, capped at 64 MB, shown with a banner, and cannot be rescanned.
