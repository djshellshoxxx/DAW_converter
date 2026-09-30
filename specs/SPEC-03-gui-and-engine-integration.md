# SPEC-03: GUI and Engine Integration

**Project:** Plugin Dependency Scanner (working name: "Rackcheck")
**Companion specs:** SPEC-01-build-order.md, SPEC-02-file-format-readers.md
**Status:** Draft v1, September 2026

Covers what the app looks like, how the user moves through it, and how the GUI talks to the scanning engine.

---

## 1. UX goals

1. **Drop and done.** A first-time user gets a useful report with zero setup and zero reading. Target: under 30 seconds from app launch to report for a typical project, excluding the one-time plugin inventory scan.
2. **Answer the real question first.** The top of every report answers "will this project open correctly, and if not, what do I need?" Details come after.
3. **Plain language.** "Not installed on this computer", not "resolution_state: missing". Technical detail lives in expandable panels and exports.
4. **Honest about certainty.** Heuristic results carry a visible marker with a tooltip explaining why.
5. **Never block.** Scans run in the background with progress; the UI stays responsive and scans can be cancelled.

---

## 2. Tech approach

- **Engine:** Python package `rackcheck_engine` (SPEC-01 section 3). No GUI code in it.
- **Shell:** pywebview native window hosting a local HTML/CSS/JS front end (bundled, no remote assets, works offline).
- **Bridge:** pywebview `js_api` object exposing engine methods to JavaScript, plus an event channel from Python to JS for progress (section 8).
- **Front end:** plain TypeScript + a small component library, or Svelte/Preact. Keep bundle small. No React required.
- **Platforms:** Windows 10/11 and macOS 13+ in Phase 2. Linux later.

If Phase 0 picks the Rust core instead (bravoh-daw), swap pywebview for Tauri; the screens and contracts in this spec stay the same.

---

## 3. Screen map

```
First run -> Home (drop zone)
                |
                v
            Scanning (progress)
                |
                v
            Report ---------> Plugin detail (side panel)
              | |  \--------> Track detail (side panel)
              | \----------> Export dialog
              v
           Compare (Phase 6)

Sidebar (always visible): Home | Recent | Installed Plugins | Library (Phase 6) | Settings
```

---

## 4. Screens

### 4.1 First run

One screen, not a wizard.

- Title: "Let's see what plugins you have."
- Short line: "We'll scan your plugin folders once so we can tell you what's installed. Nothing leaves your computer."
- Detected plugin folders listed with checkboxes (defaults from SPEC-02 section 6), "Add folder" button.
- Primary button: **Scan my plugins**. Secondary: **Skip for now** (reports will show "installed status unknown" until done).
- The inventory scan continues in the background. The user can drop a project immediately; the report fills in installed status when the inventory finishes.

### 4.2 Home

- Large drop zone filling most of the window: "Drop a project file, folder, or zip here" with a **Browse** button.
- Under it, a one-line list of supported DAW names (text only, no vendor logos; see SPEC-07 section 4.3). Hovering "Pro Tools" shows a note if only the text export is supported in this release, with a "How to export" link.
- Recent scans list (last 10): project name, DAW icon, date, send-ready dot (green/yellow/red). Click to reopen the saved report instantly (from cache, section 9).
- Also accepts a previously exported `.json` report (SPEC-02 10.2) to view it.
- Drop anywhere in the window works, not just the drop zone.

**Multiple items dropped:** if more than one project is found (multiple files, or a folder with several projects), show a small picker: list of detected projects with checkboxes, "Scan selected". In Phase 6 this offers "Scan all as a library".

### 4.3 Scanning

Shown inline in the main area (not a modal), so the sidebar stays usable.

- Project name and detected DAW ("Ableton Live 12 project").
- Stage progress: Detecting > Reading project > Identifying plugins > Checking your system > Looking up plugin info > Building report. Current stage highlighted, with a progress bar where the stage can report percentage.
- **Cancel** button.
- Typical scans finish fast enough that this flashes by; that's fine.

### 4.4 Report

The main screen. Layout top to bottom:

**A. Header bar**
- Project name, DAW + version, file path (click to reveal in Finder/Explorer), scan time.
- Buttons: **Export** (section 6), **Rescan**, **Share with collaborator** (Phase 6), overflow menu (Open project folder, Copy summary as text).

