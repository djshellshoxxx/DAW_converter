# SPEC-08: Collaboration File Formats and Features

**Project:** Plugin Dependency Scanner (working name: "Rackcheck")
**Related:** SPEC-01 Phase 6, SPEC-02 section 10 (report export), SPEC-03 sections 4.9 and 7, SPEC-07 (privacy)
**Status:** Draft v1, September 2026

Files that one person's copy of the app creates and another person's copy reads. Because they cross between users and app versions, their formats are specified and versioned here.

---

## 1. File types

| File | Extension | Purpose |
|---|---|---|
| Report | `.json` (SPEC-02 10.2) | Full scan report; can be opened in the app without the project |
| Inventory | `.rackcheck-inventory.json` | "Here's what plugins I have" for a collaborator to compare against |
| Requirements | `.rackcheck-requirements.json` | "Here's what this project needs"; small file that can live next to the project |
| Send pack | folder or `.zip` | Project + collected media + report + readme, ready to send |

All JSON files: UTF-8, include `format`, `format_version` (SemVer) and `created_with` (app version). Readers accept the same major version and ignore unknown fields (forward compatible within a major version).

The installer registers the `.rackcheck-inventory.json` and `.rackcheck-requirements.json` types so double-clicking opens them in the app.

---

## 2. Inventory file

Lets a collaborator share their installed plugins without sharing their machine details.

```json
{
  "format": "rackcheck-inventory",
  "format_version": "1.0.0",
  "created_with": "1.3.0",
  "created_at": "2026-10-10T12:00:00-07:00",
  "owner_label": "Alex",
  "platform": { "os_family": "macos", "arch": "arm64" },
  "daws": [
    { "name": "Ableton Live", "version": "12.1.5", "edition": null }
  ],
  "plugins": [
    {
      "name": "Serum",
      "vendor": "Xfer Records",
      "format": "vst3",
      "version": "1.368",
      "arch": "arm64",
      "identity": { "vst3_cid": "...", "vst2_unique_id": null, "au": null, "clap_id": null, "aax": null },
      "kb_id": "xfer-serum"
    }
  ]
}
```

