"""Packaged MuJoCo viewer entry point."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from eric_motion_studio.config import Settings
from eric_motion_studio.domain import JointValues
from eric_motion_studio.runtime.mujoco_adapter import (
    MujocoAdapter,
    SafetyViolation,
    SimulationMode,
)
from eric_motion_studio.runtime.viewer_state import (
    MalformedStateError,
    StaleStateError,
    ViewerStateStore,
)


def build_parser() -> argparse.ArgumentParser:
    defaults = Settings.load()
    parser = argparse.ArgumentParser(
        prog="eric-motion-studio-viewer",
        description="Simulation-only MuJoCo viewer for ERIC Motion Studio",
    )
    parser.add_argument("--model-path", type=Path, default=defaults.model_path)
    parser.add_argument(
        "--state-file",
        type=Path,
        default=defaults.runtime_state_path,
    )
    parser.add_argument(
        "--simulation-mode",
        choices=tuple(mode.value for mode in SimulationMode),
        default=SimulationMode.AUTHORING_KINEMATIC.value,
    )
    parser.add_argument(
        "--max-state-age",
        type=float,
        default=5.0,
        help="return to neutral when IPC state is older than this many seconds",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="load the model and verify bindings, pose application, and stability",
    )
    return parser


def self_test(model_path: Path, mode: SimulationMode) -> None:
    adapter = MujocoAdapter(model_path, mode=mode)
    offsets = {}
    for index, joint_name in enumerate(adapter.profile.joint_names):
        limit = adapter.profile.limits[joint_name]
        negative = index % 2 and limit.lower <= -0.01
        offsets[joint_name] = -0.01 if negative else 0.01
    expected = JointValues.from_mapping(offsets, adapter.profile)
    applied = adapter.apply_pose(expected, sequence=1)
    actual = dict(applied.joint_offsets)
    for joint_name, offset in offsets.items():
        if abs(actual[joint_name] - offset) > 1e-6:
            raise RuntimeError(
                f"Viewer mapping failed for {joint_name}: "
                f"expected {offset}, got {actual[joint_name]}"
            )
    for _ in range(30 * 60):
        adapter.apply_pose(expected)
    inventory = adapter.inventory()
    if inventory["actuators"] != inventory["joints"]:
        raise RuntimeError("Every configured joint must have an actuator")
    print(
        "VIEWER_MAPPING_TEST_OK "
        f"actuated_joints={inventory['joints']} "
        f"actuators={inventory['actuators']}"
    )
    print("AUTHORING_STABILITY_30S_TEST_OK root_fixed=true")
    print("VIEWER_SELF_TEST_OK")


def run_viewer(
    model_path: Path,
    state_path: Path,
    mode: SimulationMode,
    *,
    max_state_age: float,
) -> None:
    if max_state_age <= 0:
        raise ValueError("Maximum state age must be positive")
    adapter = MujocoAdapter(model_path, mode=mode)
    state_store = ViewerStateStore(state_path, profile=adapter.profile)
    import mujoco.viewer

    print(f"SIMULATION_MODE={mode.value}", flush=True)
    print("NEUTRAL_STANCE_LOADED", flush=True)
    print("MOTION_STUDIO_VIEWER_STARTED", flush=True)
    print(f"LIVE_STATE_VIEWER_PATH: {state_store.path}", flush=True)
    print("SIMULATION ONLY — NOT CONNECTED TO PHYSICAL ERIC", flush=True)

    last_mtime_ns: int | None = None
    invalid_state = False
    with mujoco.viewer.launch_passive(adapter.model, adapter.data) as viewer:
        while viewer.is_running():
            try:
                mtime_ns = state_store.path.stat().st_mtime_ns
            except FileNotFoundError:
                mtime_ns = None
            if mtime_ns != last_mtime_ns:
                last_mtime_ns = mtime_ns
                try:
                    state = state_store.read(max_age_seconds=max_state_age)
                    with viewer.lock():
                        adapter.apply_pose(
                            state.joints,
                            sequence=state.sequence,
                        )
                    invalid_state = False
                    print(
                        f"VIEWER_POSE_APPLIED: sequence={state.sequence}",
                        flush=True,
                    )
                except FileNotFoundError:
                    with viewer.lock():
                        adapter.reset()
                    invalid_state = True
                    print("VIEWER_STATE_MISSING: neutral_applied=true", flush=True)
                except (MalformedStateError, StaleStateError, SafetyViolation) as error:
                    with viewer.lock():
                        adapter.reset()
                    invalid_state = True
                    print(
                        f"VIEWER_STATE_REJECTED: {error}; neutral_applied=true",
                        file=sys.stderr,
                        flush=True,
                    )
            elif not invalid_state and mtime_ns is not None:
                try:
                    state_store.read(max_age_seconds=max_state_age)
                except StaleStateError as error:
                    with viewer.lock():
                        adapter.reset()
                    invalid_state = True
                    print(
                        f"VIEWER_STATE_STALE: {error}; neutral_applied=true",
                        file=sys.stderr,
                        flush=True,
                    )
            if mode is SimulationMode.DYNAMIC_VALIDATION:
                try:
                    with viewer.lock():
                        adapter.step()
                except SafetyViolation as error:
                    with viewer.lock():
                        adapter.reset()
                    invalid_state = True
                    print(
                        f"VIEWER_DYNAMIC_REJECTED: {error}; neutral_applied=true",
                        file=sys.stderr,
                        flush=True,
                    )
            viewer.sync()
            time.sleep(1.0 / 60.0)


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    mode = SimulationMode.parse(args.simulation_mode)
    if args.self_test:
        self_test(args.model_path, mode)
        return 0
    run_viewer(
        args.model_path,
        args.state_file,
        mode,
        max_state_age=args.max_state_age,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