**B. Verdict card**
- Big send-ready indicator (green / yellow / red) with one sentence: "Opens fine on this computer." / "2 plugins are missing." / "This project needs a Mac."
- "Opens on: Windows ✓ Mac ✓" badges.
- Key counts as small tiles: Plugins (unique / instances), Missing, Tracks, Media files, Missing media.

**C. Warnings list**
- Grouped by severity (errors first). Each warning is one plain sentence (SPEC-02 10.5) with a count and a "Show" link that filters the relevant tab.
- Collapsed to the top 5 with "Show all" if long.

**D. Tabs**

| Tab | Contents |
|---|---|
| **Plugins** (default) | One row per unique plugin: status icon, name, vendor, format badge, instances, tracks (truncated), licensing badge, homepage button. Toggle to "per instance" view (one row per instance with track and slot) |
| **Tracks** | Tree view following track hierarchy: name, type icon, color swatch, mute/solo/frozen badges, plugin chain as small chips in slot order, sends and sidechain indicators |
| **Media** | Referenced files: name, status (ok / missing / outside folder), format, sample rate (mismatch highlighted), duration, size, source hint. Sub-section "Unused files in project folder" with total size |
| **Project** | All project-level facts from SPEC-02 9.2 and 9.6 in a two-column list: tempo and tempo changes, time signatures, key, sample rate, length, markers list, loop, metadata, folder size, backups. Fields that this DAW format can't provide show "Not stored in this format" in grey (from `unavailable_fields`) |
| **Special** | Max for Live devices, sampler samples, external hardware, content libraries. Hidden if empty |
| **Raw** | Pretty-printed JSON of the full report with a copy button. For power users and bug reports |

**Plugins tab details:**
- Status icons: ✓ installed, ⇄ installed in another format, ✕ missing, ◆ stock (needs DAW), ? unknown, and a small "H" marker for heuristic results.
- Filters (chips above table): All, Missing, Instruments, Effects, iLok, Free, Stock, Heuristic.
- Search box (filters name/vendor).
- Sort by any column. Default sort: missing first, then by instance count.
- Group by: none / vendor / track / format.
- Row click opens the plugin detail panel.
- Homepage button opens the link in the default browser. A small icon shows the link source (official KB link vs vendor-declared vs search fallback); search fallback reads "Search for it".

**Every detected field must be visible somewhere in the report** (SPEC-01 section 8). The rule for placement: summary facts in the verdict card and tabs, everything else in detail panels or the Project tab, and the complete set in the Raw tab.

### 4.5 Plugin detail panel (slides in from the right)

- Name, vendor, category, format badges, status in plain language ("Installed (VST3, version 1.368)").
- Links: Homepage, Manual, Support (only those that exist), each with its source.
- "Used in this project": list of tracks and slots, bypassed instances marked, whether any parameters are automated, preset name if known.
- Your system: installed version, path, architecture, other formats installed. Warning if older than the project's saved version.
- About this plugin (KB): licensing system, price model, platforms, available formats, Apple Silicon, status, free alternatives (each clickable), "Info last verified <date>".
- Identity (collapsed "Technical details"): CID / unique ID / AU codes / CLAP id, file hint, confidence and reason.
- Footer: "Is something wrong here? Report it" (opt-in, sends only plugin identity fields; preview what will be sent before sending).

### 4.6 Track detail panel

- Name, type, color, parent group, mute/solo/arm/frozen.
- Plugin chain in order (click a plugin to jump to its detail).
- Routing: output, sends with levels, sidechain sources.
- Clips count, MIDI note stats, automated parameters, media files used.

### 4.7 Installed Plugins screen

- Table of everything found on this machine: name, vendor, format, version, architecture, path, homepage.
- Filters: format, vendor, architecture (flag Intel-only on Apple Silicon), duplicates (same plugin in several formats).
- **Rescan** button and last-scanned time. Settings link to manage folders.
- **Export my plugin list** (Phase 6 collaborator file, section 4.9).

### 4.8 Library screen (Phase 6)

- Choose a folder; scans every project in it (with progress, cancellable, resumable).
- Table of projects: name, DAW, date, send-ready dot, missing count.
- Cross-project view: most used plugins, plugins used in only one project, "if you uninstall X, these projects break".
- Export combined CSV (SPEC-02 10.4).

