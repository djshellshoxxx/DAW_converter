# SPEC-05: Packaging, Signing and Updates

**Project:** Plugin Dependency Scanner (working name: "Rackcheck")
**Related:** SPEC-01 section 3 (stack), SPEC-04 section 6 (KB updates), SPEC-07 (security)
**Status:** Draft v1, September 2026

How the app gets built, signed, installed and updated on Windows and macOS. For a tool aimed at non-technical users this is not optional polish: an unsigned app on macOS gets blocked, and an unsigned installer on Windows shows a blue SmartScreen warning that makes people think it's a virus.

**Verify every tool name, price and requirement below against the vendor's current docs at build time.** Signing rules change often.

---

## 1. Targets

| Platform | Minimum | Architectures | Package |
|---|---|---|---|
| Windows | Windows 10 22H2, Windows 11 | x64 (arm64 later) | Signed installer (.exe), optional .msi later |
| macOS | macOS 13 | arm64 and x86_64 (universal2 or two builds) | Signed, notarized .dmg containing the .app |

---

## 2. Build tooling (Python stack)

- **PyInstaller** in `--onedir` mode (not `--onefile`). Onedir starts faster (no unpacking to temp on every launch) and triggers fewer antivirus false positives.
- **pywebview** backends: WebView2 on Windows (Edge runtime, present on current Windows 10/11; ship the Evergreen bootstrapper in the installer as a fallback), WKWebView on macOS (built in).
- The plugin probe helper (SPEC-02 section 6) is a separate executable in the same bundle, so it can run as a child process and be signed like everything else.
- Front-end assets built once and bundled; no network loading.
- **Antivirus false positives:** PyInstaller's stock bootloader is often flagged because malware uses it too. Mitigations: onedir mode, build the bootloader from source in CI, sign everything, and submit new releases to Microsoft's malware analysis portal if flagged.

If Phase 0 chose the Rust/Tauri stack instead, Tauri has its own bundler and updater; sections 3 to 6 still apply in principle.

---

## 3. macOS signing and notarization

**Requirements:**
- Apple Developer Program membership (individual is fine to start; an organization account shows a company name instead of a personal name to users).
- A **Developer ID Application** certificate (for the app) and **Developer ID Installer** certificate only if shipping a .pkg.

**Steps (in CI):**
1. Enable the **hardened runtime** on every executable.
2. Sign **inside out**: every .dylib, .so, framework and helper executable first, then the main executable, then the .app bundle. Don't rely on `--deep`; sign each item explicitly.
3. Entitlements: start with none. Add only what testing proves is required (Python and some libraries may need specific hardened-runtime exceptions; document each one and why in `packaging/entitlements.md`).
4. Build the .dmg, sign it.
5. Submit with `xcrun notarytool` using an App Store Connect API key (stored as CI secret).
6. Staple the ticket to the .dmg (`xcrun stapler staple`) so it validates offline.
7. Verify: `spctl --assess` and `codesign --verify --strict` on a clean machine.

**Not the Mac App Store.** App Store sandboxing would block reading plugin folders across the system and running the probe helper. Distribute directly from the website.

---

## 4. Windows signing

**Recommended: Azure Artifact Signing** (Microsoft's managed service, formerly called Trusted Signing).
- Available to individual developers in the US and Canada, and to organizations in more regions. Check current eligibility.
- Pricing at time of writing starts around USD 9.99/month for the basic tier. Needs a paid Azure subscription (free/trial subscriptions not supported).
- No hardware token to buy or lose; certificates are short-lived and managed by Microsoft. Works with standard SignTool in CI.
- Identity validation is done once in the Azure portal; allow up to a couple of weeks.

**Alternative:** a traditional OV code signing certificate from a CA. Since mid-2023 industry rules require these keys to live on a hardware token or HSM, which makes CI signing awkward and costs more. Only use this if Artifact Signing eligibility is a problem.

**What to sign:** every .exe and .dll we ship (including the probe helper), then the installer itself. Always timestamp signatures so they stay valid after the signing certificate expires.

**SmartScreen:** signing removes the "unknown publisher" warning, but SmartScreen reputation still builds over time with download volume. Expect some warnings on the very first releases. Don't change signing identity between releases, since reputation is tied to it.

**Installer:** Inno Setup (simple, well known) producing a signed setup .exe.
- Default: per-user install to `%LOCALAPPDATA%\Programs\Rackcheck`, no admin prompt.
- Option: all-users install to `Program Files` (admin).
- Start menu shortcut, optional desktop shortcut, file association for `.rackcheck-*` files (SPEC-08).
- Clean uninstall; asks whether to also remove settings and cache.

---

## 5. CI release pipeline

GitHub Actions (hosted macOS and Windows runners are needed; self-hosted CI would need a Mac).

```
tag v1.2.0
  -> run full test suite (SPEC-06)
  -> build Windows (x64)      -> sign files -> build installer -> sign installer
  -> build macOS (arm64, x86_64 or universal2) -> sign -> dmg -> notarize -> staple
  -> smoke test each artifact on a clean VM/runner (launch, scan a fixture, export)
  -> generate update manifest (section 6), sign it
  -> publish: GitHub Release (or own download host) + website download links
  -> publish release notes
```

**Secrets** (CI secret store only, never in the repo or on a laptop): Apple API key and certificates, Azure service principal for Artifact Signing, update-manifest signing key, KB signing key (SPEC-04).

**Versioning:** SemVer. `major.minor.patch`. Engine, schema and KB versions are tracked separately and shown in Settings > About.

---

## 6. Updates

### 6.1 App updates

**Phase 2 (v1): notify only.**
- On launch (max once per day, skippable in Settings), fetch a signed `update-manifest.json`:
  ```json
  {
    "channel": "stable",
    "latest": "1.2.0",
    "min_supported": "1.0.0",
    "released_at": "2026-10-01T18:00:00Z",
    "notes_url": "https://.../releases/1.2.0",
    "downloads": {
      "windows-x64": { "url": "...", "sha256": "..." },
      "macos-universal": { "url": "...", "sha256": "..." }
    },
    "signature": "..."
  }
  ```
- Verify the signature against the public key compiled into the app. If newer, show a non-blocking banner: "Version 1.2.0 is available" with "What's new" and "Download".

**Later: in-app update.** Download in background, verify hash and signature, install on next launch. Evaluate a maintained updater framework before writing one (for PyInstaller apps, look at TUF-based options such as `tufup`; check its license and maintenance status). Never auto-install without user consent.

**Channels:** `stable` and `beta` (opt-in in Settings).

### 6.2 KB updates
Separate from app updates, defined in SPEC-04 section 6. Silent, signed, daily check, works without an app update.

### 6.3 Offline
All update checks fail silently when offline. The app must never require a network connection to launch or scan.

---

## 7. Release checklist

- [ ] All tests green, fixture regression green (SPEC-06)
- [ ] Version numbers bumped (app, engine, schema if changed)
- [ ] `THIRD_PARTY_NOTICES` regenerated and license ledger reviewed (SPEC-07)
- [ ] Windows: all binaries and installer signed and timestamped; installs and uninstalls cleanly on a fresh VM without admin
- [ ] macOS: notarized and stapled; opens on a fresh VM with no Gatekeeper warning, on both Apple Silicon and Intel
- [ ] Smoke test: launch, first-run inventory, scan one fixture per supported format, export JSON and CSV
- [ ] Update manifest signed and published; previous version sees the update banner
- [ ] Release notes written in plain language
- [ ] Website download links updated
