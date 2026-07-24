ERIC Motion Studio
==================

Simulation-only motion authoring for the Unitree G1 model. The application does
not connect to physical ERIC hardware, BrainOS, DDS, or SDK2.

Requirements
------------

- Python 3.11
- macOS or Linux with a graphical desktop for the MuJoCo viewer

Install from the repository root:

    python3.11 -m venv .venv
    .venv/bin/pip install -e ".[dev]"

Supported entry points
----------------------

Launch the authoring application:

    .venv/bin/eric-motion-studio

Equivalent module invocation:

    .venv/bin/python -m eric_motion_studio

On macOS, `launchers/macos/ERIC Motion Studio.command` is the supported
double-click launcher. It resolves the repository and virtual environment
relative to its own location; it contains no machine-specific paths.

The viewer is normally supervised by the authoring application. Its diagnostic
entry point is:

    .venv/bin/eric-motion-studio-viewer --self-test

Validation
----------

Run the complete test and cutover gates:

    .venv/bin/ruff format --check src tests tools
    .venv/bin/ruff check src tests tools
    QT_QPA_PLATFORM=offscreen .venv/bin/pytest
    .venv/bin/eric-motion-studio --headless --no-console-log
    .venv/bin/eric-motion-studio --self-test
    .venv/bin/eric-motion-studio --audit-commands
    .venv/bin/python tools/cutover_audit.py
    .venv/bin/eric-motion-studio-viewer --self-test

Audit one prompt:

    .venv/bin/eric-motion-studio --audit-command "wave right hand"

Runtime data
------------

Built-in resources are immutable package data. User motions, exports, logs, and
viewer IPC are stored under platform user-data/state directories by default.
Use `--data-dir`, `--export-dir`, `--log-path`, `--runtime-state-path`, or the
matching `ERIC_MOTION_STUDIO_*` environment variables to override them.

Legacy backup
-------------

`codebase/` is a read-only historical backup. It is not a supported launcher,
import path, resource fallback, or runtime-data destination.
