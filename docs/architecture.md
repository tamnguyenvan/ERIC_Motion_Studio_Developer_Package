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
```

Built-ins and user motions appear in one UI library, but package resources
remain immutable. Duplicating a built-in or custom motion immediately creates
and opens a uniquely named custom motion. Custom motions are edited with the
normal Save command and can be duplicated or deleted. There is no draft or
approval state. Dense trajectories are runtime output and never the canonical
authoring source.

Supported entry points are declared in `pyproject.toml`:

- `eric-motion-studio` for authoring, audits, and headless diagnostics;
- `eric-motion-studio-viewer` for the standalone MuJoCo viewer.
