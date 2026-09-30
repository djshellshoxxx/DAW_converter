# SPEC-07: Security, Privacy and Legal

**Project:** Plugin Dependency Scanner (working name: "Rackcheck")
**Related:** SPEC-01 section 4 (license policy), SPEC-04 (KB signing), SPEC-05 (code signing)
**Status:** Draft v1, September 2026

**Not legal advice.** This spec lists what needs deciding and documenting. Have a lawyer review the legal sections, the EULA and the privacy policy before any paid release.

---

## 1. Threat model

The app opens files from strangers (collaborators' projects, downloaded templates) and loads third-party plugin binaries. Treat both as hostile.

| Threat | Where | Mitigation |
|---|---|---|
| Zip bomb | .dawproject, .song, zipped uploads | Limit total uncompressed size (default 4 GB), entry count (default 100k), compression ratio (default 100:1); stream extraction; abort on limit |
| Zip slip (path traversal) | Any zip extraction | Reject entries with absolute paths, `..`, drive letters, or symlinks; extract only into a fresh temp folder; prefer reading entries in memory without extracting |
| XML attacks (billion laughs, external entities) | .als, .song, .dawproject | Use a hardened parser (Python: `defusedxml`); disable DTDs and external entities |
| Gzip bomb | .als | Same size limits while decompressing |
| Malformed binaries causing hangs or huge allocations | .flp, .cpr, ProjectData, .ptx | Bounds-check every length field against remaining bytes; per-reader time budget (60 s default); memory cap |
| Malicious plugin binary during inventory probe | Installed plugins | Metadata files first; probe only in a separate child process with timeout, no network access where the OS allows, lowest practical privileges; never probe plugins found inside project folders or downloads, only in plugin install folders |
| Tampered KB or update manifest | Network | Ed25519 signatures verified against keys compiled into the app; HTTPS; reject on failure (SPEC-04, SPEC-05) |
| Malicious link in KB or report JSON | Links opened from the UI | Engine `open_url` allows `https://` (and `http://`) only; KB CI enforces official vendor domains; reports opened from other people show a domain preview before opening links |
| Web front end injection | Plugin/track names rendered in HTML | Render all project-derived text as text, never HTML; strict Content Security Policy; no remote scripts; no `eval` |
| Bridge abuse | pywebview js_api | Expose only the SPEC-03 section 7 methods; validate every argument; paths from JS are checked against what the user actually chose |
| Symlink tricks in project folders | Media scanning | Don't follow symlinks outside the project folder when computing sizes or hashes; report them instead |
| Opening a shared report JSON | Reports from others | Validate against schema before loading; treat all strings as untrusted text |

**Read-only guarantee** (SPEC-01 P3): enforced in code by opening project files with read-only flags and never passing project paths to any write API. Tested in CI.

---

## 2. Data handling

### 2.1 What stays local (always)
- Project files and their contents
- Media files and hashes
- Full reports, the plugin inventory, recent scans, settings, logs

### 2.2 What goes over the network
| Traffic | When | Content | Default |
|---|---|---|---|
| KB update check | Max once/day | Request for manifest; standard HTTP headers | On (can be turned off) |
| App update check | Max once/day | Request for manifest; app version and OS in the URL or header | On (can be turned off) |
| Unknown plugin report | After a scan, if enabled | Format, plugin name, vendor string, IDs, binary file name (no path), DAW name and version. No project name, track names, usernames, or file paths | **Off** |
| Crash report | On crash, if enabled | Stack trace, app/engine/KB versions, OS. Paths scrubbed | **Off** |
| Support bundle | Only when the user creates and sends it themselves | Logs, versions, report JSON (redacted); project file only via separate checkbox | Manual |

- Opt-in toggles show the exact payload example ("See what gets sent").
- No analytics, no advertising IDs, no third-party trackers in the app.
- Server side: unknown-plugin reports store no IP addresses beyond what's needed for rate limiting (drop after 24 h). Crash reports kept 90 days.

### 2.3 Hosting
Prefer hosting the KB, update manifests and report endpoints with a Canadian or EU provider. Keeps data residency simple for Canadian and EU privacy rules and fits users who care about where their data goes.

---

## 3. Privacy compliance

Applies once the app collects anything from users (opt-in reports, crash reports, purchase info).

- **Canada:** PIPEDA for commercial activity; Quebec Law 25 has stricter requirements (e.g. privacy officer designation, privacy-by-default) for Quebec users.
- **EU/UK users:** GDPR / UK GDPR (lawful basis = consent for opt-in reports; data subject rights; processor agreements with hosting and payment providers).
- **US:** state laws (e.g. California) mostly triggered by size thresholds; keep collection minimal so obligations stay minimal.

Deliverables:
- [ ] Privacy policy in plain language, linked from the website, installer and Settings
- [ ] Designated privacy contact (you, at first)
- [ ] Record of what data is collected, why, where it's stored, and how long
- [ ] Process for access and deletion requests
- [ ] Data processing agreements with any service that handles user data (hosting, payment provider, email)

---

## 4. Legal

### 4.1 Open source compliance
- License ledger and A/B/C classes per SPEC-01 section 4.
- `THIRD_PARTY_NOTICES` shipped in the app (Settings > About > Licenses) and regenerated each release (SPEC-05 checklist).
- LGPL libraries (e.g. ptformat): shipped as a separately replaceable library; source of our modifications published; notice explains how to replace it.
- CI check: fail the build if a dependency's license isn't in the ledger.

### 4.2 Reverse engineering
- Readers are built for interoperability (reading the user's own files). Canada's Copyright Act and the US DMCA both contain interoperability provisions; get a lawyer to confirm they cover each binary reader, especially the Pro Tools XOR decryption (SPEC-02 section 4.8).
- Clean-room process for GPL references (SPEC-01 section 4) with notes kept as a record.
- Never ship or distribute any DAW's own code, SDK headers under restrictive licenses, or plugin binaries.
- Check the EULAs of DAWs used to create fixtures for clauses about reverse engineering; note any concerns for the lawyer review.

### 4.3 Trademarks
- DAW and plugin names are used only to identify compatibility and what a project contains (nominative use). Examples: "Reads Ableton Live projects", "Serum by Xfer Records".
- **No DAW or vendor logos** in the app or on the website without written permission. Use text names and generic icons (SPEC-03 home screen uses names, not logos).
- Standard disclaimer in About and on the website: "Not affiliated with or endorsed by Ableton, Apple, Avid, Bitwig, Cockos, Fender/PreSonus, Image-Line, Steinberg or any plugin vendor. All trademarks belong to their owners."

### 4.4 Knowledge base content
- Facts only (names, links, formats, licensing systems). No copied marketing text, product images, or screenshots from vendor sites.
- Data license and contributor sign-off per SPEC-04 section 3.

### 4.5 User-facing documents
- [ ] EULA (license grant, no warranty, limitation of liability, especially "we don't guarantee a project will open", no reverse engineering of our app, termination)
- [ ] Privacy policy (section 3)
- [ ] Terms of sale / refund policy (SPEC-09)
- [ ] Beta participation and project donation consent terms (SPEC-06 section 2.5)

### 4.6 Business structure
Decide early whether to sell as a sole proprietor or incorporate (liability, taxes, and how the name shows on code signing certificates: SPEC-05). An accountant can advise on GST/HST registration thresholds; a merchant-of-record payment provider (SPEC-09) can handle sales tax collection across countries.

---

## 5. Secrets and keys

| Secret | Stored | Rotation |
|---|---|---|
| Apple signing certs and notary API key | CI secret store | On expiry or compromise |
| Azure Artifact Signing credentials | CI secret store (service principal) | Per Azure policy |
| Update manifest signing key (Ed25519) | CI secret store, offline backup in a password manager | Only on compromise; app supports two public keys so a new key can be introduced one release before the old one is retired |
| KB signing key (Ed25519) | Same as above, separate key | Same |
| Server API credentials | Server secret store | Yearly |

Enable 2FA on every account involved (GitHub, Apple, Azure, domain registrar, hosting, payment provider).

---

## 6. Security process

- `SECURITY.md` with a contact address for reporting vulnerabilities; acknowledge within 5 days.
- Dependency updates checked weekly (Dependabot or equivalent); security fixes released as patches.
- Fuzzing runs nightly (SPEC-06).
- Security review of every new reader before it leaves beta: limits enforced, bounds checks present, fuzz clean.