**Privacy defaults (SPEC-07):**
- No file paths, no usernames, no machine name. `owner_label` is whatever the user types (default blank).
- DAW list is optional (checkbox, default on, since it's what makes stock-device comparison work).
- The export dialog shows a preview of the content before saving.

**DAW detection for the inventory:** read installed DAW versions from standard install locations. Mark each as detected or user-entered. Users can add or remove DAWs manually (e.g. Ableton edition matters for stock devices).

---

## 3. Requirements file

A lightweight "what this project needs" list, generated from a report. Useful to drop next to a project in a shared folder, attach to a message, or commit alongside a project in version control.

```json
{
  "format": "rackcheck-requirements",
  "format_version": "1.0.0",
  "created_with": "1.3.0",
  "created_at": "...",
  "project": { "name": "Nightfall", "daw": "Ableton Live", "daw_version": "12.1.5",
               "tempo_bpm": 140, "sample_rate": 48000 },
  "requires": {
    "daw": { "name": "Ableton Live", "min_version": "12.1", "edition_hint": "Suite" },
    "plugins": [
      {
        "name": "Serum", "vendor": "Xfer Records",
        "formats_seen": ["vst3"], "min_version": null,
        "identity": { "vst3_cid": "..." }, "kb_id": "xfer-serum",
        "instances": 3, "homepage": "https://..."
      }
    ],
    "stock_devices": ["Wavetable", "Echo"],
    "external_hardware": [],
    "max_for_live": []
  },
  "media": { "file_count": 212, "total_bytes": 1800000000, "outside_project_folder": 0 }
}
```

`edition_hint` comes from the KB stock device lists (SPEC-04) when a stock device only exists in higher DAW editions.

---

## 4. Compare

**Inputs:** a report or requirements file (what's needed) and one or more inventories (what someone has). The local machine's own inventory is always available as one of them.

**Matching:** same resolver as SPEC-02 section 5 (exact ID, cross-format via KB, then normalized name + vendor).

**Per plugin result:**
| Result | Meaning |
|---|---|
| `has_same` | Same plugin, same format |
| `has_other_format` | Same plugin, different format (note whether the DAW usually substitutes automatically, from KB) |
| `has_older` | Same plugin, older version than the project saved with (when known) |
| `missing` | Not present |
| `stock_ok` / `stock_missing_daw` | Stock device; collaborator has / lacks the needed DAW (or edition) |
| `unknown` | Couldn't identify |

**Platform check:** collaborator's OS vs plugin platforms (e.g. AU-only plugin, collaborator on Windows).

**Output:** the report view gains a column per compared inventory (SPEC-03 section 4.9), verdict becomes "Will this open for Alex?", and the compare result is included in exports as a `compare` section:

```json
"compare": [{
  "inventory_label": "Alex",
  "platform": "macos-arm64",
  "verdict": "red",
  "results": [{ "plugin_key": "xfer-serum", "result": "missing" }],
  "freeze_suggestions": ["t1", "t4"]
}]
```
The CSV full report gets matching `compare_<label>_result` columns on plugin rows.

**Freeze suggestions:** tracks whose chains contain a plugin the collaborator is missing, so the sender knows what to freeze, flatten, or bounce before sending.

---

## 5. Send pack

Bundles everything a collaborator needs to open the project.

**Principle:** never modify the user's project (SPEC-01 P3). The app does not rewrite media paths inside project files. Instead it checks whether the project is self-contained and, if not, walks the user through their DAW's own "collect media" feature first.

**Flow:**
1. User clicks **Create send pack** on a report.
2. The app checks: missing media, media outside the project folder, plugins the chosen collaborator lacks (if an inventory was loaded).
3. If media is outside the folder, show DAW-specific instructions to collect it using the DAW's own feature (e.g. Ableton "Collect All and Save", REAPER "Save As" with copy media, Logic "Save As" with assets included, FL Studio "Export project data files", Cubase "Back up Project", Studio One "Save To New Folder", Pro Tools "Save Copy In" with audio files). Verify exact menu names per DAW version and keep them in the KB so they can be updated without an app release. Then rescan.
4. If plugins will be missing for the collaborator, show freeze suggestions and let the user continue or go back.
5. Build the pack.

**Pack contents:**
```
Nightfall_sendpack/
  project/                    # copy of the project folder (untouched)
  REPORT.html                 # human-readable report
  report.json                 # full report (SPEC-02 10.2), redact-paths on by default
  requirements.rackcheck-requirements.json
  README.txt                  # plain-language summary
  manifest.json               # file list with sizes and SHA-256 hashes
```

**README.txt example:**
```
Project: Nightfall (Ableton Live 12.1.5, 140 BPM, 48 kHz)

To open this project you need:
  - Ableton Live 12.1 or newer (Suite edition)
  - Serum by Xfer Records - https://...
  - Pro-Q 4 by FabFilter - https://...

Tracks frozen by the sender: Bass, Lead

Created with Rackcheck 1.3.0 on 2026-10-10
```

**Output options:** folder, or .zip (zip64 for packs over 4 GB). Show the final size before building. Warn if over common transfer limits (e.g. 2 GB) and suggest a file transfer service.

**Receiving a pack:** dropping a send pack (or its zip) into the app detects `manifest.json`, verifies hashes (reports any corrupted/missing files from the transfer), and immediately compares `requirements` against the receiver's own inventory.

---

## 6. Versioning rules

- `format_version` major bump = breaking change. Older apps show "This file was made with a newer version of Rackcheck. Please update." and don't guess.
- Minor bump = new optional fields. Older apps ignore them.
- Every format has a JSON Schema in `schemas/` and golden test files in `fixtures/collab/` (SPEC-06).
- Keep reading support for all previous major versions for at least 2 years.
