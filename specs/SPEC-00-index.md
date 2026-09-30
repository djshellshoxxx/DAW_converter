# Rackcheck Spec Index

Working name "Rackcheck": a desktop app that scans DAW project files and lists every plugin used, with links and key info.

| Spec | Covers |
|---|---|
| SPEC-01-build-order.md | Product goals, design principles, architecture, license policy, research protocol, fixture strategy, build phases, report contents, risks |
| SPEC-02-file-format-readers.md | Format detection, data model, per-DAW readers and prior work, identity resolution, installed plugin inventory, KB schema, detectable data catalog, JSON/CSV export formats, warning codes |
| SPEC-03-gui-and-engine-integration.md | Screens, user flows, error states, export flow, engine API, jobs and progress, caching, accessibility |
| SPEC-04-knowledge-base-operations.md | KB repo, data license, entry rules, contributions, signed releases, data sources, freshness |
| SPEC-05-packaging-signing-updates.md | PyInstaller builds, macOS notarization, Windows signing, installers, CI release pipeline, app updates |
| SPEC-06-testing-and-qa.md | Test layers, fixture library, robustness rules, performance targets, CI, beta program, DAW update process |
| SPEC-07-security-privacy-legal.md | Threat model, data handling, privacy law, open source compliance, reverse engineering, trademarks, secrets |
| SPEC-08-collaboration-formats.md | Inventory, requirements and send pack formats, compare logic, versioning |
| SPEC-09-business-model.md | Model options, free/Pro split, app licensing, payments, distribution, marketing, costs, open decisions |

Suggested reading order for a new build session: 00, 01, 02, 03, then the others as each phase needs them.
