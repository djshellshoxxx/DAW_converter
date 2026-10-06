# SPEC-11: Reader resource limits

**Status:** implementation in progress  
**Scope:** close the 60-second reader-timeout requirement in SPEC-06 and untrusted
input resource-exhaustion risks in SPEC-07.

## 1. Goal

Bound time and memory consumed by reading a project and return a structured scan
failure without leaving workers or temporary files behind.

## 2. Requirements

- A reader has a configurable hard wall-clock deadline, default 60 seconds.
- The reader runs in a spawned child process that is terminated and reaped at the
  deadline; timeout errors use the stable READER_TIMEOUT code.
- Serialized reader results are capped at 64 MiB.
- The deadline stops CPU work; a caller-side timeout that leaves the reader running
  is insufficient.
- A timeout produces the existing structured error shape, identifies the input
  path, and allows later queued scans to run.
- Worker processes do not write to or mutate project files. Extracted temporary
  input is cleaned on success, parser error, cancellation, and timeout.
- IPC results are restricted to the serializable scan model and bounded in size.
  Tracebacks and arbitrary exception payloads are not returned to the GUI.
- Cancellation and shutdown reap workers within a bounded grace period.
- Platform behavior is tested using the process start method used by packaged
  Windows, macOS, and Linux builds.

## 3. Acceptance criteria

1. A deliberately blocking reader is terminated at the configured deadline.
2. A scan after timeout succeeds, proving the service remains usable.
3. Cancellation and shutdown leave no child processes running.
4. Tests cover worker exceptions, malformed IPC, and temporary archive cleanup.
5. CI exercises timeout tests on Linux, Windows, and macOS.

## 4. Design constraint

Use a killable process boundary rather than Python thread cancellation. Keep the
public start_scan/cancel_job GUI bridge contract stable unless implementation
demonstrates a necessary backward-compatible extension.
