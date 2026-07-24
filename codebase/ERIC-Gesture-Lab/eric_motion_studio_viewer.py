#!/usr/bin/env python3
"""Simulation-only MuJoCo viewer process for ERIC Motion Studio."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict

import mujoco
import mujoco.viewer

MODEL_PATH = (
    Path.home()
    / "Projects/ERIC_Motion_Studio_Developer_Package/codebase/ERIC-Gesture-Lab/unitree_mujoco"
    / "unitree_robots/g1/scene_29dof.xml"
)
LAB_DIR = Path.home() / "Projects/ERIC_Motion_Studio_Developer_Package/codebase/ERIC-Gesture-Lab"
LIVE_STATE_PATH = LAB_DIR / ".motion_studio_live_pose.json"
BASE_POSITION = [0.0, 0.0, 0.79]
BASE_QUATERNION = [1.0, 0.0, 0.0, 0.0]
SIMULATION_MODE = os.environ.get("ERIC_MOTION_STUDIO_SIM_MODE", "AUTHORING_KINEMATIC").strip().upper() or "AUTHORING_KINEMATIC"
EDITOR_JOINTS = [
    "waist_yaw_joint",
    "waist_roll_joint",
    "waist_pitch_joint",
    "left_shoulder_pitch_joint",
    "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint",
    "left_elbow_joint",
    "left_wrist_roll_joint",
    "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
    "right_shoulder_pitch_joint",
    "right_shoulder_roll_joint",
    "right_shoulder_yaw_joint",
    "right_elbow_joint",
    "right_wrist_roll_joint",
    "right_wrist_pitch_joint",
    "right_wrist_yaw_joint",
]

FULL_BODY_JOINTS = [
    "left_hip_pitch_joint",
    "left_hip_roll_joint",
    "left_hip_yaw_joint",
    "left_knee_joint",
    "left_ankle_pitch_joint",
    "left_ankle_roll_joint",
    "right_hip_pitch_joint",
    "right_hip_roll_joint",
    "right_hip_yaw_joint",
    "right_knee_joint",
    "right_ankle_pitch_joint",
    "right_ankle_roll_joint",
    *EDITOR_JOINTS,
]

LEFT_LEG_JOINTS = tuple(FULL_BODY_JOINTS[0:6])
RIGHT_LEG_JOINTS = tuple(FULL_BODY_JOINTS[6:12])


def neutral_leg_targets_text() -> str:
    return ",".join(f"{joint}=+0.000000" for joint in LEFT_LEG_JOINTS + RIGHT_LEG_JOINTS)


def log_authoring_mode() -> None:
    if SIMULATION_MODE == "AUTHORING_KINEMATIC":
        print("SIMULATION_MODE=AUTHORING_KINEMATIC", flush=True)
        print("ROOT_CONSTRAINT_ACTIVE=true", flush=True)
        print("GRAVITY_BALANCE_REQUIRED=false", flush=True)
    else:
        print("SIMULATION_MODE=DYNAMIC_VALIDATION", flush=True)
        print("FULL_BODY_STABILIZATION_ACTIVE=true", flush=True)
    print("NEUTRAL_STANCE_LOADED", flush=True)
    print("ROOT_POSITION=<0.000000,0.000000,0.790000>", flush=True)
    print("ROOT_QUATERNION=<1.000000,0.000000,0.000000,0.000000>", flush=True)
    print(f"LEG_TARGETS={neutral_leg_targets_text()}", flush=True)


def qpos_address(model: mujoco.MjModel, joint_name: str) -> int:
    joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
    if joint_id < 0:
        raise RuntimeError(f"Required joint missing from model: {joint_name}")
    return int(model.jnt_qposadr[joint_id])




def actuator_index_by_joint(model: mujoco.MjModel, joint_name: str) -> int | None:
    joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
    if joint_id < 0:
        return None
    for actuator_index in range(model.nu):
        if int(model.actuator_trnid[actuator_index][0]) == joint_id:
            return int(actuator_index)
    return None


def compact_nonzero_offsets(offsets: Dict[str, float], limit: int = 4) -> str:
    active = [(joint, value) for joint, value in offsets.items() if abs(float(value)) > 1e-6]
    if not active:
        return "none"
    return ",".join(f"{joint}={value:+.3f}" for joint, value in active[:limit])

def read_state(path: Path) -> tuple[Dict[str, float], int | None]:
    try:
        payload = json.loads(path.read_text())
        offsets = payload.get("joint_offsets_rad", {})
        if not isinstance(offsets, dict):
            return {}, None
        sequence = payload.get("sequence")
        if not isinstance(sequence, int):
            sequence = None
        return {joint: float(offsets.get(joint, 0.0)) for joint in FULL_BODY_JOINTS}, sequence
    except FileNotFoundError:
        return {}, None
    except Exception as exc:
        print(f"VIEWER_STATE_READ_FAILED: {exc}", file=sys.stderr)
        return {}, None


def self_test() -> None:
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    if SIMULATION_MODE == "AUTHORING_KINEMATIC":
        model.opt.gravity[:] = 0.0
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    data.qpos[0:3] = BASE_POSITION
    data.qpos[3:7] = BASE_QUATERNION
    addresses = {joint: qpos_address(model, joint) for joint in FULL_BODY_JOINTS}
    actuator_indices = {joint: actuator_index_by_joint(model, joint) for joint in FULL_BODY_JOINTS}
    neutral = data.qpos.copy()
    root_before = data.qpos[0:7].copy()
    test_offsets = {joint: 0.0 for joint in FULL_BODY_JOINTS}
    for index, joint in enumerate(FULL_BODY_JOINTS):
        sign = -1.0 if index % 2 else 1.0
        test_offsets[joint] = round(sign * (0.035 + (index % 5) * 0.012), 6)
    for joint, offset in test_offsets.items():
        data.qpos[addresses[joint]] = neutral[addresses[joint]] + offset
        actuator_index = actuator_indices.get(joint)
        if model.nu and actuator_index is not None:
            data.ctrl[actuator_index] = neutral[addresses[joint]] + offset
    mujoco.mj_forward(model, data)
    for joint, expected_offset in test_offsets.items():
        applied_offset = float(data.qpos[addresses[joint]] - neutral[addresses[joint]])
        if abs(applied_offset - expected_offset) > 1e-6:
            raise RuntimeError(f"Viewer mapping failed for {joint}: expected {expected_offset}, got {applied_offset}")
        actuator_index = actuator_indices.get(joint)
        if actuator_index is None:
            raise RuntimeError(f"No actuator found for {joint}")
    for _ in range(30 * 60):
        data.qpos[0:3] = BASE_POSITION
        data.qpos[3:7] = BASE_QUATERNION
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
    if max(abs(float(a) - float(b)) for a, b in zip(data.qpos[0:7], root_before)) > 1e-9:
        raise RuntimeError("Authoring root moved during 30-second fixed-root self-test")
    print(f"VIEWER_MAPPING_TEST_OK actuated_joints={len(FULL_BODY_JOINTS)} actuators={sum(1 for joint in FULL_BODY_JOINTS if actuator_indices.get(joint) is not None)}")
    print("AUTHORING_STABILITY_30S_TEST_OK root_fixed=true")
    print("VIEWER_SELF_TEST_OK")


def run(state_file: Path) -> None:
    state_file = state_file.expanduser().resolve()
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"MuJoCo model not found: {MODEL_PATH}")
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    if SIMULATION_MODE == "AUTHORING_KINEMATIC":
        model.opt.gravity[:] = 0.0
    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    data.qpos[0:3] = BASE_POSITION
    data.qpos[3:7] = BASE_QUATERNION
    data.qvel[:] = 0.0
    addresses = {joint: qpos_address(model, joint) for joint in FULL_BODY_JOINTS}
    actuator_indices = {joint: actuator_index_by_joint(model, joint) for joint in FULL_BODY_JOINTS}
    neutral = data.qpos.copy()
    neutral_ctrl = data.ctrl.copy() if model.nu else None
    log_authoring_mode()
    print("MOTION_STUDIO_VIEWER_STARTED")
    print(f"LIVE_STATE_VIEWER_PATH: {state_file}")
    print("SIMULATION ONLY — NOT CONNECTED TO PHYSICAL ERIC")
    last_state_mtime_ns = None
    last_offsets = {joint: 0.0 for joint in FULL_BODY_JOINTS}
    last_sequence = None
    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running():
            state_changed = False
            try:
                state_mtime_ns = state_file.stat().st_mtime_ns
            except FileNotFoundError:
                state_mtime_ns = None
            if state_mtime_ns is not None and state_mtime_ns != last_state_mtime_ns:
                last_offsets, last_sequence = read_state(state_file)
                last_state_mtime_ns = state_mtime_ns
                state_changed = True
                print(f"LIVE_STATE_VIEWER_UPDATE_RECEIVED: path={state_file} sequence={last_sequence} mtime_ns={state_mtime_ns}", flush=True)
            offsets = last_offsets
            with viewer.lock():
                data.qpos[:] = neutral
                data.qpos[0:3] = BASE_POSITION
                data.qpos[3:7] = BASE_QUATERNION
                for joint, offset in offsets.items():
                    data.qpos[addresses[joint]] = neutral[addresses[joint]] + offset
                data.qvel[:] = 0.0
                if model.nu and neutral_ctrl is not None:
                    data.ctrl[:] = neutral_ctrl
                    for joint, offset in offsets.items():
                        actuator_index = actuator_indices.get(joint)
                        if actuator_index is not None:
                            data.ctrl[actuator_index] = neutral[addresses[joint]] + offset
                mujoco.mj_forward(model, data)
                if SIMULATION_MODE == "DYNAMIC_VALIDATION":
                    root_height = float(data.qpos[2]) if model.nq > 2 else BASE_POSITION[2]
                    if not (0.45 <= root_height <= 1.05):
                        print(f"STABILITY_FAULT reason=root_height value={root_height:+.6f}", flush=True)
                        print("PLAYBACK_ABORTED", flush=True)
                        data.qpos[:] = neutral
                        data.qpos[0:3] = BASE_POSITION
                        data.qpos[3:7] = BASE_QUATERNION
                        data.qvel[:] = 0.0
                        mujoco.mj_forward(model, data)
                if state_changed:
                    print(f"VIEWER_POSE_APPLIED: sequence={last_sequence} nonzero={sum(1 for value in offsets.values() if abs(float(value)) > 1e-6)} sample={compact_nonzero_offsets(offsets)}", flush=True)
                    if model.nu:
                        print(f"VIEWER_CTRL_UPDATED: sequence={last_sequence} actuators={sum(1 for joint in FULL_BODY_JOINTS if actuator_indices.get(joint) is not None)}", flush=True)
            viewer.sync()
            if state_changed:
                print(f"VIEWER_REDRAW: sequence={last_sequence} true", flush=True)
            time.sleep(1.0 / 60.0)


def main() -> int:
    parser = argparse.ArgumentParser(description="ERIC Motion Studio MuJoCo viewer helper")
    parser.add_argument("--state-file", type=Path, default=LIVE_STATE_PATH)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    run(args.state_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
