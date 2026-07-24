# Phase 0 Baseline

Recorded on 2026-07-24 before cleanup or refactoring.

## Source Baseline

- Commit: `8434852a6ac16001a5624efd1edac349710bb141`
- Branch: `main`
- Python: CPython 3.11.15
- Authoritative legacy entry point:
  `codebase/ERIC-Gesture-Lab/eric_motion_studio.py`
- Non-authoritative launcher: `codebase/ERIC Motion Studio.command`
  (stale `$HOME/Desktop/ERIC-MuJoCo` and `$HOME/Desktop/ERIC-Gesture-Lab`
  paths)

The legacy entry point is frozen as the behavioral reference for the refactor.

## Supported Launch Commands

Run from the repository root with the project virtual environment:

```sh
.venv/bin/python codebase/ERIC-Gesture-Lab/eric_motion_studio.py
.venv/bin/python codebase/ERIC-Gesture-Lab/eric_motion_studio.py --self-test
.venv/bin/python codebase/ERIC-Gesture-Lab/eric_motion_studio.py --audit-commands
.venv/bin/python codebase/ERIC-Gesture-Lab/eric_motion_studio.py --audit-command "wave right hand"
.venv/bin/python codebase/ERIC-Gesture-Lab/eric_motion_studio_viewer.py --self-test
```

The GUI and viewer require a display. The self-test and command-audit commands
are supported headless regression gates.

## Dependency Baseline

`codebase/ERIC-Gesture-Lab/requirements.txt` is the reproducible dependency
record:

```text
absl-py==2.5.0
etils==1.14.0
fsspec==2026.6.0
glfw==2.10.2
mujoco==3.10.0
numpy==1.26.4
PyOpenGL==3.1.10
PySide6==6.11.1
PySide6_Addons==6.11.1
PySide6_Essentials==6.11.1
shiboken6==6.11.1
typing_extensions==4.16.0
zipp==4.1.0
```

## Regression Outcomes

- Legacy `--self-test`: exit 0; all markers in
  `tests/fixtures/self-test-markers.txt` present.
- Focused audit, `wave right hand`: exit 0; all markers in
  `tests/fixtures/command-audit-markers.txt` present.
- Characterization suite covers motion generation and editing primitives,
  playback trajectory accounting, animation schemas, gesture persistence,
  viewer state parsing, and the BrainOS export contract.

Run the complete Phase 0 quality gate:

```sh
.venv/bin/python -m unittest discover -s tests -v
```
