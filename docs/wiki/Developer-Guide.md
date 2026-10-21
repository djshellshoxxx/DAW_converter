# Developer Guide

## Set up

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .[dev,gui]
```

Python 3.12 is the target version (`pyproject.toml`, CI matrix).

## Test and lint

```bash
python -m pytest -q
python -m ruff check src tests
```

Ruff is configured in `pyproject.toml` (line length 100, rules E, F, W, I, B, UP, SIM).
Pytest fixtures live in `tests/conftest.py`; `tests/helpers_report.py` is a shared helper for report tests.
Locally on Linux the suite passed with 285 tests and ruff reported no issues. CI runs both on
Ubuntu, Windows and macOS.

Testing gaps: no real DAW-saved projects are used, the GUI interactive behaviour is not
covered by automated tests (only the bridge and static HTML checks), and installed-plugin
scanning is tested with synthetic bundles.

## Add a reader

1. Create `src/rackcheck_engine/readers/<daw>.py` with a class implementing `can_read(path)`
   (returns a `Confidence` or `None`) and `read(path) -> ScanResult`. See `readers/base.py`.
2. Register it in `readers/__init__.py`.
3. Add the format to `detect.py` if it is not already recognised.
4. Add crafted fixtures under `tests/` and a `test_reader_<daw>.py`.
5. Update `docs/spec-coverage.md` and the license ledger if you referenced third-party code.

Readers run in a child process with a result-size cap, so they must return plain data and
must not print or write files.

## Add plugin knowledge

Edit `kb/plugins.json` and `kb/vendors.json`, then run `pytest tests/test_kb.py`. Use `--kb`
to test an alternative knowledge base without touching the bundled one.

## Conventions

- Follow the specs; change the spec before changing public behaviour.
- Keep the engine free of GUI imports; the GUI depends on the engine, not the reverse.
- Never guess unknown fields; use `None`.
- Record architecture decisions in `DECISIONS.md`.

## Release

Versioning is in `rackcheck_engine/__init__.py` (`ENGINE_VERSION`). Packaging and signing are
specified in `specs/SPEC-05-packaging-signing-updates.md` and are not implemented yet.
