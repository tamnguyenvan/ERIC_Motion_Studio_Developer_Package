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

Supported entry points are declared in `pyproject.toml`:

- `eric-motion-studio` for authoring, audits, and headless diagnostics;
- `eric-motion-studio-viewer` for the standalone MuJoCo viewer.
