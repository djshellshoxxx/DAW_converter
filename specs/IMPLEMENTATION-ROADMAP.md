# Implementation roadmap

This map turns open items in TODO.md and docs/spec-coverage.md into ordered
capabilities. Detailed product and release requirements remain in their existing
specs; this file records dependencies and what can be verified locally.

## Capability map

| Capability | Spec | State | Next action |
|---|---|---|---|
| Project readiness warnings | SPEC-02 §10.5; SPEC-10 | In progress | Implement explicit evidence first; start with Ableton external hardware. |
| Reader resource limits | SPEC-07 §1; SPEC-11 | In progress | Hard deadline and bounded reader result implemented; finish cleanup/IPC edge tests and cross-platform CI. |
| XML and archive safety | SPEC-02 §2; SPEC-07 §1 | Implemented; coverage reconciliation needed | Verify adversarial cases against current parsers and update evidence. |
| Knowledge base | SPEC-04 | Seed data exists; verification/update pending | Verify records; updates need signing key and distribution endpoint. |
| Packaging and signing | SPEC-05 | Pending | Build locally; signing acceptance needs platform certificates. |
| Real fixtures and GUI host validation | SPEC-01 §6; SPEC-03; SPEC-06 | Blocked on external environments | Capture DAW-saved fixtures and exercise GUI on Windows/macOS. |
| Collaboration, compare, library scan | SPEC-08 | Specified; not implemented | Phase 6 after core scan/report behavior stabilizes. |
| Additional DAW readers | SPEC-02 §§4.4–4.9 | Specified; not implemented | Separate reader projects with DAW-saved fixtures. |
| Privacy controls and HTML export | SPEC-03; SPEC-07; DECISIONS.md | Deferred / pending decision | Keep v1 scope; spec if promoted. |

## Delivery order

1. Implement precisely detectable readiness warnings; label heuristic evidence
   honestly (SPEC-10).
2. Close the reader timeout gap and reconcile security coverage (SPEC-11).
3. Expand verified KB data and complete packaging that needs no secrets.
4. Run GUI and real-fixture acceptance when the required hosts and certificates
   are available.
5. Start the already-specified Phase 3 readers and Phase 6 collaboration work as
   separate, reviewable changes.

## Evidence rules

- Implemented means code plus an automated test.
- Verified means acceptance in the environment named by the relevant spec.
- Blocked is reserved for work requiring an unavailable DAW, certificate, or
  legal review; it must not hide tasks that can be done locally.
- Existing specs are not copied here. New specs are added only where current
  requirements lack an implementable contract.
