# ERIC Motion Studio

ERIC Motion Studio is a simulation-only motion authoring application for the
Unitree G1 humanoid model. It provides a PySide6 editor, data-driven gesture
generation, versioned JSON motion files, local BrainOS-format exports, and a
MuJoCo viewer.

It does not connect to physical ERIC hardware, DDS, BrainOS, or SDK2.

## Requirements

- Python 3.11
- macOS or Linux
- A graphical desktop for the authoring UI and MuJoCo viewer

## Install

From the repository root:

```text
python3.11 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

On Ubuntu CI or a minimal Linux installation, install the Qt runtime library
used by PySide6:

```text
sudo apt-get install libegl1
```

## Run

Launch the authoring application:

```text
.venv/bin/eric-motion-studio
```

Equivalent module invocation:

```text
.venv/bin/python -m eric_motion_studio
```

On macOS, use `launchers/macos/ERIC Motion Studio.command` for a double-click
launch. The launcher resolves the project and virtual environment relative to
its own location. PySide6 startup validates the bundled Cocoa plugin and clears
stale Qt and dynamic-loader overrides. The viewer resolves `mjpython` from the
active environment; no machine-specific project path is required.

The viewer is normally started by the authoring application. Run its diagnostic
entry point directly with:

```text
.venv/bin/eric-motion-studio-viewer --self-test
```

## Validation

Run the complete local quality gate:

```text
.venv/bin/ruff format --check src tests tools
.venv/bin/ruff check src tests tools
QT_QPA_PLATFORM=offscreen .venv/bin/pytest
.venv/bin/eric-motion-studio --headless --no-console-log
.venv/bin/eric-motion-studio --self-test
.venv/bin/eric-motion-studio --audit-commands
.venv/bin/python tools/cutover_audit.py
.venv/bin/python tools/release_audit.py
.venv/bin/eric-motion-studio-viewer --self-test
```

Audit one natural-language gesture:

```text
.venv/bin/eric-motion-studio --audit-command "wave right hand"
```

GitHub Actions runs the same formatting, lint, test, headless, viewer, and
release checks.

## Runtime data and configuration

Packaged resources are immutable and live under
`src/eric_motion_studio/resources/`. Built-in motions are generated from
definitions and stages. User motions, poses, compatibility artifacts, exports,
logs, and viewer IPC state are stored in platform user-data/state directories
by default.

Writable data is separated into `motions/`, `poses/`, `compiled/`, and
`exports/`. On Linux the default root is
`~/.local/share/eric-motion-studio/`; on macOS it is
`~/Library/Application Support/ERIC Motion Studio/`.

Built-ins are read-only. Duplicate one to create and immediately open a custom
motion, then use the normal Save or Delete commands. Playback derives dense
frames automatically; there is no approval workflow.

Override paths with these CLI options or matching environment variables:

- `--model-path` / `ERIC_MOTION_STUDIO_MODEL_PATH`
- `--data-dir` / `ERIC_MOTION_STUDIO_DATA_DIR`
- `--export-dir` / `ERIC_MOTION_STUDIO_EXPORT_DIR`
- `--log-path` / `ERIC_MOTION_STUDIO_LOG_PATH`
- `--runtime-state-path` / `ERIC_MOTION_STUDIO_RUNTIME_STATE_PATH`

## Project layout

```text
src/eric_motion_studio/       application package
src/eric_motion_studio/resources/  definitions, stages, models, schemas, icons
tests/                         unit, integration, Qt, and parity tests
tools/                         cutover and release audits
docs/                          architecture and operator documentation
launchers/macos/               supported macOS launcher
codebase/                      read-only historical legacy backup
```

The supported console scripts are `eric-motion-studio` and
`eric-motion-studio-viewer`. The active package never imports from or writes to
`codebase/`.

## Gesture command documentation

- [Gesture command framework](docs/gesture-command-framework.md)
- [Client requirements delivery](docs/client-requirements-delivery.md)

## Documentation

- [Architecture](docs/architecture.md)
- [Gesture authoring](docs/gesture-authoring.md)
- [File formats](docs/file-formats.md)
- [Testing](docs/testing.md)
- [Release and rollback](docs/release.md)
- [Phase 7 release gate](docs/phase-7-release.md)

## License and hardware scope

This repository is intended for local simulation and motion authoring. Hardware
control is explicitly out of scope.
