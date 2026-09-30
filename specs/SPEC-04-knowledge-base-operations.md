# SPEC-04: Knowledge Base Operations

**Project:** Plugin Dependency Scanner (working name: "Rackcheck")
**Related:** SPEC-02 section 7 (KB schema), SPEC-05 (update delivery), SPEC-07 (signing, privacy)
**Status:** Draft v1, September 2026

The knowledge base (KB) is the vendor and plugin data that turns a raw plugin name into a useful answer: homepage, licensing system, platforms, status. The scanner is only as good as this data, and it goes stale constantly, so it needs its own process.

---

## 1. Goals

1. Accurate, sourced facts about plugins and vendors, linked only to official pages.
2. Easy to contribute to, hard to vandalize.
3. Updates reach users within days, without an app update.
4. Every entry says how fresh it is.

---

## 2. Repository

A separate public Git repo: `rackcheck-kb`. Kept apart from the app code so contributors don't need the app's build setup, and so KB releases have their own cadence.

```
rackcheck-kb/
  schema/
    vendor.schema.json
    plugin.schema.json
  vendors/
    fabfilter.json
    xfer-records.json
  plugins/
    fabfilter/
      pro-q-4.json
      pro-l-2.json
    xfer-records/
      serum.json
      serum-2.json
  stock/
    ableton-live.json        # built-in devices per DAW
    fl-studio.json
    logic-pro.json
  aliases/
    name-normalization.json  # suffixes to strip, known renames
  tools/
    validate.py
    build_bundle.py
    link_check.py
  CONTRIBUTING.md
  LICENSE-DATA
```

**One file per entry**, not one big JSON file. This keeps pull requests small and avoids merge conflicts. The build step (section 6) compiles everything into a single bundle for the app.

**Stock device files** list each DAW's built-in devices by their internal names (as seen in project files), so readers can label them `stock` and the report can say "needs Ableton Live Suite" where relevant (e.g. devices only in higher DAW editions).

---

## 3. Data license

Pick before accepting any outside contributions, because it's hard to change later.

**Recommendation: CC0 (public domain dedication) for KB data.** It lets the commercial app ship the data with no attribution complexity, and lets others reuse it, which builds goodwill with the community doing the contributing.

