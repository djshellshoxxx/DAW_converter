# SPEC-10: Project readiness warnings

**Status:** implementation in progress  
**Scope:** Phase 2 report warnings listed in SPEC-02 §10.5 and TODO.md.

## 1. Goal

Warn collaborators about dependencies not represented by the installed-plugin
inventory. Each warning must cite project evidence and avoid false certainty.

## 2. Common warning contract

Each warning uses the existing report shape:

    {"code":"EXTERNAL_HARDWARE","severity":"warning","message":"...","related_ids":["t1"]}

- code is stable and machine-readable.
- severity follows section 3.
- message is concise and names the dependency or uncertainty.
- related_ids contains supporting track or plugin IDs; it is empty only when the
  source format provides no stable object ID.
- An absent or unsupported field is not evidence that a dependency is absent.
- Warnings do not change scan results, edit projects, or access the network.

## 3. Warning requirements

| Code | Severity | Emit when | Do not emit when |
|---|---|---|---|
| EXTERNAL_HARDWARE | warning | A reader finds an explicit external hardware insert/device. Relate it to its containing track. | A display name merely contains “hardware,” or the format is not understood. |
| SIDECHAIN_PRESENT | info | A reader finds an explicit sidechain input or routing connection. Relate source/destination track IDs when known. | A compressor exists without an explicit sidechain connection. |
| THIRD_PARTY_CONTENT | info | A plugin record or explicit project reference points to content identified by the KB as third-party content; mark ambiguous references heuristic. | A plugin name alone suggests a preset/sample product. Never inspect opaque plugin state. |
| DAW_VERSION_NEWER | warning | Saved project version and user-provided installed DAW version are known, parseable, comparable, and installed version is older. | Installed version unavailable, a version unparseable, or version namespaces incomparable. |

## 4. Initial implementation slice

The first supported source is Ableton Live. Its ExternalInstrument and
ExternalAudioEffect device tags are explicit hardware evidence. The reader records
the containing track ID in ScanResult.external_hardware_tracks; the report emits
one EXTERNAL_HARDWARE warning with those track IDs. Detection inside nested racks
still points to the containing track. Other DAWs remain unsupported until their
reader provides equally explicit evidence.

This slice does not infer sidechains, third-party content, or installed DAW
versions. Those require the evidence sources in section 3 and separate delivery.

## 5. Acceptance criteria

1. Ableton external hardware devices produce one warning with the containing track
   ID in related_ids.
2. Ableton projects without these devices produce no such warning.
3. A device nested in a rack still identifies the outer track.
4. A similarly named ordinary third-party plugin does not trigger the warning.
5. SIDECHAIN_PRESENT, THIRD_PARTY_CONTENT, and DAW_VERSION_NEWER are not emitted
   without the evidence specified in section 3.
6. Existing report schema and all other warning behavior remain stable.
