# License Ledger

Every outside project used, consulted, or referenced for code, format documentation, or knowledge. Format per SPEC-01 Section 4.

**License classes:**
- **A: Use code** (MIT, BSD, Apache-2.0, ISC) – Can copy or depend on it. Copyright notice in THIRD_PARTY_NOTICES.
- **B: Link only** (LGPL) – Use only as a separately linked library (DLL/.so/.dylib or separate Python package).
- **C: Reference only** (GPL, AGPL, non-commercial, unknown/no license) – Read for format knowledge only. Write our own implementation via clean-room process. Notes in docs/format-notes/.

---

## Phase 1 Reference Projects (SPEC-02 Sections 4.1-4.3)

### REAPER .rpp (SPEC-02 Section 4.1)

| Project | URL | License | Class | Version/Commit | Notes |
|---------|-----|---------|-------|-----------------|-------|
| Perlence/rpp | https://github.com/Perlence/rpp | BSD-3-Clause | A | Check release | Parser/emitter, ElementTree-like API for REAPER chunks |
| IcEarthlight/rppxml | https://github.com/IcEarthlight/rppxml | Verify in repo | Verify | Latest commit | Python + C++ (WDL), 13x faster than rpp on large files, reads .RfxChain |
| reaproj (PyPI) | https://pypi.org/project/reaproj/ | Verify in PyPI | Verify | Latest PyPI | Object model on top of rpp |
| GriffinSauce/reaper-project-parser | https://github.com/GriffinSauce/reaper-project-parser | Verify in repo | Verify | Latest commit | TypeScript, pre-1.0 |

**Status:** Format notes to be written during Phase 1 parser development. No code copied; implementation written from format spec.

### Ableton Live .als (SPEC-02 Section 4.2)

| Project | URL | License | Class | Version/Commit | Notes |
|---------|-----|---------|-------|-----------------|-------|
| bounceconnection/pluginventory | https://github.com/bounceconnection/pluginventory | MIT | A | Latest release | macOS app: scans .als for AU/VST3/VST2 plugins. Study its matching logic. |
| bravoh-daw | https://docs.rs/bravoh-daw/ | MIT | A | Latest crate release | Rust unified parser including Ableton plugins. Format knowledge only; we build in Python. |
| luizen/als-tools | https://github.com/luizen/als-tools | Verify in repo | Verify | Latest commit | C#, search/list/count across .als files |
| my5t3ry/als-parser | https://github.com/my5t3ry/als-parser | Verify in repo | Verify | Latest commit | Java, Live 8+ |
| offlinemark/dawtool | https://github.com/offlinemark/dawtool | Verify in repo | Verify | Latest commit | Python, ADC 2020 talk, focused on markers/tempo |
| madisonrickert/ableton-tools | https://github.com/madisonrickert/ableton-tools | Verify in repo | Verify | Latest commit | Python, safe .als editing, sample reference handling |

**Status:** Format notes to be written during Phase 1. No code copied.

### DAWproject .dawproject (SPEC-02 Section 4.3)

| Project | URL | License | Class | Version/Commit | Notes |
|---------|-----|---------|-------|-----------------|-------|
| bitwig/dawproject | https://github.com/bitwig/dawproject | MIT | A | Latest release | Official spec, XML schema, reference DOM |
| roex-audio/dawproject-py | https://github.com/roex-audio/dawproject-py | MIT | A | Latest release | Python load/inspect/save library. May be used as a dependency. |
| dawproject-rs | https://github.com/maykBrito/dawproject-rs | MIT NO-AI | C | Latest commit | Nonstandard license; do not use. Format reference only. |
| audiohacking/daw2logic | https://github.com/audiohacking/daw2logic | Verify in repo | Verify | Latest commit | DAWproject to Logic converter; good test-file source |

**Status:** Format notes to be written. Implementation in Python from spec; may use dawproject-py library if MIT confirmed.

---

## Utilities and Tools Referenced (SPEC-02)

| Project | URL | License | Class | Purpose |
|---------|-----|---------|-------|---------|
| Python defusedxml | https://github.com/tiran/defusedxml | Python Software Foundation | A | XML safety: disable DTDs, external entities (Phase 1 readers) |
| pytest | https://pytest.org/ | MIT | A | Test framework |
| dataclasses | Python stdlib | PSF | A | Data model definition |
| PyInstaller | https://www.pyinstaller.org/ | GPL v2 + exceptions | B | App packaging (SPEC-05); kept as separate tool, not bundled in our code |

---

## Format Documentation and Reverse Engineering (SPEC-02 Section 4 referenced in notes)

| Source | License | Class | Usage |
|--------|---------|-------|-------|
| Steinberg VST3 Developer Portal (official spec) | Proprietary | Reference | VST3 plugin format, moduleinfo.json schema |
| free-audio/clap (official spec) | MIT | A | CLAP plugin format, descriptor structure |
| Apple Audio Unit docs (official spec) | Proprietary | Reference | AU plugin format |
| Bitwig DAWproject official repo | MIT | A | DAWproject format specification |
| ptformat (Damien Zammit, Robin Gareus) | LGPL-2.1+ | B | Pro Tools XOR decryption, block walk (used in Ardour). May be referenced for Phase 5b research. |
| logicx-analyzer | Check repo | Verify | Logic ProjectData reverse engineering notes (~60% of format understood) |
| LogicProFormatWriter | MIT | A | Includes PROJECTDATA_FORMAT.md byte-level spec and tools |
| logicxkit | Check repo | Verify | Logic channel strips, AU state reading |
| CubaseTools | Check repo | Verify | Cubase 10-15 format analysis |
| fgimian/cubase-project-plugins | MIT | A | Cubase .cpr plugin listing (purpose-built, GUID/name matching) |

---

## Quality and Safety Tools

| Project | URL | License | Purpose |
|---------|-----|---------|---------|
| tox | https://tox.wiki/ | MIT | Test automation across Python versions |
| black | https://github.com/psf/black | MIT | Code formatting (CI) |
| ruff | https://github.com/astral-sh/ruff | MIT | Linting (CI) |
| GitHub Actions | https://github.com/features/actions | GitHub-proprietary | CI/CD platform |

---

## No Outside Code Copied

**Status:** All Phase 0 code is original, written directly in this repo. No reference project code has been copied.

**Next steps:**
- Phase 1 readers will reference format documentation from the projects listed above. Clean-room notes will be written for any GPL sources (FL Studio history, Cubase reverse engineering) before implementation.
- License ledger will be updated as each Phase 1 reader is integrated.
- Before any paid release, this ledger will be reviewed by a lawyer to confirm open-source compliance and that reverse-engineering rights are defensible in target jurisdictions (Canada, US, EU).

---

**Last updated:** 2026-09-29  
**Next review:** As Phase 1 readers are integrated (before Phase 2)