Alternative: CC BY 4.0 (requires attribution in the app's credits). Avoid share-alike licenses (CC BY-SA, ODbL) since they complicate bundling in a commercial product.

Contributors agree via a DCO sign-off (`Signed-off-by:` line in commits) that they have the right to contribute and accept the data license. Document this in `CONTRIBUTING.md`.

---

## 4. Entry rules

### 4.1 Required on every entry
- `last_verified` date.
- `sources`: list of URLs backing the facts (official vendor product page, vendor licensing FAQ, vendor system requirements page). Not stored in the app bundle, only in the repo, for review.

### 4.2 Link rules
- Homepage, manual and support links must be official vendor domains (or the vendor's official store page if that is their only product page).
- No affiliate links, no reseller links, no tracking parameters (strip `utm_*` etc.).
- HTTPS only.

### 4.3 Identity rules
- Plugin IDs (VST3 CID, VST2 unique ID, AU codes, CLAP id, AAX IDs) come only from real evidence: a plugin's own `moduleinfo.json` or `Info.plist`, a crafted fixture, a sandboxed probe result, or aggregated opt-in reports (section 7). Never typed from memory or guessed.
- One plugin entry covers all formats of that plugin. `keys` holds every known ID across formats. That's what lets the resolver say "you have the VST3 of the VST2 this project uses".
- Major versions sold as separate products get separate entries (e.g. Serum and Serum 2), linked with `successor_id`.

### 4.4 Facts that change often
Licensing systems, formats and platforms do change. Example: Joey Sturgis Tones moved new purchases off iLok to its own system in October 2025. So:
- `licensing` can hold more than one value, with an optional `licensing_note` ("iLok for purchases before Oct 2025, vendor account after").
- `status` changes (discontinued, replaced) require a source link.

---

## 5. Contribution flow

1. Contributor opens a PR (template asks: what changed, source links, how IDs were obtained).
2. CI runs:
   - JSON Schema validation
   - ID format checks (CID is 32 hex, AU codes are 4 chars, etc.)
   - Duplicate ID detection across all entries
   - Link check on changed URLs (HTTP status, redirect target stays on vendor domain)
   - Domain check: links match the vendor's `official_domains` list
3. A maintainer reviews sources and merges.
4. Merged changes go out in the next KB release (section 6).

**Issue templates** for non-developers: "Wrong info", "Missing plugin", "Broken link". Maintainers convert these into entries.

**Vendor corrections:** vendors can request changes. Verify the request comes from an email on the vendor's official domain before acting. Vendor requests to be removed from the KB are honored for links and descriptions, but the scanner will still identify their plugins by name (that's factual data the user's own project contains).

---

## 6. Build and release

- `tools/build_bundle.py` compiles all entries into `kb-bundle.json` (minified) plus `kb-manifest.json`:
  ```json
  {
    "kb_version": "2026.09.25.1",
    "schema_version": "1.0.0",
    "min_app_version": "1.0.0",
    "sha256": "...",
    "entries": { "vendors": 412, "plugins": 3890, "stock": 9 },
    "published_at": "2026-09-25T18:00:00Z"
  }
  ```
- Version format: `YYYY.MM.DD.n`.
- The manifest and bundle are signed with an Ed25519 key (minisign or equivalent). The public key is compiled into the app. The private key lives only in the CI secret store, never on a laptop (SPEC-07).
- Published to a static host (GitHub Releases or a CDN). The app checks the manifest at most once a day (SPEC-05 section 6).
- App behavior: download, verify signature and hash, check `min_app_version`, swap in atomically, keep the previous bundle for rollback. On any failure, keep using the current bundle silently and log it.
- The app always ships a bundled KB snapshot so it works fully offline from first launch.

**Cadence:** weekly scheduled release if anything merged, plus on-demand releases for important fixes.

---

## 7. Where new data comes from

In priority order:

1. **Seeding (before first release):** top ~100 vendors and their most-used plugins, entered manually from official sites. Use the fixture-building work (SPEC-06) to capture IDs for the free plugins used in fixtures.
2. **Opt-in unknown plugin reports:** when a user scans a project with an unresolved plugin and has opted in, the app sends only identity fields (format, name, vendor string, IDs, file name without path). Reports are aggregated server-side; any plugin reported by 3+ distinct installs is queued for a maintainer to research and add. Payload and handling defined in SPEC-07.
3. **Installed inventory metadata:** VST3 `moduleinfo.json` Factory Info (vendor, URL) is vendor-declared and a good starting point for new entries, but still needs maintainer review before becoming an official KB link.
4. **Community PRs and issues.**

---

## 8. Keeping it fresh

- **Weekly link check** over all entries. Broken links (4xx/5xx, or redirect off the vendor's domain) open an issue automatically.
- **Staleness:** entries with `last_verified` older than 12 months are listed in a monthly "needs review" issue. The app shows "info may be out of date" for them (SPEC-02 section 7).
- **Vendor watch:** maintainers subscribe to news sources that announce licensing and product changes (KVR news, Bedroom Producers Blog, vendor newsletters) and update affected entries.

---

## 9. Roles

| Role | Can do |
|---|---|
| Contributor | Open PRs and issues |
| Reviewer | Approve PRs in their area (e.g. a vendor they know well) |
| Maintainer | Merge, release, manage signing via CI |

Start with just you as maintainer. Add reviewers once contribution volume justifies it.

---

## 10. Acceptance criteria (KB v1, needed for Phase 2)

- [ ] Repo, schemas, CI validation, link checker running
- [ ] Data license and DCO decided and documented
- [ ] 100 vendors and their main plugins entered with sources
- [ ] Stock device lists for Ableton Live, REAPER (JSFX/Rea* plugins) and DAWproject built-in profiles
- [ ] Signed bundle build and publish working end to end
- [ ] App verifies, installs and rolls back a KB update in testing
