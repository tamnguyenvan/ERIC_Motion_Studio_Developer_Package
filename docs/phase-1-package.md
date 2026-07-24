# Phase 1 Package

ERIC Motion Studio now uses a standard `src/` package with two equivalent
entry points:

```sh
python -m eric_motion_studio
eric-motion-studio
```

Use `--headless` for startup validation without importing PySide6 or MuJoCo.
Run `--help` for all path overrides.

## Configuration

CLI values take precedence over environment values and defaults.

| Path | CLI | Environment |
| --- | --- | --- |
| Model | `--model-path` | `ERIC_MOTION_STUDIO_MODEL_PATH` |
| User data | `--data-dir` | `ERIC_MOTION_STUDIO_DATA_DIR` |
| Exports | `--export-dir` | `ERIC_MOTION_STUDIO_EXPORT_DIR` |
| JSON log | `--log-path` | `ERIC_MOTION_STUDIO_LOG_PATH` |
| Runtime state | `--runtime-state-path` | `ERIC_MOTION_STUDIO_RUNTIME_STATE_PATH` |

The model and built-in motion data are immutable package resources. Mutable
paths use XDG user data, state, and runtime directories with home-directory
fallbacks. Startup creates only the resolved mutable directories.

Logs are newline-delimited JSON, default to `INFO`, rotate at 1 MB, and retain
three backups.
