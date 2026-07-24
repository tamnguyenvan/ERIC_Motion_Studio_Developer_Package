# Phase 6 — Cutover

The supported product is now the `eric_motion_studio` package. The legacy
`codebase/` tree is retained read-only for regression comparison and is not in
the application import, resource, launcher, or runtime-data paths.

## Supported launch paths

- `eric-motion-studio`
- `python -m eric_motion_studio`
- macOS: `launchers/macos/ERIC Motion Studio.command`
- diagnostic viewer: `eric-motion-studio-viewer --self-test`

All launch paths resolve the active environment and package resources without
machine-specific absolute paths.

## Cutover parity checklist

The active self-test verifies:

- built-in animation, gesture, schema, and G1 model resource completeness;
- authoring from the data-driven command compiler;
- playback controller progression and neutral reset;
- built-in and newly saved animation/gesture compatibility;
- local simulation-only BrainOS export round trips;
- atomic viewer-state synchronization through MuJoCo pose application; and
- compilation and safety validation of every declared command alias.

The Qt suite covers critical interactive authoring, selection, playback, save,
export, and unsaved-change flows. The viewer self-test covers all 29 joint and
actuator bindings plus fixed-root stability. `tools/cutover_audit.py` rejects
absolute source paths, legacy runtime references, missing resources, and stale
launcher targets.

## Legacy boundary

`codebase/README.md` defines the backup as read-only. Tests may read legacy
fixtures for parity; supported application code never imports or writes there.
