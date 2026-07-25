# Architecture

The supported application is the `eric_motion_studio` package under `src/`.
`codebase/` is a read-only historical backup and is never imported or used for
runtime resources.

```text
cli.py / __main__.py  ->  application.py  ->  ui / runtime / infrastructure
                              |
                       domain + gestures
                              |
                    packaged resources and schemas
```

Domain and gesture modules are pure Python. The UI owns Qt concerns, runtime
owns MuJoCo and viewer IPC, and infrastructure owns file formats and persistence
boundaries. `config.Settings` is the only source of default resource and mutable
runtime paths. The viewer is a separate process supervised through the packaged
viewer entry point.

The Motion Library is layered:

```text
gesture definitions + stages -> generated read-only built-ins
user data/motions/            -> editable custom motions
playback/export               -> derived trajectories generated on demand
pose definitions + stages     -> searchable read-only built-in poses
user data/poses/              -> searchable editable custom poses
```

Built-ins and user motions appear in one UI library, but package resources
remain immutable. Duplicating a built-in or custom motion immediately creates
and opens a uniquely named custom motion. The Gestures and Poses panels each
separate **Custom** and **System (Built-in)** entries. System entries are
read-only and expose only **Make a copy**; copying immediately selects the new
custom entry. Custom motions are edited with the
normal Save command and can be duplicated or deleted. There is no draft or
approval state. Dense trajectories are runtime output and never the canonical
authoring source.

Library selection is activation: selecting a different item resolves unsaved
changes, stops active playback, loads the motion at its first keyframe, and
updates the MuJoCo preview. Built-ins activate in read-only mode. Natural-language
commands use the same switch path and produce a temporary editable motion; the
parser and compiler remain internal services rather than separate UI actions.

Pose selection is intentionally separate from motion selection. It stops active
playback and changes only the joint/MuJoCo preview. Capturing that preview
creates a keyframe snapshot. Built-in pose metadata references canonical stage
joint maps, while custom pose files contain their own joint snapshot and search
metadata.

Supported entry points are declared in `pyproject.toml`:

- `eric-motion-studio` for authoring, audits, and headless diagnostics;
- `eric-motion-studio-viewer` for the standalone MuJoCo viewer.