### 4.9 Compare / collaborator (Phase 6)

- Import a collaborator's plugin list file (`.rackcheck-inventory.json`).
- Report re-renders with an extra status column: "On Alex's machine: ✓ / ✕".
- Verdict card switches to "Will this open for Alex?".

### 4.10 Settings

- Plugin folders (add/remove, rescan).
- Knowledge base: current version, "Check for updates automatically" toggle (default on, can be turned off), manual update button.
- Export defaults: redact paths on/off, default export folder, CSV delimiter (comma / semicolon for European Excel locales).
- Privacy: opt-in toggles for "report unknown plugins" and crash reports, both off by default, with plain-language descriptions.
- Appearance: system / light / dark.
- Diagnostics: "Open log folder", "Create support bundle" (logs + app/KB versions, no project files).

---

## 5. Error and edge states

| Situation | What the user sees |
|---|---|
| Unsupported file | "We can't read this file type yet." Shows what it looks like (if detected) and a helpful path, e.g. for Bitwig: "Export as DAWproject (File > Export DAWproject) and drop that file instead." |
| Pro Tools .ptx before 5b | "Pro Tools sessions need one extra step for now." with a 3-step card for Export Session Info as Text, then "Drop the text file here" |
| Corrupt / truncated project | "This project file looks damaged or incomplete." Offer to scan the newest backup if one is found nearby (Ableton Backup folder, .rpp-bak, FL autosave) |
| Newer format than the reader knows | Partial report with a banner: "This was saved with a newer version of <DAW> than we fully support. Some details may be missing." Results from fallback scanning marked heuristic |
| Zip contains no project | "No project files found in this zip." |
| Inventory not scanned yet | Status column shows "Unknown" with a banner "Scan your plugins to see what's installed" and a button |
| Inventory scan crashes on a plugin | Plugin listed as "Couldn't read" in Installed Plugins; scan continues (sandbox, SPEC-02 section 6) |
| Offline | Everything works; KB update check silently skipped |
| Very large project | Progress shows per-stage counts; UI stays responsive |

Error text always says what happened and what to do next. Never show a stack trace in the main UI; details go in the log and the Raw tab.

---

## 6. Export flow

- **Export** button opens a small menu:
  - Full report (JSON)
  - Full report (CSV)
  - Plugin list (CSV)
  - Missing plugins only (CSV)
  - HTML report (when available)
- Options row under the menu: "Redact file paths" checkbox (remembers last choice).
- Standard OS save dialog with the default filename from SPEC-02 10.1.
- After saving: toast "Saved to <folder>" with **Show in folder**.
- Formats must match SPEC-02 section 10 exactly; the GUI never builds its own export. It calls the engine (section 7) so CLI and GUI exports are identical.

---

## 7. Engine API (the bridge contract)

The GUI only talks to the engine through these methods. The same functions back the CLI. All inputs and outputs are JSON-serializable. Long operations return a job ID immediately and report progress through events (section 8).

| Method | Input | Returns | Notes |
|---|---|---|---|
| `get_app_info()` | - | `{app_version, engine_version, kb_version, schema_version, supported_formats[]}` | `supported_formats` drives the Home screen list |
| `detect(paths[])` | file/folder/zip paths | `[{path, format, confidence, reason, projects_found[]}]` | Fast, synchronous. Used right after a drop to build the picker if needed |
| `start_scan(path, options)` | path + `{use_inventory: bool}` | `{job_id}` | Async |
| `cancel_job(job_id)` | - | `{ok}` | |
| `get_report(job_id or report_id)` | - | Full report JSON (SPEC-02 10.2) | |
| `export_report(report_id, format, dest_path, options)` | format: `json`, `csv_full`, `csv_plugins`, `csv_missing`, `html`; options: `{redact_paths, csv_delimiter}` | `{path}` | |
| `open_report_file(path)` | exported .json | `{report_id}` | For viewing shared reports |
| `list_recent()` | - | `[{report_id, project_name, daw, scanned_at, send_ready}]` | |
| `start_inventory_scan(folders[] or null)` | null = defaults + saved | `{job_id}` | Async |
| `get_inventory()` | - | `{scanned_at, plugins[]}` | |
| `get_settings()` / `set_settings(patch)` | - / partial settings | settings JSON | |
| `update_kb()` | - | `{job_id}` | Async, optional network |
| `open_url(url)` | url | `{ok}` | Engine validates scheme (http/https only) before opening |
| `reveal_path(path)` | path | `{ok}` | Show in Finder/Explorer |
| `library_scan(folder)` | folder | `{job_id}` | Phase 6 |
| `export_inventory(dest_path)` / `import_inventory(path)` | | | Phase 6 |
| `create_support_bundle(dest_path)` | | `{path}` | |

