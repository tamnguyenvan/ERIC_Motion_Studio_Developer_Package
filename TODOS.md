# ERIC Motion Studio Refactor TODOs

## Milestone 0 — Baseline and Safety

- [x] Record the current commit, Python 3.11, dependency versions, and supported
      launch commands.
- [x] Treat `codebase/ERIC-Gesture-Lab/eric_motion_studio.py` as the authoritative
      legacy entry point; label the stale `.command` launcher as non-authoritative.
- [x] Capture current `--self-test` and command-audit outcomes as regression
      fixtures with concise, machine-checkable output.
- [x] Add characterization tests for motion creation, editing, playback, file
      schemas, gesture save/load, viewer state, and BrainOS export.
- [x] Inventory every tracked and untracked artifact with path, hash, owner,
      purpose, and keep/archive/remove decision.
- [x] Specifically compare the `.backup` source, numbered live-pose files, ad hoc
      tests, screenshot, logs, cache files, and repair inventory text files.
- [x] Update `.gitignore` for generated state, logs, caches, screenshots, local
      environments, and audit output where appropriate.
- [x] Confirm user-owned working-tree changes before any cleanup.
- [x] Quality gate: legacy entry point and headless baseline tests pass unchanged.

## Milestone 1 — Standard Project Skeleton

- [x] Add `pyproject.toml` with pinned runtime dependencies, package metadata,
      console script, Ruff, and pytest configuration.
- [x] Create `src/eric_motion_studio/`, `resources/`, and `tests/`.
- [x] Add `python -m eric_motion_studio` and one console-script entry point.
- [x] Implement typed settings with package-relative defaults plus CLI/environment
      overrides for model, data, export, log, and runtime-state paths.
- [x] Store mutable user data outside packaged resources.
- [x] Remove Qt, MuJoCo, and UI imports from package import-time execution.
- [x] Add structured logging with bounded default verbosity.
- [x] Quality gate: clean install, import, `--help`, and headless startup checks pass.

## Milestone 2 — Pure Domain and File Formats

- [ ] Extract `Keyframe`, motion, gesture, joint, and playback value objects.
- [ ] Extract interpolation, cloning, timing, clamping, and trajectory operations.
- [ ] Extract animation, pose, gesture, and export serializers/repositories.
- [ ] Define and validate versioned JSON schemas at repository boundaries.
- [ ] Preserve existing files with golden round-trip tests.
- [ ] Centralize joint names, limits, groups, and model metadata behind a model
      profile rather than duplicating constants in app and viewer.
- [ ] Quality gate: pure unit tests pass without PySide6 or MuJoCo imports.

## Milestone 3 — Extensible Gesture Language

- [ ] Define a validated `GestureDefinition` schema containing canonical ID,
      aliases, supported slots, generator ID, defaults, tags, and constraints.
- [ ] Move synonyms and canonical command inventory into gesture definition data.
- [ ] Implement normalization and token/phrase matching as isolated components.
- [ ] Implement typed slot extraction for side, direction, speed, intensity, hold,
      sequence, and neutral-return modifiers.
- [ ] Implement an explicit resolution result: success, ambiguity, unsupported
      gesture, or invalid slot.
- [ ] Create a generator protocol and registry with no parser-to-generator
      condition chain.
- [ ] Port wave, talking idle, thinking, scratch-head, arm, presentation, and
      structured full-body generators incrementally.
- [ ] Store reusable poses/stages as validated data; keep only algorithms in code.
- [ ] Run joint-limit, amplitude, trajectory, balance, collision, and semantic
      validators after compilation.
- [ ] Add parameterized tests proving every alias resolves to its canonical gesture.
- [ ] Add tests showing a synonym can be added without changing Python.
- [ ] Add ambiguity, unknown-command, malformed-definition, and compound-command
      tests.
- [ ] Quality gate: legacy command inventory has equal or better behavior and all
      generator outputs remain deterministic.

## Milestone 4 — PySide6 UI Split

- [ ] Extract the main window shell from application state and use cases.
- [ ] Split motion metadata, gesture library, joint editor, keyframe editor,
      playback controls, and status panels into focused widgets.
- [ ] Add controllers/services for document lifecycle, undo/redo, playback,
      gesture authoring, export, and unsaved-change handling.
- [ ] Replace direct file/process access in widgets with injected interfaces.
- [ ] Preserve shortcuts, signals, selection behavior, and visible status messages.
- [ ] Add unit tests for controllers and Qt tests for critical user flows.
- [ ] Quality gate: UI smoke test and critical interaction tests pass.

## Milestone 5 — MuJoCo, Viewer, and Runtime I/O

- [ ] Extract model loading, bindings, neutral state, simulation mode, and safety
      checks into a MuJoCo adapter.
- [ ] Extract viewer state serialization and atomic file IPC.
- [ ] Make the viewer a package entry point using shared configuration/model data.
- [ ] Replace hardcoded interpreter and viewer paths with the active interpreter
      and injected process-launch settings.
- [ ] Handle viewer startup, shutdown, crash, stale state, and malformed state
      explicitly.
- [ ] Add headless integration tests for model load and pose application.
- [ ] Quality gate: app/viewer integration passes in `.venv` and manual MuJoCo
      playback matches the legacy baseline.

## Milestone 6 — Cutover

- [ ] Copy required built-in resources into the active resource layout without
      importing or writing into `codebase/`.
- [ ] Update developer documentation and supported platform launchers to invoke
      only the new package entry point.
- [ ] Run format, lint, unit, integration, headless self-test, and command audit.
- [ ] Run manual regression checks for authoring, playback, saved gestures, file
      compatibility, exports, and viewer synchronization.
- [ ] Verify the new application has no absolute paths and no runtime dependency on
      the legacy tree.
- [ ] Mark `codebase/` clearly as read-only legacy backup.
- [ ] Quality gate: all tests and parity checklist pass before declaring cutover.

## Milestone 7 — Active-Tree Cleanup and Release

- [ ] Remove verified duplicates and generated artifacts from the active project;
      do not alter the preserved `codebase/` backup.
- [ ] Ensure only one supported app entry point and one supported viewer entry point
      remain.
- [ ] Add architecture, gesture-authoring, file-format, testing, and release docs.
- [ ] Add CI for formatting, linting, tests, and headless self-test.
- [ ] Produce an initial versioned release and rollback instructions.
- [ ] Quality gate: fresh-clone setup and launch succeed using only documented steps.
