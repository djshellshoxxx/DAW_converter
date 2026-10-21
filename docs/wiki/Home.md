# Rackcheck Wiki

Rackcheck scans DAW project files and reports every plugin, track, and media file they use,
and whether those plugins are installed on the machine.

- [User Guide](User-Guide) - install, CLI and GUI usage, reading the report
- [Developer Guide](Developer-Guide) - setup, build, tests, and how to extend readers
- [Architecture and Design Rationale](Architecture-and-Design-Rationale) - why the code is shaped this way
- [Codebase Map](Codebase-Map) - where to find what

Status: 0.1.0-alpha. Readers for REAPER, Ableton Live and DAWproject are implemented; the
other formats are detected only. Real-DAW validation is still pending.

The authoritative requirements are in `specs/` in the repository; `docs/spec-coverage.md`
tracks what is implemented and verified.
