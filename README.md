# Rackcheck

Rackcheck scans DAW project files and lists every plugin, track, and media file the project
uses, then checks which of those are installed on the machine and whether the project is
likely to open and play there.

**Status:** 0.1.0-alpha. Core engine, CLI, and GUI are implemented. Real-DAW fixture
validation and GUI/host verification on real machines are still pending.

## What it does

For a supported project, Rackcheck reports:

- Every plugin used: name, vendor, format (VST2, VST3, AU, CLAP, AAX, or stock device), and the track it sits on.
- Whether each plugin is installed locally (requires the plugin inventory scan).
- Links and licensing hints from a bundled knowledge base (`kb/vendors.json`, `kb/plugins.json`).
- Media files referenced by the project, including missing files and files outside the project folder.
- A "send-ready" verdict with the reasons behind it.

Supported project formats:

| Format | Extension(s) | Reader status |
|---|---|---|
| REAPER | `.rpp` | Implemented, tested with crafted fixtures |
| Ableton Live | `.als` | Implemented, tested with crafted fixtures |
| DAWproject | `.dawproject` | Implemented, tested with crafted fixtures |
| Studio One, FL Studio, Cubase, Logic, Pro Tools | various | Detected only; no reader yet |

Detection is content-based (magic bytes and XML/zip structure). File extensions are only a
hint, so renamed or backup files (`.rpp-bak`, extensionless `.als`) are still recognised.

## Installation

Requires Python 3.12 or newer. The engine is standard-library only; the GUI needs `pywebview`.

```bash
git clone <this repository>
cd <this repository>
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e .[dev,gui]     # engine, tests, lint, and GUI
# or, engine only:
pip install -e .
```

Pre-built signed installers are planned for a later phase and are not available yet.

## Usage

### Command line

```bash
rackcheck scan ~/Music/my-track.als             # human-readable summary
rackcheck scan ~/Music/my-track.als --json      # full JSON report to stdout
rackcheck scan ~/Music/sessions/                # scan every project in a folder
rackcheck scan project.zip --csv report.csv --plugin-list plugins.csv
rackcheck scan project.rpp --inventory saved-inventory.json   # use a saved plugin inventory
rackcheck scan project.rpp --no-inventory       # skip the installed-plugin check
rackcheck scan project.rpp --redact-paths       # strip home-directory paths from output
rackcheck scan project.rpp --kb ./my-kb         # use another knowledge-base folder
rackcheck detect project.als                    # format detection only (JSON)
rackcheck --version
```

Run `rackcheck scan --help` for the authoritative option list.

### Desktop GUI

```bash
rackcheck-gui            # or: python -m rackcheck_gui
```

Drop a project file, folder, or zip on the window, or use Browse. The window shows a report
with Plugins, Tracks, Media, Project, and Raw tabs, and exports JSON or CSV using the same
writers as the CLI. Settings, recent reports, and the plugin inventory are stored in
`%APPDATA%\Rackcheck` on Windows or `~/Library/Application Support/Rackcheck` on macOS.
Set `RACKCHECK_DATA_DIR` to use a different folder.

The design goal (SPEC-01, principle 3) is that Rackcheck only reads project files; the
read-only guarantee is listed as "in progress" in `docs/spec-coverage.md`.

## Configuration

| Setting | Where | Effect |
|---|---|---|
| `RACKCHECK_DATA_DIR` | environment variable | Overrides the settings/report/inventory data folder used by the GUI. |
| `--kb DIR` | CLI flag | Uses a different knowledge-base folder instead of the bundled `kb/`. |
| `--inventory PATH` / `--no-inventory` | CLI flags | Use a saved plugin inventory, or skip the installed-plugin check. |
| Plugin folders | GUI Settings | Extra folders scanned for installed plugins. |

## Testing and lint

```bash
python -m pytest -q          # test suite
python -m ruff check src tests
```

The current suite passes locally on Linux (285 tests). CI runs pytest and ruff on Ubuntu,
Windows, and macOS with Python 3.12 (`.github/workflows/ci.yml`). Passing tests do not prove
compatibility with real DAW-saved projects; see `docs/spec-coverage.md` for what is still
blocked on real fixtures.

## Project layout

```
src/rackcheck_engine/   Engine: detection, readers, resolution, reports, exports, CLI
src/rackcheck_gui/      pywebview GUI and its JavaScript bridge (api.py) plus static HTML/JS/CSS
kb/                     Bundled knowledge base (vendors.json, plugins.json)
tests/                  pytest suite
specs/                  Product and engineering specifications (SPEC-00 to SPEC-11)
docs/                   Spec coverage matrix, licence ledger, wiki copy
shared/scripts/         Release and project helper scripts
.github/workflows/      CI
```

See `docs/wiki/Codebase-Map.md` for a file-by-file guide.

## Specifications

Start with `specs/SPEC-01-build-order.md` and `specs/SPEC-02-file-format-readers.md`. The
index is `specs/SPEC-00-index.md`. Implementation status per requirement is tracked in
`docs/spec-coverage.md`.

## Contributing

Read `DECISIONS.md` before changing architecture, and the relevant SPEC before changing
behaviour. Add tests for new reader or resolver behaviour and keep `ruff` clean. Do not commit
real user projects; fixtures are crafted or donated with consent.

## Licence

Copyright © 2026 Sheldon Davidson. All rights reserved. See `LICENSE` (Rackcheck Proprietary
Source License). Note: `pyproject.toml` currently declares `license = { text = "MIT" }`, which
conflicts with the `LICENSE` file; this needs to be resolved by the owner.
