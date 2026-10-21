# User Guide

## Install

Python 3.12+ is required.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .                 # CLI only
pip install -e .[gui]            # adds the desktop GUI (pywebview)
```

Signed installers are not available yet.

## Scan a project from the command line

```bash
rackcheck scan path/to/project.als
rackcheck scan path/to/project.als --json > report.json
rackcheck scan path/to/Sessions/          # folder: every project inside is scanned
rackcheck scan project.zip                # zip archives are extracted safely and inspected
rackcheck detect path/to/file             # identify the format only
```

Useful options: `--csv PATH` (full report as CSV), `--plugin-list PATH` (plugin list CSV),
`--inventory PATH` (use a saved plugin inventory), `--no-inventory` (skip the installed-plugin
check), `--kb DIR` (alternative knowledge base), `--redact-paths` (remove home-folder paths
from output, useful before sharing a report). `rackcheck scan --help` lists everything.

## Use the GUI

Start with `rackcheck-gui` or `python -m rackcheck_gui`. Drop a file, folder or zip onto
the window or use Browse. Tabs:

- **Plugins**: every plugin, its format, vendor, and install status. Select one for details.
- **Tracks**: tracks and the plugins on each.
- **Media**: audio files referenced by the project, with missing or external files flagged.
- **Project**: project-level facts and the send-ready verdict.
- **Raw**: the full report data.

Export JSON or CSV from the report view. Recent reports can be reopened from the home screen.

## Reading the verdict

The send-ready verdict lists reasons, for example missing plugins or missing media. Plugin
installation status depends on the inventory: without an inventory the check is skipped and
the verdict says so. Knowledge-base vendor and plugin data is seed data and has not been
independently verified.

## Where data is stored

| Platform | Location |
|---|---|
| Windows | `%APPDATA%\Rackcheck` |
| macOS | `~/Library/Application Support/Rackcheck` |
| Any | override with the `RACKCHECK_DATA_DIR` environment variable |

## Supported projects

REAPER `.rpp`, Ableton Live `.als` and DAWproject `.dawproject` are read. Studio One, FL Studio,
Cubase, Logic and Pro Tools projects are recognised by detection but not read yet.

## Troubleshooting

- **"Reader not available"** - the project format is detected but has no reader yet.
- **Plugins shown as unknown** - the plugin is not in the knowledge base or the inventory; try
  `--plugin-list` to review them, or extend the knowledge base with `--kb`.
- **Inventory unreadable** - the saved inventory file is malformed; re-run without `--inventory`.
