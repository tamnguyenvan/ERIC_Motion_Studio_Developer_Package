# Client requirements delivery

## Runtime source confirmed

The supported macOS launcher is:

```text
launchers/macos/ERIC Motion Studio.command
```

It resolves the project root from its own location and executes:

```text
<project>/.venv/bin/eric-motion-studio
```

The installed entry point is declared in `pyproject.toml` as:

```text
eric-motion-studio = eric_motion_studio.cli:main
```

Therefore, the active runtime source is the package under
`src/eric_motion_studio/`. The historical `codebase/` directory is not used by
the launcher.

## Parser and motion generation

The runtime now uses:

- validated gesture definitions;
- exact aliases and short canonical triggers;
- composable action/effector grammar;
- typed side, direction, speed, intensity, hold, sequence, and neutral-return
  slots;
- deterministic candidate ranking and ambiguity rejection;
- suggestion-only typo similarity;
- reusable stage-sequence motion generation;
- joint-limit, amplitude, duration, balance, collision, semantic-side, and
  neutral-return validation.

Examples:

```text
idle                  -> idle_pose
standby               -> idle_pose
talking idle          -> talking_idle
pondering             -> thinking_hand_on_chin
waving left hand      -> wave(side=left)
bring down both hands -> lower_arm(side=both)
```

`idle` previously failed because it was only a tag and was not registered as an
alias, trigger, or semantic action.

## Compatibility

Legacy phrases and all definition aliases remain covered by regression tests.
The full command audit includes both aliases and triggers. Ambiguous commands
are rejected rather than guessed.

## MuJoCo verification

Run:

```bash
.venv/bin/python -m eric_motion_studio --audit-mujoco-gestures
```

This compiles every implemented canonical gesture, creates its dense
trajectory, applies every frame to the packaged Unitree G1 model, and verifies
safe joint ranges, finite state, and a fixed authoring root.

Verified result for this delivery:

```text
MUJOCO_ALL_GESTURES_AUDITED gestures=25 frames=1758 status=PASS
```

The data-driven command audit also passed:

```text
ALL_COMMANDS_AUDITED total=103 status=PASS
```

The complete automated test suite, cutover audit, and release audit passed.

## Backups

The pre-change source files are archived at:

```text
backups/gesture-command-framework/pre-change-source-8a7a06b.tar.gz
```

The baseline Git commit is:

```text
8a7a06bae077d80e80b1ea16b6a2d7ba87af75ba
```

The archive contains the pre-change versions of every existing source,
resource, and test file modified by this delivery. New documentation and test
features did not exist at the baseline.

## Adding gestures and synonyms

See [gesture-command-framework.md](gesture-command-framework.md) for the data
formats, resolution order, extension workflow, safety policy, and verification
commands.
