# Review Findings

## P1: Launch passive viewers through `mjpython` on macOS

**Location:** `src/eric_motion_studio/runtime/viewer_process.py:51`

`ViewerLaunchSettings` defaults to `sys.executable`, so the passive MuJoCo
viewer is launched through ordinary Python. On the supported macOS runtime,
MuJoCo requires applications using `launch_passive` to run through `mjpython`;
the packaged viewer can therefore abort or fail to open when playback begins.

Resolve and use the environment's `mjpython` launcher on macOS while retaining
the active Python interpreter on other platforms.

## P2: Step the simulation in dynamic validation mode

**Location:** `src/eric_motion_studio/viewer.py:153-154`

The viewer loop synchronizes and sleeps without calling `mj_step` when
`DYNAMIC_VALIDATION` is selected. Pose application also restores the neutral
root and only runs `mj_forward`, so gravity, contacts, and actuator forces never
evolve. The root-height safety check consequently examines the injected 0.79 m
pose rather than detecting an unstable simulation.

Advance MuJoCo dynamics in dynamic-validation mode and validate the evolved
simulation state.
