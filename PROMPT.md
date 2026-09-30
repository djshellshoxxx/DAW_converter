# Autonomous build instructions

You are working unattended in this project's root directory. Follow `CLAUDE.md` and all applicable specifications. The user is not available during this run. Make routine engineering and design decisions yourself and record material choices in `DECISIONS.md`. Do not treat a missing answer as permission to omit a requirement.

## Start of every iteration

1. Read `CLAUDE.md`, this file, `TODO.md`, `DECISIONS.md`, and `docs/spec-coverage.md` if they exist. Read only project files, not unrelated global files.
2. Run `rg --files specs -g '*.md'` to inventory **every** Markdown specification recursively, even if the master prompt does not mention it. If `rg` is unavailable, use an equivalent recursive file listing. If `specs/` is missing or empty, record that as a blocker; do not signal completion.
3. Compare the inventory with the previous iteration. Read every new or changed spec, and read existing specs as needed to implement or verify their requirements. The first iteration must read **every** inventoried spec in full. Preserve the precedence rules in `CLAUDE.md` and the master prompt. Record any unresolved contradiction in `DECISIONS.md`; resolve it where possible instead of guessing silently.
4. Maintain `docs/spec-coverage.md` with one row per actionable requirement: stable ID, source file and section, acceptance criterion, implementation location, verification method and evidence, and status (`pending`, `in progress`, `verified`, or `blocked`). Group related atomic requirements only if one implementation and one verification genuinely cover them all. A class name, UI mockup, or passing build alone does not verify audio behavior.
5. Update `TODO.md` to show the next executable work, current blockers, and completed work. Pick the highest-priority unverified requirement or release gate.

## Working rules

1. Implement working functionality, not placeholders, dummy UI controls, TODO comments, silent stubs, or documentation that claims a feature exists when it does not.
2. Work in small coherent steps. After each meaningful step, build, run the relevant tests, fix failures, update spec coverage and `TODO.md`, and commit the verified change with a clear message. Do not commit failing code as complete.
3. Keep the engine, GUI, parameter automation, preset state, routing, export, and documentation consistent. Verify the actual connection between controls and sound. Preserve the physical-realism constraints and the two-source limit.
4. If a tool, dependency, host, reference recording, or test environment is missing, try a reasonable local workaround. If it remains unavailable, mark affected requirements `blocked`, record exactly what is missing and how to run the verification elsewhere, and continue independent work. Do not relabel a blocked requirement as verified or silently narrow the specification.
5. If a spec is added, removed, or modified during development, inventory `specs/` again and reconcile `docs/spec-coverage.md`. Apply documented precedence; never rely exclusively on the master prompt's list of filenames.
6. Maintain reproducible build and test commands in project documentation. Do not invent test results, screenshots, DAW validation, audio measurements, or listening observations.
7. Save an end-of-iteration note in `TODO.md` describing what changed, commands and results, remaining work, and the next action. This is the handoff to the next iteration.

## Definition of done

Do **not** emit the completion promise until **all** of these are true:

1. Run a fresh recursive inventory of `specs/**/*.md`. Every file and every actionable requirement appears in `docs/spec-coverage.md`, including specifications added after work began. There are zero required rows marked `pending`, `in progress`, or `blocked`. There are no unexplained omissions or conflicting requirements.
2. Every row marked `verified` has a real implementation location and concrete evidence: test name and output, build command and result, host validation, inspection evidence, or documented manual acceptance result appropriate to the requirement. Verify source behavior, GUI-to-engine wiring, parameter automation, two-source combinations, signal routing, presets, export, and release requirements, not just compilation.
3. The project builds in the required release configuration with zero errors. Relevant automated tests, plugin validation, and packaging checks pass. Fix failures rather than hiding or skipping them.
4. The VST3 loads and works in at least one actual DAW on the target platform, and the required audio, GUI, routing, state-reload, and export scenarios have been exercised. If the target host or machine is unavailable, this gate is unverified: document it and do **not** claim commercial readiness or emit the promise.
5. Realism and listening claims have the evidence required by the specs. If controlled reference recordings or human listening checks are required for a claimed release gate and cannot be performed, record the outstanding gate rather than claiming it passed.
6. `TODO.md` contains no remaining required work. `DECISIONS.md`, test results, coverage table, installation instructions, and release notes accurately describe what was built and verified. There is no unexplained critical defect.

## Final audit and completion signal

Before completion, independently re-read `CLAUDE.md`, this file, and the final spec inventory. Reconcile the coverage table against the files and actual implementation; run final build and verification commands. Treat any existing `.ralph-done` from a previous run as stale, never as evidence of current success. Do not create or retain `.ralph-done` while any required gate remains open.

**Only when every definition-of-done item is genuinely satisfied:**

1. Create or replace an empty `.ralph-done` file in the repository root.
2. Commit the final verified state if git is available.
3. Output exactly: `<promise>COMPLETE</promise>`.

Never output the promise merely to escape the loop. If the iteration limit is reached or a required gate cannot be verified, leave the promise absent, keep `TODO.md` and `docs/spec-coverage.md` accurate, and report the precise remaining work.