# Codebase Map: where to find what

| I want to... | Look in |
|---|---|
| Change the CLI flags or output | `src/rackcheck_engine/cli.py` |
| Add or fix a project format | `src/rackcheck_engine/readers/` (copy `reaper.py` or `ableton.py`), register in `readers/__init__.py` |
| Change format detection | `src/rackcheck_engine/detect.py` |
| Change how zips/folders/bundles are found | `src/rackcheck_engine/inputs.py` |
| Change size or safety limits | `src/rackcheck_engine/safety.py`, `inputs.py` |
| Change the common data model | `src/rackcheck_engine/model.py` (and SPEC-02 section 3) |
| Change plugin matching | `src/rackcheck_engine/resolve.py` |
| Change the installed-plugin scan | `src/rackcheck_engine/inventory/scan.py` |
| Change the JSON report or verdict/warnings | `src/rackcheck_engine/report.py` |
| Change export formats | `src/rackcheck_engine/export.py` |
| Change timeouts, reader worker process | `src/rackcheck_engine/service.py` |
| Edit plugin or vendor knowledge base | `kb/plugins.json`, `kb/vendors.json`, loader in `src/rackcheck_engine/kb/` |
| Change GUI screens | `src/rackcheck_gui/static/index.html`, `app.js`, `style.css`, `ui-assistance.js` |
| Change GUI-to-engine calls | `src/rackcheck_gui/api.py` |
| Change GUI window/startup | `src/rackcheck_gui/app.py`, `__main__.py` |
| Settings and recent reports storage | `src/rackcheck_gui/storage.py` |
| Requirements | `specs/SPEC-*.md`, status in `docs/spec-coverage.md` |
| Build order and roadmap | `specs/SPEC-01-build-order.md`, `specs/IMPLEMENTATION-ROADMAP.md` |
| CI | `.github/workflows/ci.yml` |
| Release/packaging helper scripts | `shared/scripts/` |
| Licences of reference projects | `docs/LICENSE-LEDGER.md`, `THIRD_PARTY_NOTICES` |

Tests mirror the modules: `test_reader_*.py` for readers, `test_resolve.py`, `test_export.py`,
`test_gui_api.py` and `test_gui_static.py` for the GUI, and `test_cli_*.py` for the CLI.
