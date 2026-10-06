# Rackcheck: Plugin Dependency Scanner

Drop a DAW project file. See exactly what plugins it uses, which ones you have installed, and what they cost.

**Current version:** 0.1.0-alpha  
**Project readers:** REAPER `.rpp`, Ableton Live `.als`, and DAWproject  
**Platforms:** Windows and macOS plugin inventory scanning; GUI and host support still need real-machine verification

---

## What It Does

Rackcheck reads any supported DAW project file and extracts:
- Every plugin used (name, vendor, format: VST2/VST3/AU/CLAP/AAX/stock)
- Which track each plugin is on
- Whether it's installed on your machine
- Links to the plugin's homepage and manual
- Licensing info (iLok, vendor account, free, etc.)
- Whether the project will open on your OS and DAW

Use it to:
- **Before sending a project:** "Is my collaborator missing any plugins?"
- **Opening old sessions:** "Where is that VST2 plugin I used 3 years ago?"
- **Managing dependencies:** "What happens if I uninstall Serum?"

---

## Installation

### From Source (Development)

Requires Python 3.12+.

```bash
git clone https://github.com/<you>/rackcheck.git
cd rackcheck
python -m venv .venv

# Windows
.venv\Scripts\activate
pip install -e .[dev,gui]

# macOS / Linux
source .venv/bin/activate
pip install -e .[dev,gui]
```

### Pre-built Installers (Phase 2)

Windows and macOS signed installers will ship after Phase 1 readers are complete.

---

## Quick Start

### CLI Usage

```bash
# Scan a project and print a summary
rackcheck scan ~/Music/my-track.als

# Output full JSON report
rackcheck scan ~/Music/my-track.als --json > report.json

# Scan a folder (finds all projects)
rackcheck scan ~/Music/sessions/

# Detect format without reading (fast)
rackcheck detect ~/Music/my-track.als
```

### GUI Usage

```bash
# Needs the optional gui extra (pywebview): pip install -e .[gui]
rackcheck-gui            # or: python -m rackcheck_gui
```

Drop a project file, folder or zip on the window (or use Browse). Exports use the same
engine writers as the CLI. Settings, recent reports and the plugin inventory are stored in
`%APPDATA%\Rackcheck` (`~/Library/Application Support/Rackcheck` on macOS); set
`RACKCHECK_DATA_DIR` to use another folder.

### Run Tests

```bash
.venv/Scripts/python -m pytest -v
```

**278 automated tests pass** across readers, inventory scanning, reports, exports, CLI, and GUI bridge.
Real projects saved by DAWs and an interactive GUI check are still needed for release validation.

---

## Project Structure

```
rackcheck/
├── src/rackcheck_engine/
│   ├── __init__.py            # Public API
│   ├── __main__.py            # CLI entry point
│   ├── cli.py                 # Command-line interface
│   ├── model.py               # Common data model (SPEC-02 Section 3)
│   ├── detect.py              # Format detection (SPEC-02 Section 2)
│   ├── inputs.py              # Input handling: files, folders, zips
│   ├── safety.py              # Zip bomb, DTD, and other protections
│   ├── errors.py              # Exception types
│   └── readers/
│       ├── base.py            # BaseReader interface
│       ├── reaper.py          # REAPER .rpp reader (Phase 1)
│       ├── ableton.py         # Ableton .als reader (Phase 1)
│       └── dawproject.py      # DAWproject reader (Phase 1)
├── tests/
│   ├── conftest.py            # pytest fixtures
│   ├── test_detect.py         # Format detection tests
│   ├── test_inputs.py         # Input handling and safety tests
│   └── test_cli_and_model.py  # CLI and model tests
├── fixtures/                  # Test projects (crafted and real)
├── docs/
│   ├── spec-coverage.md       # Implementation tracking
│   ├── LICENSE-LEDGER.md      # Reference projects and licenses
│   ├── format-notes/          # Clean-room format documentation
│   └── ...
├── DECISIONS.md               # Architecture decisions
├── PROMPT.md                  # Autonomous build instructions
├── SPEC-*.md                  # Detailed specifications
├── specs/                     # All specification files (reference)
└── setup.py / pyproject.toml  # Package definition
```

---

## Specifications

Comprehensive design specs are in the `specs/` folder:

- **SPEC-01** – Product goals, architecture, build phases
- **SPEC-02** – File format readers, data model, export formats
- **SPEC-03** – GUI and engine API
- **SPEC-04** – Knowledge base (KB) operations
- **SPEC-05** – Packaging, signing, updates
- **SPEC-06** – Testing, fixtures, QA
- **SPEC-07** – Security, privacy, legal
- **SPEC-08** – Collaboration file formats
- **SPEC-09** – Business model and licensing (open decisions)

