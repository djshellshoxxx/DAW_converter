# SPEC-06: Testing and QA

**Project:** Plugin Dependency Scanner (working name: "Rackcheck")
**Related:** SPEC-01 section 6 (fixture strategy), SPEC-02 section 8 (reader checklist), SPEC-03 section 11, SPEC-05 section 7
**Status:** Draft v1, September 2026

Readers of undocumented binary formats break silently when DAWs update. Testing is how we find out before users do.

---

## 1. Test layers

| Layer | What it covers | Tooling (Python stack) | Runs |
|---|---|---|---|
| Unit | Parsing helpers, ID normalization, name matching, CSV/JSON writers | pytest | Every commit |
| Reader fixtures | Each reader against crafted and real projects, compared to golden JSON | pytest + golden files | Every commit |
| Schema | Every report validates against `report-v1.schema.json`; CSV columns match JSON fields | jsonschema + custom check | Every commit |
| Resolver / enrichment | Identity resolution against a test inventory and test KB | pytest | Every commit |
| Fuzz | Readers never crash or hang on malformed input | hypothesis, atheris (or cargo-fuzz for Rust) | Nightly |
| Performance | Scan time and memory on large projects | pytest-benchmark | Nightly |
| GUI | Front end against a mocked engine bridge | Playwright in a browser | Every commit |
| End to end | Built, signed app on clean VMs | Scripted smoke test + manual | Every release |
| Beta | Real users, real projects | Beta channel | Before each minor release |

---

## 2. Fixture library

### 2.1 Layout
```
fixtures/
  ableton/
    12.1/
      one-vst3-insert/
        project.als
        fixture.yaml
        expected.json
      same-plugin-x3/
      ...
    11.3/
  reaper/
  dawproject/
    bitwig-5.3/
    cubase-14/
    studio-one-7/
  flstudio/
  cubase/
  studioone/
  logic/
  protools/
    text-export/
    ptx/
```

### 2.2 `fixture.yaml` (one per fixture)
```yaml
daw: Ableton Live
daw_version: "12.1.5"
os: macOS 15.6
created_by: sheldon
created_at: 2026-10-02
purpose: One VST3 insert on one audio track
plugins_used:
  - name: TDR Nova
    format: vst3
    version: "2.1.x"
notes: Saved immediately after inserting, no parameter changes
```

### 2.3 Crafted fixture set
The standard set from SPEC-01 section 6, built in every supported DAW and major version. Use the same free plugins everywhere so outputs are comparable: Surge XT, Vital, TDR Nova, Valhalla Supermassive (confirm current availability and formats before building). Add DAW-specific cases:
- Ableton: racks with nested racks, Max for Live device, Simpler with a sample, External Instrument
- FL Studio: plugin in channel rack and in mixer slot, Patcher containing plugins
- REAPER: FX on master, input FX, renamed FX instance, JSFX
- Logic: multiple alternatives, Session Player track
- Pro Tools: plugins in every insert slot A to J, aux and instrument tracks, inactive plugin
- Studio One: FX chain, multi-instrument

### 2.4 Golden files
`expected.json` is the full report the reader should produce, with volatile fields (timestamps, machine info, absolute paths) normalized. When a reader changes on purpose, regenerate goldens with `make update-goldens`, and review the diff in the PR. A golden change nobody reviewed is a bug.

### 2.5 Real-world (donated) projects
- Collected through the beta program (section 6) with explicit consent.
- **Never committed to any public repo.** Stored in private encrypted storage, pulled only by a private CI job or run locally.
- Media files stripped if not needed (replace audio with same-length silence of the same format) to cut size and protect the donor's work.
- Donors can ask for deletion at any time.

### 2.6 Version coverage matrix
Maintain `fixtures/COVERAGE.md`: rows = DAWs, columns = versions, cells = fixture count and pass status. The SPEC-02 section 9 availability table is updated from this.

---

## 3. Specific test rules

**Detection:** every fixture also tested renamed (wrong extension), inside a zip, and inside a folder with other files.

**Robustness (must hold for every reader):**
- Truncated file at 10%, 50%, 90% length: returns a clear error or partial result, never crashes
- Zero-byte file
- Random bytes with a valid magic header
- Zip bomb and XML bomb inputs: rejected within limits (SPEC-07)
- Paths with unicode, spaces, very long paths (Windows 260+ chars)
- Read-only files and folders

**Timeouts:** each reader has a hard time budget (default 60 s) enforced by the engine; tests confirm it triggers.

**Export parity:** for every fixture, CSV full report contains exactly the same facts as the JSON report (automated check walking the JSON). GUI export output is byte-identical to CLI export output.

**Probe sandbox:** test plugins that crash on load, hang forever, and write to stdout; the inventory scan must continue and mark them "Couldn't read". Build these as tiny deliberately broken test plugins (JUCE makes this easy).

---

## 4. Performance targets

| Case | Target |
|---|---|
| Typical project (50 tracks, 100 plugin instances, 200 media files) on a 2020+ laptop | Report visible in under 5 s after drop (media hashing may continue in background) |
| Large project (300 tracks, 1 GB project file) | Report visible under 30 s, memory under 1 GB |
| Inventory scan, 1,000 installed plugins, metadata only | Under 60 s first run, under 5 s cached rescan |
| Library scan (Phase 6), 500 projects | Progress visible, cancellable, no UI freeze |

Nightly benchmarks fail the build on a 20% regression.

---

## 5. CI

- GitHub Actions matrix: Windows latest, macOS latest (arm64), macOS Intel runner while available.
- Every PR: unit, fixtures, schema, resolver, GUI tests.
- Nightly: fuzz (time-boxed), performance, private real-world fixture job.
- Release: full suite + SPEC-05 smoke tests on clean VMs.
- Coverage target: 85% line coverage on engine code; readers must hit every branch exercised by their fixtures.

---

## 6. Beta program

- Opt-in beta channel in Settings (SPEC-05 section 6.1).
- Beta invite list of producers across DAWs; aim for at least 5 active users per supported DAW before a reader leaves beta.
- In-app "Report a problem" creates a support bundle (logs, app/engine/KB versions, the report JSON with redact-paths on). Attaching the project file is a separate, explicit checkbox.
- Each reader has a public status: `beta` or `stable`. Promote to `stable` when: fixture coverage complete for current + previous major version, no open crash bugs, beta users confirm results on real projects.

---

## 7. When a DAW updates

A DAW release is the most likely cause of breakage. Process:
1. Watch DAW release notes (subscribe to each vendor's release announcements).
2. Within a week of a major/minor DAW release, build the crafted fixture set in the new version.
3. Run the suite. If a reader fails, ship a fix or mark that DAW version as "partial support" in the app (SPEC-03 section 5 banner) until fixed.
4. Update `COVERAGE.md` and the SPEC-02 availability table.

---

## 8. Bug handling

| Severity | Example | Target |
|---|---|---|
| S1 | Crash on launch, crash on common project, data written to user's project | Hotfix within 48 h |
| S2 | Wrong plugin list for a supported DAW version | Fix in next patch release |
| S3 | Wrong KB info, cosmetic UI issues | KB release or next minor |

Every fixed reader bug gets a new fixture that reproduces it before the fix is merged.
