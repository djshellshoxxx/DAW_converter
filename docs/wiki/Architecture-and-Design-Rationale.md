# Architecture and Design Rationale

Rationale below is taken from `DECISIONS.md`, `specs/`, and the code. Points marked
*(inferred)* are conclusions drawn from the code rather than written decisions.

## Layers

1. **Detection** (`detect.py`) identifies a file's format from magic bytes and content. The
   extension is only a hint (SPEC-01 P2), because real projects appear as `.rpp-bak`, extensionless
   or misnamed zip files. Detection returns format, confidence, and reason so failures can be explained.
2. **Inputs** (`inputs.py`, `safety.py`) turn a file, folder, or zip into candidate projects.
   Zip slip, zip bombs, and gzip bombs are rejected before parsing.
3. **Readers** (`readers/`) convert one format into the common model (`model.py`, SPEC-02 section 3).
   Each reader implements `can_read` and `read`, and is registered in `readers/__init__.py`.
4. **Resolution** (`resolve.py`) matches plugin references to the knowledge base and to the
   installed inventory, in ordered confidence tiers.
5. **Report** (`report.py`) builds the JSON report: summary, warnings, plugins, tracks, media.
6. **Exports** (`export.py`) write JSON, CSV, and plugin-list CSV. CSV output guards against
   formula injection.
7. **Front ends**: `cli.py` (command line) and `rackcheck_gui` (pywebview). Both call the same
   `service.scan_candidate`, so their reports match.

## Key decisions

- **Python, standard library only for the core.** *Decision recorded in DECISIONS.md.* Avoids a
  compile step and eases PyInstaller packaging. A Rust parser (bravoh-daw) was considered but not
  tested against real fixtures.
- **pywebview for the GUI.** *Decision recorded.* Keeps everything in one Python repository with
  a small bridge rather than a separate IPC server.
- **Reader isolation.** *Decision recorded.* One module per format, each optional. Missing readers
  degrade to a "reader not available" result instead of failing the scan.
- **Scans run in a child process with bounded results.** `service.py` runs each reader in a
  subprocess with a 60 s timeout and a 64 MB serialised-result cap, so a hostile or corrupt project
  cannot hang or exhaust the parent. *(inferred from code; matches the SPEC-01 "never load plugin
  binaries in the main process" principle.)*
- **Unknown stays unknown.** Fields default to `None` and are never guessed (SPEC-02 section 3).
- **Clean-room format work for GPL references.** *Decision recorded.* Notes are meant to go in
  `docs/format-notes/` (that folder is referenced but not present in this snapshot); implementation is written from notes, and `docs/LICENSE-LEDGER.md` tracks
  each reference project.
- **Bridge safety in the GUI.** Paths from JavaScript are honoured only if the user chose them
  (native dialog, drop, or recent entry). Methods not listed in SPEC-03 are private by naming
  convention. *(from `api.py` docstring)*
- **Bounded XML parsing.** `defusedxml` is intended to block DTDs and external entities. The
  spec-coverage matrix marks this as pending for some paths, so treat it as partially done.

## Known limitations

- No real DAW-saved fixtures are committed (by design, real projects are not published), so reader
  accuracy on real files is unverified.
- Installed-plugin inventory covers Windows and macOS only.
- The plugin knowledge base is seed data marked unverified.