Start with **SPEC-01** and **SPEC-02** for the full picture.

---

## Development Status

### Phase 0 ✓ (Complete)
- [x] Format detector (all target DAW formats)
- [x] Common data model + JSON serialization
- [x] Input handling (files, folders, zips, bundles)
- [x] CLI: `rackcheck scan`
- [x] Reader interface
- [x] Safety hardening (zip bombs, zip slip, gzip bombs)
- [x] 34 unit tests, all passing

### Phase 1 ✓ (Implementation complete; real-project validation pending)
- [x] REAPER .rpp reader
- [x] Ableton .als reader
- [x] DAWproject reader
- [x] Synthetic reader fixture suite
- [ ] DAW-saved acceptance fixtures

### Phase 2 Core ✓ (Release work pending)
- [x] Installed plugin inventory scanner and identity resolver
- [x] Knowledge base v1, report builder, JSON/CSV exports
- [x] GUI bridge and report screens
- [ ] Real-window GUI verification
- [ ] Signed Windows and macOS installers

### Phase 3-7 (Later)
- Studio One, FL Studio, Cubase native readers
- Logic Pro / GarageBand
- Pro Tools text export and native readers
- Power features (library scan, collaborator compare, send pack)
- Long-tail DAWs and Linux build

---

## License

**Source code:** MIT (SPEC-01 Section 4)  
**Knowledge base data:** CC0 (public domain) – see SPEC-04 Section 3  
**Trademarks:** This project is not affiliated with or endorsed by Ableton, Apple, Avid, Bitwig, Cockos, Image-Line, Fender/PreSonus, Steinberg, or any plugin vendor.

See **DECISIONS.md** and **docs/LICENSE-LEDGER.md** for references and compliance details.

---

## Contributing

### Reporting Bugs

Use GitHub Issues. Include:
1. What you scanned (DAW, project file type)
2. Command and output (redact file paths if sensitive)
3. Expected vs. actual result
4. Your OS and Python version

### Suggesting Features

Open a GitHub Discussion. Check SPEC-09 (business model) and SPEC-01 Phase 6-7 (planned features) first.

### Contributing Fixtures

Real-world project fixtures are invaluable for QA. If you'd like to donate a project for testing:
1. Open an issue or email (to be specified in public beta phase)
2. Confirm consent: fixture may be used to test plugin detection, with audio stripped for privacy
3. We keep fixtures private (never public) unless you consent to publication

### Contributing to the Knowledge Base

When Phase 2 ships, the KB repo will accept community PRs. Contributors sign off via DCO (Developer Certificate of Origin).

---

## Support

- **Docs:** See `specs/` and `DECISIONS.md`
- **Tests:** Run `pytest -v` to see what's implemented
- **Spec coverage:** See `docs/spec-coverage.md` for status of every requirement
- **Known issues:** See `TODO.md` for blockers and workarounds

---

## FAQ

**Q: Can I use this to open projects yet?**  
A: Yes. The readers extract plugins from REAPER, Ableton, and DAWproject files. Other formats are detected but do not yet have readers.

**Q: When will it support my DAW?**  
A: See the **Development Status** section above. Priority order: REAPER, Ableton, DAWproject (Phase 1), then Studio One, FL Studio, Cubase (Phase 3), Logic Pro (Phase 4), and Pro Tools (Phase 5).

**Q: Is there a GUI yet?**  
A: Yes. The pywebview GUI and engine bridge are implemented. A real-window check on the target operating systems remains part of release validation.

**Q: How is this different from Pluginventory?**  
A: Pluginventory (macOS, Ableton-only) is excellent. Rackcheck is cross-platform, supports many DAWs (Rackcheck 5+ by Phase 3, Pluginventory 1), and includes collaboration features (compare plugins, send packs). Both serve the same community; Rackcheck is aimed at the producer workflow across DAWs and machines.

**Q: Will it cost money?**  
A: See SPEC-09. The recommendation is a free tier (scan any project, see the report) and a Pro tier (collaboration features, library scan, send packs). Not decided yet; the community will help decide during beta. No paywalls for core functionality.

**Q: Is there any tracking or telemetry?**  
A: No. All scans stay on your machine. Optional opt-in reports (unknown plugins, crash logs) are off by default and send only the fields you approve. See SPEC-07 for the threat model and privacy design.



## Plain-language overview

See [ELI5: What Rackcheck does](ELI5.md) for a simple explanation of the project and its current early-stage status.

