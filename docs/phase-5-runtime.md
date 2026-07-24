# Phase 5 — MuJoCo, Viewer, and Runtime I/O

The runtime is isolated in `eric_motion_studio.runtime`. Importing the package,
domain, or UI controller layers does not import MuJoCo.

## Runtime boundaries

- `MujocoAdapter` loads the configured model, resolves all 29 shared model-profile
  joints and actuators, owns neutral state, applies validated joint offsets, and
  enforces fixed-root authoring or dynamic-validation safety rules.
- `ViewerStateStore` serializes the versioned live-pose payload through a flushed,
  fsynced temporary file and atomic replacement. Missing, malformed, and stale
  state have distinct outcomes.
- `ViewerProcessManager` launches `python -m eric_motion_studio.viewer` with the
  active interpreter and injected model/state paths. It exposes stopped, running,
  and crashed states and performs bounded terminate/kill shutdown.
- `ViewerPlaybackOutput` writes the initial pose before lazy viewer startup,
  forwards later playback frames, and returns to neutral on stop.

The packaged `eric-motion-studio-viewer` entry point uses `Settings` defaults and
the shared Unitree G1 model profile. It never references the legacy `codebase/`
tree.

## Verification

Run the headless adapter and legacy-parity stability check:

```text
eric-motion-studio-viewer --self-test
```

Expected terminal markers are `VIEWER_MAPPING_TEST_OK`,
`AUTHORING_STABILITY_30S_TEST_OK`, and `VIEWER_SELF_TEST_OK`.

The integration suite also checks atomic state round trips, malformed/stale state
rejection, process startup/crash/shutdown behavior, packaged model assets, fixed
root pose application, safety-range rejection, and visible controller errors.