**Error format** (every method): `{"error": {"code": "UNSUPPORTED_FORMAT", "message": "plain text", "details": {...}}}`. Codes are stable and mapped to the user messages in section 5.

---

## 8. Jobs, progress and threading

- Every async job runs on a worker thread (or process for inventory probing). The pywebview UI thread is never blocked.
- One project scan at a time by default; library scans run projects sequentially with a small worker pool for filesystem work.
- Inventory probes that load plugin binaries run in a **separate child process** with a per-plugin timeout (default 10 s). A crash or hang only marks that plugin "Couldn't read".

**Events** (Python to JS, via `window.evaluate_js` dispatching a CustomEvent, or equivalent):

| Event | Payload |
|---|---|
| `job.progress` | `{job_id, stage, stage_index, stage_count, percent or null, message}` |
| `job.partial` | `{job_id, section, data}` e.g. plugins list ready before media hashing finishes, so the report can render early |
| `job.done` | `{job_id, report_id}` |
| `job.failed` | `{job_id, error}` |
| `job.cancelled` | `{job_id}` |
| `inventory.updated` | `{scanned_at, count}` so open reports refresh installed status live |
| `kb.updated` | `{kb_version}` |

**Scan stages** (fixed order, used by the progress UI): `detect`, `read`, `resolve`, `inventory_match`, `enrich`, `media`, `build`.

**Partial rendering:** the report view renders as soon as `read` + `resolve` finish. Media hashing and audio header reads (slowest part on big projects) fill in afterwards via `job.partial`.

---

## 9. Storage and caching

All local, in the OS app-data folder (`%APPDATA%\Rackcheck` / `~/Library/Application Support/Rackcheck`):

| Item | Format | Notes |
|---|---|---|
| Settings | JSON | |
| Plugin inventory cache | SQLite | Keyed by path + mtime + size (SPEC-02 section 6) |
| Recent reports | JSON files + SQLite index | Last 50 kept; user can clear. Stored reports honor the redact setting only on export, not in cache |
| Knowledge base | Bundled JSON + downloaded updates | Updates signed and verified before use |
| Logs | Rolling text logs, 7 days | No project contents logged, paths only at debug level |

Reopening a recent report loads from cache instantly and shows "Scanned <date>. Rescan?" if the project file has changed since.

---

## 10. Accessibility and polish

- Full keyboard navigation: Tab order, Enter to open rows, Esc to close panels, Cmd/Ctrl+O to browse, Cmd/Ctrl+E to export, Cmd/Ctrl+F to search the current tab.
- Status is never color-only: every status has an icon and text (important for the green/yellow/red verdict).
- Screen-reader labels on all icons and badges.
- Respects OS dark/light mode and text scaling.
- Minimum window size 900x600; tables scroll horizontally inside their panel rather than the whole window.
- Copy-friendly: right-click a row to copy name, link, or row as text.

---

## 11. Acceptance criteria (Phase 2 GUI)

- [ ] New user can install, launch, and get a report from an Ableton project without instructions (hallway test with 3 non-technical people)
- [ ] Drop works for file, folder, zip, and multiple items
- [ ] Inventory scan runs in background; report updates live when it finishes
- [ ] Verdict card, warnings, and all tabs render for every Phase 1 fixture
- [ ] Every field present in the JSON report is visible somewhere in the UI (automated check: walk the report JSON and assert each non-null field is rendered or listed in Raw)
- [ ] All export types produce files byte-identical to the CLI output for the same report
- [ ] Cancel works at every stage
- [ ] A plugin that crashes on probe does not crash or freeze the app
- [ ] Works fully offline
- [ ] Keyboard-only walkthrough possible
