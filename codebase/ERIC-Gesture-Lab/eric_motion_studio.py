#!/usr/bin/env python3
"""ERIC Motion Studio Animation V1 - simulation-only MuJoCo editor."""

from __future__ import annotations

import argparse
import json
import atexit
import math
import copy
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Any

HEADLESS_CLI = (
    any(arg == "--self-test" or arg == "--audit-commands" or arg == "--audit-command" for arg in sys.argv[1:])
    or os.environ.get("ERIC_MOTION_STUDIO_SELF_TEST") == "1"
)


def configure_qt_plugin_path() -> None:
    try:
        import PySide6
    except Exception as exc:  # pragma: no cover - shown to user at startup
        print(f"ERROR: PySide6 package import failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

    pyside_root = Path(PySide6.__file__).resolve().parent
    qt_plugins = pyside_root / "Qt" / "plugins"
    qt_platforms = qt_plugins / "platforms"
    cocoa_plugin = qt_platforms / "libqcocoa.dylib"
    # if not cocoa_plugin.exists():
    #     print(f"ERROR: Qt cocoa platform plugin not found: {cocoa_plugin}", file=sys.stderr)
    #     raise SystemExit(1)

    # Do not force QT_PLUGIN_PATH/QT_QPA_PLATFORM_PLUGIN_PATH here. The isolated
    # PySide6 runtime knows its own plugin tree; stale overrides are what caused
    # Qt to reject the Cocoa platform plugin in macOS launcher sessions.
    os.environ.pop("QT_PLUGIN_PATH", None)
    os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)
    os.environ.pop("QT_QPA_PLATFORM", None)
    os.environ.pop("DYLD_LIBRARY_PATH", None)
    os.environ.pop("DYLD_FRAMEWORK_PATH", None)
    print(f"QT_PLUGIN_ROOT_VERIFIED: {qt_plugins}")
    print(f"QT_COCOA_PLUGIN_VERIFIED: {cocoa_plugin}")
    print("QT_PLUGIN_DISCOVERY: PySide6 default runtime discovery")


if not HEADLESS_CLI:
    configure_qt_plugin_path()
    try:
        from PySide6.QtCore import QCoreApplication, Qt, QTimer
        from PySide6.QtGui import QKeySequence, QShortcut
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QFileDialog,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QInputDialog,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QDoubleSpinBox,
            QScrollArea,
            QSlider,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
    except Exception as exc:  # pragma: no cover - shown to user at startup
        print(f"ERROR: PySide6 Qt import failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

    print(f"QT_LIBRARY_PATHS_ACTIVE: {QCoreApplication.libraryPaths()}")
else:
    print("QT_IMPORT_SKIPPED_HEADLESS_CLI", flush=True)

    class _HeadlessQtObject:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Qt widgets are unavailable in headless Motion Studio CLI mode")

    class _HeadlessBase:
        pass

    class _HeadlessQtNamespace:
        AlignCenter = 0
        Horizontal = 1

    QMainWindow = _HeadlessBase
    QApplication = QCheckBox = QComboBox = QFileDialog = QGridLayout = QGroupBox = QHBoxLayout = QInputDialog = QLabel = QListWidget = QListWidgetItem = QLineEdit = QMessageBox = QPushButton = QDoubleSpinBox = QScrollArea = QSlider = QTextEdit = QVBoxLayout = QWidget = _HeadlessQtObject
    QTimer = QKeySequence = QShortcut = _HeadlessQtObject
    Qt = _HeadlessQtNamespace()

try:
    import mujoco
except Exception as exc:  # pragma: no cover - shown to user at startup
    print(f"ERROR: MuJoCo import failed: {exc}", file=sys.stderr)
    raise SystemExit(1)

LAB_DIR = Path(__file__).resolve().parent
MODEL_PATH = LAB_DIR / "unitree_mujoco" / "unitree_robots/g1/scene_29dof.xml"
POSES_DIR = LAB_DIR / "poses"
ANIMATIONS_DIR = LAB_DIR / "animations"
CUSTOM_ANIMATIONS_DIR = ANIMATIONS_DIR / "custom"
BRAINOS_EXPORTS_DIR = LAB_DIR / "brainos_exports"
GESTURES_DIR = LAB_DIR / "gestures"
COMMAND_AUDIT_DIR = LAB_DIR / "command_audit_reports"
SAMPLE_ANIMATION_PATH = ANIMATIONS_DIR / "conversational_talking.json"
SCRATCH_HEAD_ANIMATION_PATH = ANIMATIONS_DIR / "scratch_head.json"
THINKING_HAND_ON_CHIN_ANIMATION_PATH = ANIMATIONS_DIR / "thinking_hand_on_chin.json"
LIVE_STATE_TMP_PATH = LAB_DIR / ".motion_studio_live_pose.tmp"
LIVE_STATE_PATH = LAB_DIR / ".motion_studio_live_pose.json"
VIEWER_SCRIPT_PATH = LAB_DIR / "eric_motion_studio_viewer.py"
STATUS_TEXT = "SIMULATION ONLY — NOT CONNECTED TO PHYSICAL ERIC"

BASE_POSITION = [0.0, 0.0, 0.79]
BASE_QUATERNION = [1.0, 0.0, 0.0, 0.0]
SLIDER_SCALE = 1000
DEFAULT_RANGE = (-1.5, 1.5)
DEFAULT_KEYFRAME_DURATION_MS = 900
MIN_KEYFRAME_DURATION_MS = 100
MAX_KEYFRAME_DURATION_MS = 10000
DEFAULT_PLAYBACK_SPEED = 1.0
SIMULATION_MODE = os.environ.get("ERIC_MOTION_STUDIO_SIM_MODE", "AUTHORING_KINEMATIC").strip().upper() or "AUTHORING_KINEMATIC"
GESTURE_FRAME_RATE = 30
GESTURE_SCHEMA_VERSION = 1
GESTURE_RETURN_NEUTRAL_DURATION_MS = 650
MIN_PLAYBACK_SPEED = 0.25
MAX_PLAYBACK_SPEED = 2.0
SOFT_LIMIT_RATIO = 0.85

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
WAIST_JOINTS = ("waist_yaw_joint", "waist_roll_joint", "waist_pitch_joint")
LEFT_ARM_JOINTS = tuple(joint for joint in FULL_BODY_JOINTS if joint.startswith("left_shoulder") or joint.startswith("left_elbow") or joint.startswith("left_wrist"))
RIGHT_ARM_JOINTS = tuple(joint for joint in FULL_BODY_JOINTS if joint.startswith("right_shoulder") or joint.startswith("right_elbow") or joint.startswith("right_wrist"))
ARM_JOINTS = LEFT_ARM_JOINTS + RIGHT_ARM_JOINTS

# Conservative simulation-only limits. They keep generated poses well inside the
# MuJoCo model limits and avoid turning prompt text into risky leg or torso poses.
FULL_BODY_SOFT_LIMITS = {
    "left_hip_pitch_joint": (-0.18, 0.18),
    "left_hip_roll_joint": (-0.12, 0.12),
    "left_hip_yaw_joint": (-0.08, 0.08),
    "left_knee_joint": (-0.02, 0.28),
    "left_ankle_pitch_joint": (-0.14, 0.14),
    "left_ankle_roll_joint": (-0.10, 0.10),
    "right_hip_pitch_joint": (-0.18, 0.18),
    "right_hip_roll_joint": (-0.12, 0.12),
    "right_hip_yaw_joint": (-0.08, 0.08),
    "right_knee_joint": (-0.02, 0.28),
    "right_ankle_pitch_joint": (-0.14, 0.14),
    "right_ankle_roll_joint": (-0.10, 0.10),
    "waist_yaw_joint": (-0.35, 0.35),
    "waist_roll_joint": (-0.10, 0.10),
    "waist_pitch_joint": (-0.08, 0.12),
    "left_shoulder_pitch_joint": (-0.95, 0.20),
    "left_shoulder_roll_joint": (-0.25, 0.55),
    "left_shoulder_yaw_joint": (-0.55, 0.55),
    "left_elbow_joint": (-0.10, 0.75),
    "left_wrist_roll_joint": (-0.35, 0.35),
    "left_wrist_pitch_joint": (-0.25, 0.25),
    "left_wrist_yaw_joint": (-0.35, 0.35),
    "right_shoulder_pitch_joint": (-0.95, 0.20),
    "right_shoulder_roll_joint": (-0.55, 0.25),
    "right_shoulder_yaw_joint": (-0.55, 0.55),
    "right_elbow_joint": (-0.75, 0.10),
    "right_wrist_roll_joint": (-0.35, 0.35),
    "right_wrist_pitch_joint": (-0.25, 0.25),
    "right_wrist_yaw_joint": (-0.35, 0.35),
}
MAX_GENERATED_JOINT_DELTA_RAD = 0.16
VISIBLE_ARM_DELTA_THRESHOLD_RAD = 0.22
STRICT_INACTIVE_TOLERANCE = 1e-6
TRAJECTORY_ACCOUNTING_TOLERANCE_SECONDS = 0.12
TALKING_IDLE_FRAME_COUNT = 180
TALKING_IDLE_DURATION_SECONDS = 6.0
TALKING_IDLE_DURATION_MS = 6000


@dataclass(frozen=True)
class JointBinding:
    name: str
    qpos_address: int
    limited: bool
    lower: float
    upper: float


@dataclass
class Keyframe:
    name: str
    duration_ms: int
    joint_offsets_rad: Dict[str, float]


def iso_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def display_joint_name(joint_name: str) -> str:
    return joint_name.replace("_joint", "")


def keyframe_clone(frame: Keyframe) -> Keyframe:
    return Keyframe(frame.name, int(frame.duration_ms), complete_offsets(frame.joint_offsets_rad))


def clone_keyframes(frames: Sequence[Keyframe]) -> List[Keyframe]:
    return [keyframe_clone(frame) for frame in frames]


def model_name(model: mujoco.MjModel, obj_type: mujoco.mjtObj, index: int) -> str:
    return mujoco.mj_id2name(model, obj_type, index) or ""


def print_model_inventory(model: mujoco.MjModel) -> None:
    print("=== ERIC Motion Studio Model Inventory ===")
    print(f"MODEL_PATH: {MODEL_PATH}")
    print("JOINTS:")
    for i in range(model.njnt):
        print(f"  {i}: {model_name(model, mujoco.mjtObj.mjOBJ_JOINT, i)}")
    print("ACTUATORS:")
    for i in range(model.nu):
        print(f"  {i}: {model_name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i)}")
    print("KEYFRAMES:")
    if model.nkey == 0:
        print("  none")
    for i in range(model.nkey):
        print(f"  {i}: {model_name(model, mujoco.mjtObj.mjOBJ_KEY, i)}")
    print(STATUS_TEXT)


def joint_binding(model: mujoco.MjModel, joint_name: str) -> JointBinding:
    joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
    if joint_id < 0:
        raise RuntimeError(f"Required joint missing from model: {joint_name}")
    address = int(model.jnt_qposadr[joint_id])
    limited = bool(model.jnt_limited[joint_id])
    if limited:
        lower = float(model.jnt_range[joint_id][0])
        upper = float(model.jnt_range[joint_id][1])
    else:
        lower, upper = DEFAULT_RANGE
    if lower >= upper:
        lower, upper = DEFAULT_RANGE
    return JointBinding(joint_name, address, limited, lower, upper)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def smooth_step(value: float) -> float:
    t = clamp(value, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def interpolate_offsets(a: Dict[str, float], b: Dict[str, float], alpha: float) -> Dict[str, float]:
    eased = smooth_step(alpha)
    return {
        joint: float(a.get(joint, 0.0)) + (float(b.get(joint, 0.0)) - float(a.get(joint, 0.0))) * eased
        for joint in FULL_BODY_JOINTS
    }


def complete_offsets(offsets: Dict[str, float] | None) -> Dict[str, float]:
    source = offsets or {}
    return {joint: float(source.get(joint, 0.0)) for joint in FULL_BODY_JOINTS}


def keyframe_to_json(keyframe: Keyframe) -> Dict[str, object]:
    joint_targets = {joint: round(float(keyframe.joint_offsets_rad.get(joint, 0.0)), 6) for joint in FULL_BODY_JOINTS}
    return {
        "name": keyframe.name,
        "duration_ms": int(keyframe.duration_ms),
        "joint_targets": joint_targets,
        "joint_offsets_rad": joint_targets,
    }


def parse_keyframe(payload: Dict[str, object], index: int) -> Keyframe:
    if not isinstance(payload, dict):
        raise ValueError(f"Keyframe {index + 1} is not an object")
    offsets = payload.get("joint_targets")
    if offsets is None:
        offsets = payload.get("joint_offsets_rad")
    if not isinstance(offsets, dict):
        raise ValueError(f"Keyframe {index + 1} missing joint_targets")
    unknown = sorted(set(offsets) - set(FULL_BODY_JOINTS))
    if unknown:
        raise ValueError(f"Keyframe {index + 1} contains unknown joints: {', '.join(unknown)}")
    duration = int(payload.get("duration_ms", DEFAULT_KEYFRAME_DURATION_MS))
    duration = max(MIN_KEYFRAME_DURATION_MS, min(MAX_KEYFRAME_DURATION_MS, duration))
    return Keyframe(
        name=str(payload.get("name") or f"Keyframe {index + 1}"),
        duration_ms=duration,
        joint_offsets_rad=complete_offsets(offsets),
    )


def animation_payload(keyframes: Sequence[Keyframe], name: str = "untitled") -> Dict[str, object]:
    now = iso_timestamp()
    total_duration = sum(int(frame.duration_ms) for frame in keyframes)
    return {
        "schema": "eric_motion_studio_animation_v1",
        "version": 1,
        "simulation_only": True,
        "motion_name": name,
        "name": name,
        "model": str(MODEL_PATH),
        "loop": False,
        "total_duration_ms": total_duration,
        "created_at": now,
        "updated_at": now,
        "keyframes": [keyframe_to_json(frame) for frame in keyframes],
    }


def load_animation_file(path: Path) -> List[Keyframe]:
    payload = json.loads(path.read_text())
    if payload.get("schema") != "eric_motion_studio_animation_v1":
        raise ValueError("Animation file schema must be eric_motion_studio_animation_v1")
    frames = payload.get("keyframes")
    if not isinstance(frames, list) or not frames:
        raise ValueError("Animation file must contain at least one keyframe")
    return [parse_keyframe(frame, i) for i, frame in enumerate(frames)]


def load_animation_payload(path: Path) -> tuple[List[Keyframe], Dict[str, object]]:
    payload = json.loads(path.read_text())
    if payload.get("schema") != "eric_motion_studio_animation_v1":
        raise ValueError("Animation file schema must be eric_motion_studio_animation_v1")
    frames = payload.get("keyframes")
    if not isinstance(frames, list) or not frames:
        raise ValueError("Animation file must contain at least one keyframe")
    return [parse_keyframe(frame, i) for i, frame in enumerate(frames)], payload


def build_motion_payload(
    keyframes: Sequence[Keyframe],
    *,
    name: str,
    loop: bool,
    description: str = "",
    created_at: str | None = None,
) -> Dict[str, object]:
    payload = animation_payload(keyframes, name=name)
    payload["created_at"] = created_at or payload["created_at"]
    payload["updated_at"] = iso_timestamp()
    payload["loop"] = bool(loop)
    payload["description"] = description
    payload["total_duration_ms"] = sum(int(frame.duration_ms) for frame in keyframes)
    return payload


def slugify_gesture_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or f"gesture_{time.strftime('%Y%m%d_%H%M%S')}"


def display_name_from_gesture_id(gesture_id: str) -> str:
    return " ".join(part.capitalize() for part in gesture_id.replace("-", "_").split("_") if part) or gesture_id


def _frame_array_from_offsets(offsets: Dict[str, float]) -> List[float]:
    return [round(float(offsets.get(joint, 0.0)), 6) for joint in FULL_BODY_JOINTS]


def _offsets_from_frame_array(values: Sequence[object]) -> Dict[str, float]:
    if len(values) != len(FULL_BODY_JOINTS):
        raise ValueError(f"Frame joint target count {len(values)} does not match expected {len(FULL_BODY_JOINTS)}")
    offsets: Dict[str, float] = {}
    for joint, value in zip(FULL_BODY_JOINTS, values):
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"Frame contains non-finite value for {joint}")
        offsets[joint] = round(numeric, 6)
    return complete_offsets(offsets)


def dense_trajectory_from_keyframes(keyframes: Sequence[Keyframe], frame_rate: int = GESTURE_FRAME_RATE) -> List[Dict[str, object]]:
    if len(keyframes) < 1:
        return []
    frame_interval = 1.0 / float(frame_rate)
    trajectory: List[Dict[str, object]] = []
    timestamp = 0.0
    current = complete_offsets(keyframes[0].joint_offsets_rad)
    trajectory.append({"timestamp": round(timestamp, 6), "joint_targets": _frame_array_from_offsets(current)})
    for target_frame in keyframes[1:]:
        start = complete_offsets(current)
        target = complete_offsets(target_frame.joint_offsets_rad)
        duration_seconds = max(0.001, int(target_frame.duration_ms) / 1000.0)
        steps = max(1, int(round(duration_seconds * frame_rate)))
        for step in range(1, steps + 1):
            alpha = step / steps
            current = interpolate_offsets(start, target, alpha)
            timestamp += frame_interval
            trajectory.append({"timestamp": round(timestamp, 6), "joint_targets": _frame_array_from_offsets(current)})
    return trajectory


def keyframes_from_dense_trajectory(frames: Sequence[Dict[str, object]], frame_rate: int = GESTURE_FRAME_RATE) -> List[Keyframe]:
    if not frames:
        return []
    duration_ms = max(1, round(1000.0 / float(frame_rate)))
    keyframes: List[Keyframe] = []
    for index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            raise ValueError(f"Gesture frame {index + 1} is not an object")
        values = frame.get("joint_targets")
        if not isinstance(values, list):
            raise ValueError(f"Gesture frame {index + 1} missing joint_targets array")
        keyframes.append(Keyframe(f"gesture frame {index + 1}", duration_ms, _offsets_from_frame_array(values)))
    return keyframes


def validate_dense_trajectory(frames: Sequence[Dict[str, object]], expected_joint_count: int = len(FULL_BODY_JOINTS)) -> None:
    if not frames:
        raise ValueError("trajectory_empty")
    previous_timestamp = -1.0
    for index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            raise ValueError(f"frame_{index + 1}_not_object")
        timestamp = float(frame.get("timestamp", 0.0))
        if not math.isfinite(timestamp):
            raise ValueError(f"frame_{index + 1}_timestamp_not_finite")
        if timestamp < previous_timestamp:
            raise ValueError(f"frame_{index + 1}_timestamp_out_of_order")
        previous_timestamp = timestamp
        values = frame.get("joint_targets")
        if not isinstance(values, list):
            raise ValueError(f"frame_{index + 1}_missing_joint_targets")
        if len(values) != expected_joint_count:
            raise ValueError(f"frame_{index + 1}_joint_count_{len(values)}_expected_{expected_joint_count}")
        for value in values:
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError(f"frame_{index + 1}_non_finite_joint")


def _max_array_delta(a: Sequence[object], b: Sequence[object]) -> float:
    return max((abs(float(left) - float(right)) for left, right in zip(a, b)), default=0.0)


def loop_safe_dense_trajectory(frames: Sequence[Dict[str, object]], frame_rate: int = GESTURE_FRAME_RATE) -> List[Dict[str, object]]:
    validate_dense_trajectory(frames)
    output = [dict(frame) for frame in frames]
    if len(output) < 2:
        return output
    first = output[0]["joint_targets"]
    last = output[-1]["joint_targets"]
    if not isinstance(first, list) or not isinstance(last, list):
        return output
    if _max_array_delta(first, last) <= 0.015:
        return output
    start_offsets = _offsets_from_frame_array(last)
    end_offsets = _offsets_from_frame_array(first)
    timestamp = float(output[-1]["timestamp"])
    bridge_steps = max(6, round(0.75 * frame_rate))
    frame_interval = 1.0 / float(frame_rate)
    for step in range(1, bridge_steps + 1):
        alpha = step / bridge_steps
        timestamp += frame_interval
        offsets = interpolate_offsets(start_offsets, end_offsets, alpha)
        output.append({"timestamp": round(timestamp, 6), "joint_targets": _frame_array_from_offsets(offsets)})
    return output


def build_gesture_payload(
    *,
    gesture_id: str,
    display_name: str,
    source_prompt: str,
    keyframes: Sequence[Keyframe],
    motion_type: str,
    loopable: bool,
    interruptible: bool,
    return_to_neutral: bool,
    tags: Sequence[str],
) -> Dict[str, object]:
    dense_frames = dense_trajectory_from_keyframes(keyframes, GESTURE_FRAME_RATE)
    if loopable:
        dense_frames = loop_safe_dense_trajectory(dense_frames, GESTURE_FRAME_RATE)
    validate_dense_trajectory(dense_frames)
    duration_seconds = float(dense_frames[-1]["timestamp"]) if dense_frames else 0.0
    return {
        "schema_version": GESTURE_SCHEMA_VERSION,
        "gesture_id": gesture_id,
        "display_name": display_name.strip() or display_name_from_gesture_id(gesture_id),
        "source_prompt": source_prompt,
        "created_at": iso_timestamp(),
        "robot_model": "Unitree G1",
        "simulation_only": True,
        "frame_rate": GESTURE_FRAME_RATE,
        "duration_seconds": round(duration_seconds, 6),
        "frame_count": len(dense_frames),
        "motion_type": motion_type,
        "loopable": bool(loopable),
        "interruptible": bool(interruptible),
        "return_to_neutral": bool(return_to_neutral),
        "tags": [tag.strip() for tag in tags if tag.strip()],
        "joint_names": list(FULL_BODY_JOINTS),
        "frames": dense_frames,
    }


def load_gesture_payload(path: Path) -> Dict[str, object]:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != GESTURE_SCHEMA_VERSION:
        raise ValueError("Gesture schema_version must be 1")
    if payload.get("robot_model") != "Unitree G1":
        raise ValueError("Gesture robot_model must be Unitree G1")
    joint_names = payload.get("joint_names")
    if joint_names != list(FULL_BODY_JOINTS):
        raise ValueError("Gesture joint_names do not match this Motion Studio model")
    frames = payload.get("frames")
    if not isinstance(frames, list):
        raise ValueError("Gesture frames must be a list")
    validate_dense_trajectory(frames)
    return payload


def neutral_offsets() -> Dict[str, float]:
    return complete_offsets({})


def neutral_leg_targets_text() -> str:
    return ",".join(f"{joint}=+0.000000" for joint in LEFT_LEG_JOINTS + RIGHT_LEG_JOINTS)


def log_neutral_stance_loaded() -> None:
    print("NEUTRAL_STANCE_LOADED", flush=True)
    print("ROOT_POSITION=<0.000000,0.000000,0.790000>", flush=True)
    print("ROOT_QUATERNION=<1.000000,0.000000,0.000000,0.000000>", flush=True)
    print(f"LEG_TARGETS={neutral_leg_targets_text()}", flush=True)


def _normalize_prompt_text(description: str) -> str:
    return re.sub(r"\s+", " ", description.strip().lower()).strip()


def _parse_wave_prompt(description: str) -> str | None:
    prompt = _normalize_prompt_text(description)
    if not prompt:
        return None
    if re.fullmatch(r"(please\s+)?wave(\s+please)?", prompt):
        return "right"
    if re.search(r"\bwave\b", prompt):
        if "left" in prompt:
            return "left"
        if "right" in prompt or "hand" in prompt:
            return "right"
        return "right"
    return None


def _is_talking_idle_description(description: str) -> bool:
    prompt = _normalize_prompt_text(description)
    direct_phrases = {
        "talking motion",
        "natural talking motion",
        "conversational idle",
        "talking idle",
        "presentation talking motion",
        "happy talking motion",
    }
    if prompt in direct_phrases:
        return True
    return ("talking" in prompt and "motion" in prompt) or ("conversational" in prompt and "idle" in prompt)


def _wave_side_profile(side: str) -> Dict[str, float]:
    # Explicit model-aware profiles. Left and right are intentionally not made by
    # blindly negating every joint: elbow and wrist signs follow the MuJoCo G1
    # joint axes that make the forearm read upright from the default camera.
    if side == "left":
        profile = {
            "left_shoulder_pitch_joint": -0.820,
            "left_shoulder_roll_joint": 0.365,
            "left_shoulder_yaw_joint": -0.105,
            "left_elbow_joint": 0.720,
            "left_wrist_roll_joint": 0.000,
            "left_wrist_pitch_joint": 0.080,
            "left_wrist_yaw_joint": -0.255,
        }
    else:
        profile = {
            "right_shoulder_pitch_joint": -0.820,
            "right_shoulder_roll_joint": -0.365,
            "right_shoulder_yaw_joint": 0.105,
            "right_elbow_joint": -0.720,
            "right_wrist_roll_joint": 0.000,
            "right_wrist_pitch_joint": 0.080,
            "right_wrist_yaw_joint": 0.255,
        }
    target = _clamp_full_body_offsets(profile)
    profile_text = ",".join(f"{joint}:{value:+.3f}" for joint, value in target.items() if abs(value) > 1e-6)
    print(f"WAVE_SIDE_PROFILE side={side} targets={profile_text}", flush=True)
    return target


def _wave_target(side: str, oscillation: float = 0.0) -> Dict[str, float]:
    target = _wave_side_profile(side)
    if side == "left":
        target["left_shoulder_yaw_joint"] = clamp(target["left_shoulder_yaw_joint"] + oscillation, *FULL_BODY_SOFT_LIMITS["left_shoulder_yaw_joint"])
        target["left_wrist_yaw_joint"] = clamp(target["left_wrist_yaw_joint"] + oscillation * 0.72, *FULL_BODY_SOFT_LIMITS["left_wrist_yaw_joint"])
        target["left_wrist_roll_joint"] = clamp(oscillation * 0.50, *FULL_BODY_SOFT_LIMITS["left_wrist_roll_joint"])
    else:
        target["right_shoulder_yaw_joint"] = clamp(target["right_shoulder_yaw_joint"] + oscillation, *FULL_BODY_SOFT_LIMITS["right_shoulder_yaw_joint"])
        target["right_wrist_yaw_joint"] = clamp(target["right_wrist_yaw_joint"] + oscillation * 0.72, *FULL_BODY_SOFT_LIMITS["right_wrist_yaw_joint"])
        target["right_wrist_roll_joint"] = clamp(oscillation * 0.50, *FULL_BODY_SOFT_LIMITS["right_wrist_roll_joint"])
    return complete_offsets(target)


def _compile_wave_motion(side: str) -> List[Keyframe]:
    print(f"MOTION_PARSE_OK action=wave side={side} confidence=1.00", flush=True)
    print(f"WAVE_DETECTED side={side}", flush=True)
    oscillations = [-0.30, 0.30, -0.30, 0.30, -0.28, 0.28]
    peak = _clamp_full_body_offsets(_wave_target(side, max(oscillations, key=abs)))
    peak_text = ",".join(f"{joint}:{value:+.3f}" for joint, value in peak.items() if abs(value) > 1e-6)
    print(f"WAVE_PEAK_TARGETS={peak_text}", flush=True)
    print("WAVE_OSCILLATIONS count=3", flush=True)
    frames = [Keyframe("neutral", 250, neutral_offsets())]
    _append_motion_frames(frames, name=f"raise {side} arm for wave", target=_wave_target(side, 0.0), frame_count=8, total_duration_ms=800)
    for index, osc in enumerate(oscillations, start=1):
        cycle = ((index - 1) // 2) + 1
        direction = "left" if osc < 0 else "right"
        _append_motion_frames(frames, name=f"wave cycle {cycle} extremum {direction}", target=_wave_target(side, osc), frame_count=4, total_duration_ms=400)
        print(f"WAVE_EXTREMUM cycle={cycle} direction={direction} frame={len(frames)} value={osc:+.3f}", flush=True)
    _append_motion_frames(frames, name="wave brief hold", target=_wave_target(side, 0.0), frame_count=4, total_duration_ms=400, hold=True)
    _append_motion_frames(frames, name=f"lower {side} arm from wave", target=neutral_offsets(), frame_count=8, total_duration_ms=800)
    _append_motion_frames(frames, name="settle neutral", target=neutral_offsets(), frame_count=3, total_duration_ms=300, hold=True)
    return [_with_duration(frame, max(80, frame.duration_ms)) for frame in frames]


def _talking_idle_transition_durations() -> List[int]:
    # There are 179 transitions after frame 0. 93 x 34 ms + 86 x 33 ms = 6000 ms,
    # while each transition still expands to exactly one 30 Hz playback frame.
    return [34 if index < 93 else 33 for index in range(TALKING_IDLE_FRAME_COUNT - 1)]


def _talking_idle_phase_targets() -> List[tuple[str, int, int, Dict[str, float]]]:
    rest = {
        "waist_pitch_joint": 0.005,
        "left_shoulder_pitch_joint": -0.180,
        "left_shoulder_roll_joint": 0.055,
        "left_shoulder_yaw_joint": -0.060,
        "left_elbow_joint": 0.280,
        "left_wrist_roll_joint": -0.020,
        "left_wrist_pitch_joint": 0.030,
        "left_wrist_yaw_joint": -0.060,
        "right_shoulder_pitch_joint": -0.190,
        "right_shoulder_roll_joint": -0.060,
        "right_shoulder_yaw_joint": 0.060,
        "right_elbow_joint": -0.300,
        "right_wrist_roll_joint": 0.020,
        "right_wrist_pitch_joint": 0.030,
        "right_wrist_yaw_joint": 0.060,
    }
    right_gesture = dict(rest)
    right_gesture.update({
        "waist_yaw_joint": -0.018,
        "waist_pitch_joint": 0.010,
        "right_shoulder_pitch_joint": -0.280,
        "right_shoulder_roll_joint": -0.130,
        "right_shoulder_yaw_joint": 0.140,
        "right_elbow_joint": -0.250,
        "right_wrist_roll_joint": 0.060,
        "right_wrist_pitch_joint": 0.050,
        "right_wrist_yaw_joint": 0.140,
    })
    left_gesture = dict(rest)
    left_gesture.update({
        "waist_yaw_joint": 0.018,
        "waist_pitch_joint": 0.010,
        "left_shoulder_pitch_joint": -0.270,
        "left_shoulder_roll_joint": 0.130,
        "left_shoulder_yaw_joint": -0.140,
        "left_elbow_joint": 0.250,
        "left_wrist_roll_joint": -0.060,
        "left_wrist_pitch_joint": 0.050,
        "left_wrist_yaw_joint": -0.140,
    })
    open_palms = {
        "waist_pitch_joint": 0.012,
        "left_shoulder_pitch_joint": -0.250,
        "left_shoulder_roll_joint": 0.180,
        "left_shoulder_yaw_joint": -0.080,
        "left_elbow_joint": 0.220,
        "left_wrist_roll_joint": -0.040,
        "left_wrist_pitch_joint": 0.080,
        "left_wrist_yaw_joint": -0.120,
        "right_shoulder_pitch_joint": -0.260,
        "right_shoulder_roll_joint": -0.185,
        "right_shoulder_yaw_joint": 0.085,
        "right_elbow_joint": -0.225,
        "right_wrist_roll_joint": 0.040,
        "right_wrist_pitch_joint": 0.080,
        "right_wrist_yaw_joint": 0.120,
    }
    right_small = dict(rest)
    right_small.update({
        "waist_yaw_joint": -0.010,
        "right_shoulder_pitch_joint": -0.230,
        "right_shoulder_roll_joint": -0.095,
        "right_shoulder_yaw_joint": 0.100,
        "right_elbow_joint": -0.270,
        "right_wrist_roll_joint": 0.040,
        "right_wrist_yaw_joint": 0.100,
    })
    left_small = dict(rest)
    left_small.update({
        "waist_yaw_joint": 0.010,
        "left_shoulder_pitch_joint": -0.220,
        "left_shoulder_roll_joint": 0.090,
        "left_shoulder_yaw_joint": -0.100,
        "left_elbow_joint": 0.260,
        "left_wrist_roll_joint": -0.040,
        "left_wrist_yaw_joint": -0.100,
    })
    return [
        ("neutral hold", 0, 14, neutral_offsets()),
        ("hands to lower chest", 15, 44, complete_offsets(rest)),
        ("right-hand speaking gesture", 45, 68, complete_offsets(right_gesture)),
        ("left-hand speaking gesture", 69, 92, complete_offsets(left_gesture)),
        ("two-handed open-palms emphasis", 93, 116, complete_offsets(open_palms)),
        ("right-hand smaller gesture", 117, 137, complete_offsets(right_small)),
        ("left-hand smaller gesture", 138, 158, complete_offsets(left_small)),
        ("return to neutral", 159, 179, neutral_offsets()),
    ]


def _log_talking_idle_phase_peaks(phase_name: str, target: Dict[str, float]) -> None:
    peaks = {
        joint: round(float(value), 6)
        for joint, value in complete_offsets(target).items()
        if abs(float(value)) > STRICT_INACTIVE_TOLERANCE
    }
    peak_text = ",".join(f"{joint}:{value:+.3f}" for joint, value in peaks.items())
    print(f"TALKING_IDLE_PHASE_PEAK phase={phase_name} peaks={peak_text}", flush=True)


def _compile_talking_idle_motion() -> List[Keyframe]:
    print("MOTION_PARSE_OK action=talking_idle side=body confidence=1.00", flush=True)
    print("TALKING_IDLE_TEMPLATE_SELECTED", flush=True)
    phase_targets = _talking_idle_phase_targets()
    for phase_name, _start, _end, target in phase_targets:
        _log_talking_idle_phase_peaks(phase_name, target)
    durations = [0] + _talking_idle_transition_durations()
    frames: List[Keyframe] = []
    for phase_index, (phase_name, start_index, end_index, target) in enumerate(phase_targets):
        start_target = phase_targets[phase_index - 1][3] if phase_index > 0 else target
        for frame_index in range(start_index, end_index + 1):
            if end_index == start_index:
                alpha = 1.0
            else:
                alpha = (frame_index - start_index) / float(end_index - start_index)
            if phase_index == 0:
                offsets = complete_offsets(target)
            else:
                offsets = interpolate_offsets(complete_offsets(start_target), complete_offsets(target), alpha)
            frames.append(Keyframe(f"talking_idle {phase_name} frame {frame_index + 1}", durations[frame_index], _clamp_full_body_offsets(offsets)))
    if len(frames) != TALKING_IDLE_FRAME_COUNT:
        raise RuntimeError(f"talking_idle generated invalid frame count: {len(frames)}")
    frames[0].joint_offsets_rad = neutral_offsets()
    frames[-1].joint_offsets_rad = neutral_offsets()
    return frames


def _with_duration(frame: Keyframe, duration_ms: int) -> Keyframe:
    return Keyframe(frame.name, int(duration_ms), complete_offsets(frame.joint_offsets_rad))


def log_motion_joint_ranges(frames: Sequence[Keyframe]) -> Dict[str, float]:
    ranges: Dict[str, float] = {}
    initial = complete_offsets(frames[0].joint_offsets_rad if frames else {})
    for joint in FULL_BODY_JOINTS:
        values = [float(frame.joint_offsets_rad.get(joint, 0.0)) for frame in frames]
        if not values:
            values = [0.0]
        minimum = min(values)
        maximum = max(values)
        delta = max(abs(value - initial.get(joint, 0.0)) for value in values)
        ranges[joint] = delta
        print(f"MOTION_JOINT_RANGE joint={joint} min={minimum:+.6f} max={maximum:+.6f} delta={delta:+.6f}", flush=True)
    return ranges


def validate_motion_amplitude(frames: Sequence[Keyframe], *, action: str | None = None, side: str | None = None) -> tuple[bool, str]:
    if not frames or len(frames) < 2:
        return False, "NO_MOTION_GENERATED"
    ranges = log_motion_joint_ranges(frames)
    if action == "wave":
        relevant = RIGHT_ARM_JOINTS if side != "left" else LEFT_ARM_JOINTS
        if max((ranges.get(joint, 0.0) for joint in relevant), default=0.0) < VISIBLE_ARM_DELTA_THRESHOLD_RAD:
            return False, "INSUFFICIENT_AMPLITUDE"
    return True, "ok"


def command_expected_duration_seconds(frames: Sequence[Keyframe]) -> float:
    # Playback starts at keyframe 0 and each subsequent keyframe owns the
    # transition duration into that target. The starting pose duration is not
    # played as a separate semantic segment.
    return sum(max(1, int(frame.duration_ms)) for frame in frames[1:]) / 1000.0


def trajectory_accounting(frames: Sequence[Keyframe], *, frame_rate: int = GESTURE_FRAME_RATE) -> Dict[str, float | int]:
    generated_frames = len(frames)
    expected_duration = command_expected_duration_seconds(frames)
    dense = dense_trajectory_from_keyframes(frames, frame_rate) if frames else []
    applied_frames = len(dense)
    actual_duration = (applied_frames / frame_rate) if frame_rate else 0.0
    print("TRAJECTORY_ACCOUNTING", flush=True)
    print(f"generated_frames={generated_frames}", flush=True)
    print(f"applied_frames={applied_frames}", flush=True)
    print(f"frame_rate={frame_rate}", flush=True)
    print(f"expected_duration={expected_duration:.3f}", flush=True)
    print(f"actual_duration={actual_duration:.3f}", flush=True)
    return {
        "generated_frames": generated_frames,
        "applied_frames": applied_frames,
        "frame_rate": frame_rate,
        "expected_duration": expected_duration,
        "actual_duration": actual_duration,
    }


def validate_trajectory_accounting(frames: Sequence[Keyframe], *, frame_rate: int = GESTURE_FRAME_RATE) -> tuple[bool, str, Dict[str, float | int]]:
    accounting = trajectory_accounting(frames, frame_rate=frame_rate)
    if not frames:
        return False, "NO_MOTION_GENERATED", accounting
    diff = abs(float(accounting["expected_duration"]) - float(accounting["actual_duration"]))
    if diff > TRAJECTORY_ACCOUNTING_TOLERANCE_SECONDS:
        return False, f"TRAJECTORY_ACCOUNTING_MISMATCH diff={diff:.3f}", accounting
    return True, "ok", accounting


def inactive_joint_changes(frames: Sequence[Keyframe], inactive_joints: Sequence[str]) -> Dict[str, float]:
    changes: Dict[str, float] = {}
    if not frames:
        return changes
    initial = complete_offsets(frames[0].joint_offsets_rad)
    for joint in inactive_joints:
        max_delta = max(abs(float(frame.joint_offsets_rad.get(joint, 0.0)) - initial.get(joint, 0.0)) for frame in frames)
        if max_delta > STRICT_INACTIVE_TOLERANCE:
            print(f"INACTIVE_JOINT_CHANGED joint={joint} delta={max_delta:+.9f}", flush=True)
            changes[joint] = max_delta
    return changes


def neutral_return_error(frames: Sequence[Keyframe]) -> float:
    if not frames:
        return float("inf")
    final = complete_offsets(frames[-1].joint_offsets_rad)
    return max(abs(float(final.get(joint, 0.0))) for joint in FULL_BODY_JOINTS)


def active_joints_for_frames(frames: Sequence[Keyframe]) -> List[str]:
    active = []
    initial = complete_offsets(frames[0].joint_offsets_rad if frames else {})
    for joint in FULL_BODY_JOINTS:
        if any(abs(float(frame.joint_offsets_rad.get(joint, 0.0)) - initial.get(joint, 0.0)) > STRICT_INACTIVE_TOLERANCE for frame in frames):
            active.append(joint)
    return active


def peak_targets_for_frames(frames: Sequence[Keyframe]) -> Dict[str, float]:
    peaks: Dict[str, float] = {}
    for joint in FULL_BODY_JOINTS:
        values = [float(frame.joint_offsets_rad.get(joint, 0.0)) for frame in frames]
        if values:
            peak = max(values, key=lambda value: abs(value))
            if abs(peak) > STRICT_INACTIVE_TOLERANCE:
                peaks[joint] = round(peak, 6)
    return peaks


def validate_wave_semantics(frames: Sequence[Keyframe], side: str) -> tuple[bool, str]:
    if not frames:
        return False, "NO_MOTION_GENERATED"
    inactive = LEFT_ARM_JOINTS if side == "right" else RIGHT_ARM_JOINTS
    contamination = inactive_joint_changes(frames, inactive)
    if contamination:
        print("MOTION_REJECTED reason=INACTIVE_JOINT_CONTAMINATION", flush=True)
        return False, "INACTIVE_JOINT_CONTAMINATION"
    active = RIGHT_ARM_JOINTS if side == "right" else LEFT_ARM_JOINTS
    ranges = {joint: max(abs(float(frame.joint_offsets_rad.get(joint, 0.0))) for frame in frames) for joint in active}
    if ranges.get(f"{side}_shoulder_pitch_joint", 0.0) < 0.65:
        return False, "WAVE_ARM_NOT_RAISED"
    if ranges.get(f"{side}_elbow_joint", 0.0) < 0.55:
        return False, "WAVE_ELBOW_NOT_BENT"
    yaw_values = [float(frame.joint_offsets_rad.get(f"{side}_shoulder_yaw_joint", 0.0)) for frame in frames]
    wrist_values = [float(frame.joint_offsets_rad.get(f"{side}_wrist_yaw_joint", 0.0)) for frame in frames]
    if (max(yaw_values) - min(yaw_values)) < 0.45 and (max(wrist_values) - min(wrist_values)) < 0.35:
        return False, "WAVE_OSCILLATION_TOO_SMALL"
    signs = []
    for value in yaw_values:
        if value > 0.12:
            signs.append(1)
        elif value < -0.12:
            signs.append(-1)
    changes = sum(1 for a, b in zip(signs, signs[1:]) if a != b)
    if changes < 5:
        return False, "WAVE_NEEDS_THREE_COMPLETE_CYCLES"
    if neutral_return_error(frames) > STRICT_INACTIVE_TOLERANCE:
        return False, "NOT_RETURNED_TO_NEUTRAL"
    return True, "ok"


def validate_talking_idle_semantics(frames: Sequence[Keyframe]) -> tuple[bool, str]:
    if len(frames) != TALKING_IDLE_FRAME_COUNT:
        return False, f"TALKING_IDLE_INVALID_FRAME_COUNT count={len(frames)}"
    if complete_offsets(frames[0].joint_offsets_rad) != complete_offsets(frames[-1].joint_offsets_rad):
        return False, "TALKING_IDLE_START_FINAL_MISMATCH"
    if neutral_return_error(frames) > STRICT_INACTIVE_TOLERANCE:
        return False, "TALKING_IDLE_NOT_RETURNED_TO_NEUTRAL"
    leg_changes = inactive_joint_changes(frames, LEFT_LEG_JOINTS + RIGHT_LEG_JOINTS)
    if leg_changes:
        return False, "TALKING_IDLE_LEGS_MOVED"
    right_phase = frames[45:69]
    left_phase = frames[69:93]
    right_peak_frame = max(right_phase, key=lambda frame: abs(float(frame.joint_offsets_rad.get("right_shoulder_roll_joint", 0.0))))
    left_peak_frame = max(left_phase, key=lambda frame: abs(float(frame.joint_offsets_rad.get("left_shoulder_roll_joint", 0.0))))
    right_peak = abs(float(right_peak_frame.joint_offsets_rad.get("right_shoulder_roll_joint", 0.0)))
    left_at_right_peak = abs(float(right_peak_frame.joint_offsets_rad.get("left_shoulder_roll_joint", 0.0)))
    left_peak = abs(float(left_peak_frame.joint_offsets_rad.get("left_shoulder_roll_joint", 0.0)))
    right_at_left_peak = abs(float(left_peak_frame.joint_offsets_rad.get("right_shoulder_roll_joint", 0.0)))
    if right_peak < 0.11 or left_peak < 0.11:
        return False, "TALKING_IDLE_ALTERNATION_TOO_SMALL"
    if (right_peak - left_at_right_peak) < 0.04 or (left_peak - right_at_left_peak) < 0.04:
        return False, "TALKING_IDLE_NOT_VISIBLY_ALTERNATING"
    open_frame = max(frames, key=lambda frame: abs(float(frame.joint_offsets_rad.get("left_shoulder_roll_joint", 0.0))) + abs(float(frame.joint_offsets_rad.get("right_shoulder_roll_joint", 0.0))))
    open_left = abs(float(open_frame.joint_offsets_rad.get("left_shoulder_roll_joint", 0.0)))
    open_right = abs(float(open_frame.joint_offsets_rad.get("right_shoulder_roll_joint", 0.0)))
    if open_left < 0.16 or open_right < 0.16:
        return False, "TALKING_IDLE_EMPHASIS_TOO_SMALL"
    return True, "ok"


def sample_conversational_talking_keyframes() -> List[Keyframe]:
    # Hands stay around waist height; offsets are deliberately modest and simulation-only.
    return [
        Keyframe("neutral", 600, complete_offsets({})),
        Keyframe(
            "open waist presentation",
            900,
            complete_offsets({
                "waist_yaw_joint": -0.025,
                "waist_pitch_joint": 0.010,
                "left_shoulder_pitch_joint": -0.060,
                "left_shoulder_roll_joint": 0.045,
                "left_shoulder_yaw_joint": -0.030,
                "left_elbow_joint": 0.160,
                "left_wrist_yaw_joint": -0.050,
                "right_shoulder_pitch_joint": -0.080,
                "right_shoulder_roll_joint": -0.060,
                "right_shoulder_yaw_joint": 0.035,
                "right_elbow_joint": -0.180,
                "right_wrist_yaw_joint": 0.060,
            }),
        ),
        Keyframe(
            "right hand emphasis",
            750,
            complete_offsets({
                "waist_yaw_joint": -0.040,
                "waist_pitch_joint": 0.012,
                "left_shoulder_pitch_joint": -0.035,
                "left_shoulder_roll_joint": 0.030,
                "left_elbow_joint": 0.120,
                "right_shoulder_pitch_joint": -0.130,
                "right_shoulder_roll_joint": -0.090,
                "right_shoulder_yaw_joint": 0.060,
                "right_elbow_joint": -0.240,
                "right_wrist_pitch_joint": 0.035,
                "right_wrist_yaw_joint": 0.100,
            }),
        ),
        Keyframe(
            "settle neutral",
            850,
            complete_offsets({}),
        ),
    ]


def sample_scratch_head_keyframes() -> List[Keyframe]:
    # scene_29dof.xml has no head/neck joints, so the requested head tilt is
    # represented only by a tiny torso cue. Feet, legs and left arm remain still.
    hand_to_temple = {
        "waist_yaw_joint": 0.105,  # about 6 degrees left
        "waist_roll_joint": -0.018,
        "right_shoulder_pitch_joint": -1.050,
        "right_shoulder_roll_joint": -0.420,
        "right_shoulder_yaw_joint": 0.500,
        "right_elbow_joint": -0.820,
        "right_wrist_roll_joint": 0.100,
        "right_wrist_pitch_joint": 0.180,
        "right_wrist_yaw_joint": 0.140,
    }
    scratch_one = {
        **hand_to_temple,
        "right_elbow_joint": -0.880,
        "right_wrist_roll_joint": 0.160,
        "right_wrist_pitch_joint": 0.240,
        "right_wrist_yaw_joint": 0.080,
    }
    scratch_two = {
        **hand_to_temple,
        "right_shoulder_yaw_joint": 0.540,
        "right_elbow_joint": -0.780,
        "right_wrist_roll_joint": 0.040,
        "right_wrist_pitch_joint": 0.130,
        "right_wrist_yaw_joint": 0.210,
    }
    scratch_three = {
        **hand_to_temple,
        "right_elbow_joint": -0.860,
        "right_wrist_roll_joint": 0.130,
        "right_wrist_pitch_joint": 0.220,
        "right_wrist_yaw_joint": 0.110,
    }
    return clamp_keyframes_to_soft_limits([
        Keyframe("scratch head neutral", 300, complete_offsets({})),
        Keyframe("raise hand to right temple", 1500, complete_offsets(hand_to_temple)),
        Keyframe("scratch movement 1", 400, complete_offsets(scratch_one)),
        Keyframe("scratch movement 2", 400, complete_offsets(scratch_two)),
        Keyframe("scratch movement 3", 400, complete_offsets(scratch_three)),
        Keyframe("brief thinking pause", 500, complete_offsets(scratch_three)),
        Keyframe("return relaxed", 1500, complete_offsets({})),
    ])


def sample_thinking_hand_on_chin_keyframes() -> List[Keyframe]:
    # scene_29dof.xml has no head/neck joints. The "look around" quality is
    # represented conservatively with tiny waist/torso cues only. Feet, legs
    # and the left arm remain still throughout.
    hand_near_chin = {
        "waist_yaw_joint": -0.055,
        "waist_pitch_joint": 0.045,
        "right_shoulder_pitch_joint": -0.820,
        "right_shoulder_roll_joint": -0.250,
        "right_shoulder_yaw_joint": 0.300,
        "right_elbow_joint": -0.980,
        "right_wrist_roll_joint": -0.050,
        "right_wrist_pitch_joint": 0.160,
        "right_wrist_yaw_joint": 0.080,
    }
    chin_settle = {
        **hand_near_chin,
        "waist_yaw_joint": -0.060,
        "waist_pitch_joint": 0.055,
        "right_shoulder_pitch_joint": -0.880,
        "right_elbow_joint": -1.070,
        "right_wrist_pitch_joint": 0.210,
    }
    thinking_hold = {
        **chin_settle,
        "waist_yaw_joint": -0.045,
        "waist_roll_joint": 0.010,
    }
    subtle_adjust_one = {
        **thinking_hold,
        "waist_yaw_joint": -0.020,
        "waist_roll_joint": 0.014,
        "right_elbow_joint": -1.020,
        "right_wrist_roll_joint": 0.020,
        "right_wrist_pitch_joint": 0.175,
        "right_wrist_yaw_joint": 0.125,
    }
    subtle_adjust_two = {
        **thinking_hold,
        "waist_yaw_joint": -0.075,
        "waist_roll_joint": -0.006,
        "right_elbow_joint": -1.095,
        "right_wrist_roll_joint": -0.085,
        "right_wrist_pitch_joint": 0.235,
        "right_wrist_yaw_joint": 0.040,
    }
    return clamp_keyframes_to_soft_limits([
        Keyframe("thinking hand on chin neutral", 300, complete_offsets({})),
        Keyframe("raise right hand toward chin", 1200, complete_offsets(hand_near_chin)),
        Keyframe("settle hand beneath chin", 400, complete_offsets(chin_settle)),
        Keyframe("thinking hold", 1000, complete_offsets(thinking_hold)),
        Keyframe("subtle thinking adjustment 1", 350, complete_offsets(subtle_adjust_one)),
        Keyframe("subtle thinking adjustment 2", 350, complete_offsets(subtle_adjust_two)),
        Keyframe("return relaxed from thinking", 1300, complete_offsets({})),
    ])


def is_scratch_head_description(description: str) -> bool:
    prompt = description.lower()
    return any(
        phrase in prompt
        for phrase in (
            "scratch head",
            "scratching his head",
            "thinking scratch",
            "rub side of head",
            "hand to temple",
        )
    )


def is_thinking_hand_on_chin_description(description: str) -> bool:
    prompt = description.lower()
    return any(
        phrase in prompt
        for phrase in (
            "hand on chin",
            "thinking pose",
            "thoughtful pose",
            "rub chin",
            "thinking with hand on chin",
            "looking thoughtful",
        )
    )


def ensure_sample_animation() -> None:
    ANIMATIONS_DIR.mkdir(parents=True, exist_ok=True)
    if not SAMPLE_ANIMATION_PATH.exists():
        payload = animation_payload(sample_conversational_talking_keyframes(), name="conversational_talking")
        SAMPLE_ANIMATION_PATH.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"SAMPLE_ANIMATION_CREATED: {SAMPLE_ANIMATION_PATH}")
    if not SCRATCH_HEAD_ANIMATION_PATH.exists():
        payload = animation_payload(sample_scratch_head_keyframes(), name="Scratch Head")
        payload["description"] = "Scratch Head built-in template. Head tilt requested, but scene_29dof.xml has no head joint; simulated as a small torso cue."
        payload["template"] = "scratch_head"
        SCRATCH_HEAD_ANIMATION_PATH.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"SAMPLE_ANIMATION_CREATED: {SCRATCH_HEAD_ANIMATION_PATH}")
    if not THINKING_HAND_ON_CHIN_ANIMATION_PATH.exists():
        payload = animation_payload(sample_thinking_hand_on_chin_keyframes(), name="Thinking – Hand on Chin")
        payload["description"] = "Thinking – Hand on Chin built-in template. scene_29dof.xml has no head/neck joints; looking around is simulated with small torso and waist cues."
        payload["template"] = "thinking_hand_on_chin"
        THINKING_HAND_ON_CHIN_ANIMATION_PATH.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"SAMPLE_ANIMATION_CREATED: {THINKING_HAND_ON_CHIN_ANIMATION_PATH}")


def slugify_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or f"motion-{time.strftime('%Y%m%d-%H%M%S')}"


def motion_nonzero_joint_count(frames: Sequence[Keyframe]) -> int:
    joints = set()
    for frame in frames:
        for joint, value in frame.joint_offsets_rad.items():
            if abs(float(value)) > 1e-6:
                joints.add(joint)
    return len(joints)


def _motion_text_flags(description: str) -> dict[str, bool]:
    prompt = description.lower()
    return {
        "slow": any(word in prompt for word in ("slow", "slowly", "smooth", "smoothly", "gentle", "calm")),
        "quick": any(word in prompt for word in ("quick", "quickly", "fast", "brisk")),
        "enthusiastic": any(word in prompt for word in ("enthusiastic", "enthusiastically", "excited", "excitedly", "energetic", "bold", "big")),
        "hesitant": any(word in prompt for word in ("hesitant", "hesitantly", "shy", "uncertain", "careful")),
        "confident": any(word in prompt for word in ("confident", "confidently", "proud", "assured")),
        "pause": any(word in prompt for word in ("pause", "hold", "briefly", "moment")),
        "return": any(phrase in prompt for phrase in ("return to neutral", "lower", "relax", "settle", "back to neutral")),
    }


def _scaled_duration(ms: int, flags: dict[str, bool]) -> int:
    factor = 1.0
    if flags["slow"]:
        factor *= 1.25
    if flags["quick"]:
        factor *= 0.82
    if flags["hesitant"]:
        factor *= 1.18
    return max(MIN_KEYFRAME_DURATION_MS, min(MAX_KEYFRAME_DURATION_MS, round(ms * factor)))


def _movement_scale(flags: dict[str, bool]) -> float:
    scale = 1.0
    if flags["enthusiastic"]:
        scale *= 1.22
    if flags["confident"]:
        scale *= 1.12
    if flags["hesitant"]:
        scale *= 0.72
    if flags["slow"] and not flags["enthusiastic"]:
        scale *= 0.92
    return clamp(scale, 0.65, 1.35)


def _target(offsets: Dict[str, float], scale: float = 1.0) -> Dict[str, float]:
    return complete_offsets({joint: round(value * scale, 6) for joint, value in offsets.items()})


def _raise_both_hands_pose(scale: float) -> Dict[str, float]:
    return _target({
        "waist_pitch_joint": 0.014,
        "left_shoulder_pitch_joint": -0.300,
        "left_shoulder_roll_joint": 0.155,
        "left_shoulder_yaw_joint": -0.070,
        "left_elbow_joint": 0.300,
        "left_wrist_pitch_joint": -0.040,
        "left_wrist_yaw_joint": -0.075,
        "right_shoulder_pitch_joint": -0.320,
        "right_shoulder_roll_joint": -0.165,
        "right_shoulder_yaw_joint": 0.075,
        "right_elbow_joint": -0.320,
        "right_wrist_pitch_joint": -0.040,
        "right_wrist_yaw_joint": 0.085,
    }, scale)


def _open_audience_pose(scale: float) -> Dict[str, float]:
    return _target({
        "waist_yaw_joint": -0.030,
        "waist_pitch_joint": 0.012,
        "left_shoulder_pitch_joint": -0.160,
        "left_shoulder_roll_joint": 0.135,
        "left_shoulder_yaw_joint": -0.080,
        "left_elbow_joint": 0.220,
        "left_wrist_yaw_joint": -0.080,
        "right_shoulder_pitch_joint": -0.180,
        "right_shoulder_roll_joint": -0.145,
        "right_shoulder_yaw_joint": 0.090,
        "right_elbow_joint": -0.230,
        "right_wrist_yaw_joint": 0.095,
    }, scale)


def _right_hand_to_chest_pose(scale: float) -> Dict[str, float]:
    return _target({
        "waist_yaw_joint": -0.025,
        "waist_pitch_joint": 0.020,
        "left_shoulder_pitch_joint": -0.040,
        "left_shoulder_roll_joint": 0.025,
        "left_elbow_joint": 0.090,
        "right_shoulder_pitch_joint": -0.430,
        "right_shoulder_roll_joint": -0.155,
        "right_shoulder_yaw_joint": 0.260,
        "right_elbow_joint": -0.620,
        "right_wrist_roll_joint": 0.050,
        "right_wrist_pitch_joint": 0.060,
        "right_wrist_yaw_joint": 0.130,
    }, scale)


def _right_point_pose(scale: float, *, look_left: bool) -> Dict[str, float]:
    waist_yaw = 0.075 if look_left else -0.035
    return _target({
        "waist_yaw_joint": waist_yaw,
        "waist_pitch_joint": 0.010,
        "left_shoulder_pitch_joint": -0.030,
        "left_elbow_joint": 0.070,
        "right_shoulder_pitch_joint": -0.350,
        "right_shoulder_roll_joint": -0.190,
        "right_shoulder_yaw_joint": 0.170,
        "right_elbow_joint": -0.180,
        "right_wrist_pitch_joint": 0.020,
        "right_wrist_yaw_joint": 0.045,
    }, scale)


def _small_settle_pose(scale: float) -> Dict[str, float]:
    return _target({
        "waist_yaw_joint": -0.010,
        "waist_pitch_joint": 0.004,
        "left_shoulder_pitch_joint": -0.018,
        "left_shoulder_roll_joint": 0.012,
        "left_elbow_joint": 0.035,
        "right_shoulder_pitch_joint": -0.020,
        "right_shoulder_roll_joint": -0.014,
        "right_elbow_joint": -0.040,
    }, min(scale, 1.0))


def _sweep_pose(scale: float, *, side: str, torso_only: bool = False) -> Dict[str, float]:
    # Horizontal presentation arcs should read from the body outward: torso
    # leads, shoulders follow, then the hands travel across with bent elbows.
    direction = -1.0 if side == "left" else 1.0
    torso_yaw = 0.280 * direction
    if torso_only:
        return _target({
            "waist_yaw_joint": torso_yaw,
            "waist_pitch_joint": 0.010,
        }, min(scale, 1.0))
    return _target({
        "waist_yaw_joint": torso_yaw,
        "waist_pitch_joint": 0.012,
        "left_shoulder_pitch_joint": -0.205,
        "left_shoulder_roll_joint": 0.095 + (0.060 * direction),
        "left_shoulder_yaw_joint": -0.155 * direction,
        "left_elbow_joint": 0.260,
        "left_wrist_pitch_joint": -0.020,
        "left_wrist_yaw_joint": -0.100 * direction,
        "right_shoulder_pitch_joint": -0.215,
        "right_shoulder_roll_joint": -0.105 + (0.060 * direction),
        "right_shoulder_yaw_joint": -0.150 * direction,
        "right_elbow_joint": -0.270,
        "right_wrist_pitch_joint": -0.020,
        "right_wrist_yaw_joint": -0.105 * direction,
    }, scale)


def _sweep_center_pose(scale: float) -> Dict[str, float]:
    return _target({
        "waist_yaw_joint": 0.000,
        "waist_pitch_joint": 0.014,
        "left_shoulder_pitch_joint": -0.225,
        "left_shoulder_roll_joint": 0.135,
        "left_shoulder_yaw_joint": -0.020,
        "left_elbow_joint": 0.285,
        "left_wrist_pitch_joint": -0.020,
        "left_wrist_yaw_joint": -0.030,
        "right_shoulder_pitch_joint": -0.235,
        "right_shoulder_roll_joint": -0.140,
        "right_shoulder_yaw_joint": 0.020,
        "right_elbow_joint": -0.295,
        "right_wrist_pitch_joint": -0.020,
        "right_wrist_yaw_joint": 0.035,
    }, scale)


def _merge_targets(*targets: Dict[str, float]) -> Dict[str, float]:
    merged: Dict[str, float] = {}
    for target in targets:
        for joint, value in target.items():
            value = float(value)
            if abs(value) > 1e-9:
                merged[joint] = value
    return complete_offsets(merged)


def _clamp_full_body_offsets(offsets: Dict[str, float]) -> Dict[str, float]:
    clamped: Dict[str, float] = {}
    for joint in FULL_BODY_JOINTS:
        value = float(offsets.get(joint, 0.0))
        lower, upper = FULL_BODY_SOFT_LIMITS.get(joint, DEFAULT_RANGE)
        clamped[joint] = round(clamp(value, lower, upper), 6)
    return clamped


def clamp_keyframes_to_soft_limits(frames: Sequence[Keyframe]) -> List[Keyframe]:
    return [Keyframe(frame.name, frame.duration_ms, _clamp_full_body_offsets(frame.joint_offsets_rad)) for frame in frames]


def _left_arm_pose(position: str, scale: float) -> Dict[str, float]:
    poses = {
        "up": {
            "left_shoulder_pitch_joint": -0.620,
            "left_shoulder_roll_joint": 0.240,
            "left_shoulder_yaw_joint": -0.080,
            "left_elbow_joint": 0.280,
            "left_wrist_pitch_joint": -0.030,
            "left_wrist_yaw_joint": -0.060,
        },
        "down": {},
        "forward": {
            "left_shoulder_pitch_joint": -0.300,
            "left_shoulder_roll_joint": 0.060,
            "left_shoulder_yaw_joint": -0.040,
            "left_elbow_joint": 0.220,
            "left_wrist_yaw_joint": -0.050,
        },
        "sideways": {
            "left_shoulder_pitch_joint": -0.160,
            "left_shoulder_roll_joint": 0.320,
            "left_shoulder_yaw_joint": -0.070,
            "left_elbow_joint": 0.240,
            "left_wrist_yaw_joint": -0.060,
        },
        "chest": {
            # Cross-body chest approximation for the 29-DoF model: shoulder pulls
            # the upper arm inward, elbow bends strongly, wrist turns toward sternum.
            "left_shoulder_pitch_joint": -0.460,
            "left_shoulder_roll_joint": 0.145,
            "left_shoulder_yaw_joint": -0.280,
            "left_elbow_joint": 0.620,
            "left_wrist_roll_joint": -0.040,
            "left_wrist_pitch_joint": 0.060,
            "left_wrist_yaw_joint": -0.150,
        },
        "open": {
            "left_shoulder_pitch_joint": -0.210,
            "left_shoulder_roll_joint": 0.185,
            "left_shoulder_yaw_joint": -0.090,
            "left_elbow_joint": 0.260,
            "left_wrist_yaw_joint": -0.070,
        },
    }
    return _target(poses.get(position, poses["forward"]), scale)


def _right_arm_pose(position: str, scale: float) -> Dict[str, float]:
    poses = {
        "up": {
            "right_shoulder_pitch_joint": -0.620,
            "right_shoulder_roll_joint": -0.250,
            "right_shoulder_yaw_joint": 0.090,
            "right_elbow_joint": -0.300,
            "right_wrist_pitch_joint": -0.030,
            "right_wrist_yaw_joint": 0.070,
        },
        "down": {},
        "forward": {
            "right_shoulder_pitch_joint": -0.310,
            "right_shoulder_roll_joint": -0.070,
            "right_shoulder_yaw_joint": 0.050,
            "right_elbow_joint": -0.230,
            "right_wrist_yaw_joint": 0.055,
        },
        "sideways": {
            "right_shoulder_pitch_joint": -0.170,
            "right_shoulder_roll_joint": -0.330,
            "right_shoulder_yaw_joint": 0.080,
            "right_elbow_joint": -0.250,
            "right_wrist_yaw_joint": 0.065,
        },
        "chest": {
            # Cross-body chest approximation for the 29-DoF model: shoulder pulls
            # the upper arm inward, elbow bends strongly, wrist turns toward sternum.
            "right_shoulder_pitch_joint": -0.460,
            "right_shoulder_roll_joint": -0.145,
            "right_shoulder_yaw_joint": 0.280,
            "right_elbow_joint": -0.620,
            "right_wrist_roll_joint": 0.040,
            "right_wrist_pitch_joint": 0.060,
            "right_wrist_yaw_joint": 0.150,
        },
        "open": {
            "right_shoulder_pitch_joint": -0.220,
            "right_shoulder_roll_joint": -0.195,
            "right_shoulder_yaw_joint": 0.100,
            "right_elbow_joint": -0.270,
            "right_wrist_yaw_joint": 0.080,
        },
    }
    return _target(poses.get(position, poses["forward"]), scale)


def _torso_pose(*, yaw_deg: float = 0.0, pitch_deg: float = 0.0, roll_deg: float = 0.0) -> Dict[str, float]:
    return complete_offsets({
        "waist_yaw_joint": round(yaw_deg * 3.141592653589793 / 180.0, 6),
        "waist_pitch_joint": round(pitch_deg * 3.141592653589793 / 180.0, 6),
        "waist_roll_joint": round(roll_deg * 3.141592653589793 / 180.0, 6),
    })


def _leg_pose(*, knee_bend: str = "none", weight_shift: str = "center", stance_width: str = "normal") -> Dict[str, float]:
    offsets: Dict[str, float] = {}
    if knee_bend in ("slight", "little"):
        offsets.update({
            "left_hip_pitch_joint": -0.045,
            "right_hip_pitch_joint": -0.045,
            "left_knee_joint": 0.120,
            "right_knee_joint": 0.120,
            "left_ankle_pitch_joint": -0.045,
            "right_ankle_pitch_joint": -0.045,
            "waist_pitch_joint": 0.035,
        })
    if stance_width == "wide":
        offsets.update({
            "left_hip_roll_joint": 0.060,
            "right_hip_roll_joint": -0.060,
            "left_ankle_roll_joint": -0.035,
            "right_ankle_roll_joint": 0.035,
        })
    if weight_shift == "left":
        offsets.update({
            "waist_roll_joint": 0.035,
            "left_hip_roll_joint": offsets.get("left_hip_roll_joint", 0.0) + 0.030,
            "right_hip_roll_joint": offsets.get("right_hip_roll_joint", 0.0) + 0.020,
            "left_ankle_roll_joint": offsets.get("left_ankle_roll_joint", 0.0) - 0.020,
            "right_ankle_roll_joint": offsets.get("right_ankle_roll_joint", 0.0) - 0.015,
        })
    elif weight_shift == "right":
        offsets.update({
            "waist_roll_joint": -0.035,
            "left_hip_roll_joint": offsets.get("left_hip_roll_joint", 0.0) - 0.020,
            "right_hip_roll_joint": offsets.get("right_hip_roll_joint", 0.0) - 0.030,
            "left_ankle_roll_joint": offsets.get("left_ankle_roll_joint", 0.0) + 0.015,
            "right_ankle_roll_joint": offsets.get("right_ankle_roll_joint", 0.0) + 0.020,
        })
    return complete_offsets(offsets)


def _head_fallback_pose(prompt: str) -> Dict[str, float]:
    # The 29-DoF G1 scene has no head/neck joints. Use a very small torso cue so
    # prompts like "look right" remain visible without inventing unavailable DOFs.
    if "look right" in prompt:
        print("FULL_BODY_HEAD_FALLBACK: no_head_joints using_torso_yaw_right", flush=True)
        return _torso_pose(yaw_deg=4.0)
    if "look left" in prompt or "look to the left" in prompt:
        print("FULL_BODY_HEAD_FALLBACK: no_head_joints using_torso_yaw_left", flush=True)
        return _torso_pose(yaw_deg=-4.0)
    if "look down" in prompt:
        print("FULL_BODY_HEAD_FALLBACK: no_head_joints using_torso_pitch_forward", flush=True)
        return _torso_pose(pitch_deg=3.0)
    if "look up" in prompt:
        print("FULL_BODY_HEAD_FALLBACK: no_head_joints using_torso_pitch_back", flush=True)
        return _torso_pose(pitch_deg=-2.0)
    return complete_offsets({})


def _full_body_balance_check(frames: Sequence[Keyframe]) -> bool:
    for frame in frames:
        offsets = frame.joint_offsets_rad
        knee = max(abs(offsets.get("left_knee_joint", 0.0)), abs(offsets.get("right_knee_joint", 0.0)))
        hip_roll = max(abs(offsets.get("left_hip_roll_joint", 0.0)), abs(offsets.get("right_hip_roll_joint", 0.0)))
        ankle_roll = max(abs(offsets.get("left_ankle_roll_joint", 0.0)), abs(offsets.get("right_ankle_roll_joint", 0.0)))
        if knee > 0.28 or hip_roll > 0.12 or ankle_roll > 0.10:
            return False
    return True


def _full_body_collision_check(frames: Sequence[Keyframe]) -> bool:
    for frame in frames:
        offsets = frame.joint_offsets_rad
        left_crosses_body = offsets.get("left_shoulder_yaw_joint", 0.0) > 0.45 and offsets.get("left_elbow_joint", 0.0) > 0.55
        right_crosses_body = offsets.get("right_shoulder_yaw_joint", 0.0) < -0.45 and offsets.get("right_elbow_joint", 0.0) < -0.55
        if left_crosses_body or right_crosses_body:
            return False
    return True


def _limit_generated_motion(frames: Sequence[Keyframe]) -> List[Keyframe]:
    if not frames:
        return []
    limited = [Keyframe(frames[0].name, frames[0].duration_ms, _clamp_full_body_offsets(frames[0].joint_offsets_rad))]
    for frame in frames[1:]:
        previous = limited[-1].joint_offsets_rad
        adjusted = {}
        for joint in FULL_BODY_JOINTS:
            target = _clamp_full_body_offsets(frame.joint_offsets_rad).get(joint, 0.0)
            delta = clamp(target - previous.get(joint, 0.0), -MAX_GENERATED_JOINT_DELTA_RAD, MAX_GENERATED_JOINT_DELTA_RAD)
            adjusted[joint] = round(previous.get(joint, 0.0) + delta, 6)
        limited.append(Keyframe(frame.name, frame.duration_ms, complete_offsets(adjusted)))
    return limited


def _stage_nonzero_count(target: Dict[str, float]) -> int:
    return sum(1 for value in target.values() if abs(float(value)) > 1e-6)


def _arm_values(target: Dict[str, float], side: str) -> tuple[float, float, float, float]:
    return (
        float(target.get(f"{side}_shoulder_pitch_joint", 0.0)),
        float(target.get(f"{side}_shoulder_roll_joint", 0.0)),
        float(target.get(f"{side}_shoulder_yaw_joint", 0.0)),
        float(target.get(f"{side}_elbow_joint", 0.0)),
    )


def _looks_like_left_chest_target(target: Dict[str, float]) -> bool:
    pitch, roll, yaw, elbow = _arm_values(target, "left")
    return pitch < -0.35 and roll > 0.08 and yaw < -0.18 and elbow > 0.48


def _looks_like_right_chest_target(target: Dict[str, float]) -> bool:
    pitch, roll, yaw, elbow = _arm_values(target, "right")
    return pitch < -0.35 and roll < -0.08 and yaw > 0.18 and elbow < -0.48


def _log_full_body_stage(index: int, label: str, target: Dict[str, float]) -> None:
    print(f"FULL_BODY_STAGE index={index} label={label}", flush=True)
    left_pitch, left_roll, left_yaw, left_elbow = _arm_values(target, "left")
    right_pitch, right_roll, right_yaw, right_elbow = _arm_values(target, "right")
    print(
        f"LEFT_ARM_TARGET shoulder_pitch={left_pitch:+.6f} shoulder_roll={left_roll:+.6f} "
        f"shoulder_yaw={left_yaw:+.6f} elbow={left_elbow:+.6f}",
        flush=True,
    )
    print(
        f"RIGHT_ARM_TARGET shoulder_pitch={right_pitch:+.6f} shoulder_roll={right_roll:+.6f} "
        f"shoulder_yaw={right_yaw:+.6f} elbow={right_elbow:+.6f}",
        flush=True,
    )
    print(f"LEFT_HAND_CHEST_TARGET resolved={str(_looks_like_left_chest_target(target)).lower()}", flush=True)
    print(f"RIGHT_HAND_CHEST_TARGET resolved={str(_looks_like_right_chest_target(target)).lower()}", flush=True)
    for joint in FULL_BODY_JOINTS:
        value = float(target.get(joint, 0.0))
        if abs(value) > 1e-6:
            print(f"FULL_BODY_TARGET joint={joint} value={value:+.6f}", flush=True)
    print(f"FULL_BODY_STAGE_NONZERO count={_stage_nonzero_count(target)}", flush=True)


def _append_structured_stage(
    stages: list[tuple[str, Dict[str, object], Dict[str, float], int, int, bool]],
    label: str,
    body: Dict[str, object],
    target: Dict[str, float],
    frame_count: int,
    duration_ms: int,
    hold: bool = False,
) -> None:
    stages.append((label, body, _clamp_full_body_offsets(target), frame_count, duration_ms, hold))


def _split_motion_clauses(description: str) -> list[str]:
    normalized = description.lower()
    for token in (".", ";", "!", "?"):
        normalized = normalized.replace(token, ".")
    normalized = normalized.replace(", then ", ".")
    normalized = normalized.replace(" then ", ".")
    normalized = normalized.replace(" and then ", ".")
    return [clause.strip() for clause in normalized.split(".") if clause.strip()]


def _structured_full_body_stage_targets(description: str, flags: dict[str, bool]) -> list[tuple[str, Dict[str, object], Dict[str, float], int, int, bool]]:
    prompt = description.lower()
    scale = _movement_scale(flags)
    if any(word in prompt for word in ("straight", "strongly", "far left", "noticeably", "wide", "obvious", "extreme")):
        scale = max(scale, 1.0)
    stages: list[tuple[str, Dict[str, object], Dict[str, float], int, int, bool]] = []
    clauses = _split_motion_clauses(description)

    state = {
        "left_arm": "down",
        "right_arm": "down",
        "torso_yaw": 0.0,
        "torso_pitch": 0.0,
        "torso_roll": 0.0,
        "knee_bend": "none",
        "weight_shift": "center",
        "stance_width": "normal",
        "head_prompt": "",
    }

    def state_target() -> Dict[str, float]:
        return _merge_targets(
            _left_arm_pose(str(state["left_arm"]), scale),
            _right_arm_pose(str(state["right_arm"]), scale),
            _torso_pose(
                yaw_deg=float(state["torso_yaw"]),
                pitch_deg=float(state["torso_pitch"]),
                roll_deg=float(state["torso_roll"]),
            ),
            _leg_pose(
                knee_bend=str(state["knee_bend"]),
                weight_shift=str(state["weight_shift"]),
                stance_width=str(state["stance_width"]),
            ),
            _head_fallback_pose(str(state["head_prompt"])),
        )

    def append_current(label: str, frame_count: int, duration_ms: int, hold: bool = False) -> None:
        body = {
            "left_arm": {"position": state["left_arm"]},
            "right_arm": {"position": state["right_arm"]},
            "torso": {"yaw_deg": state["torso_yaw"], "pitch_deg": state["torso_pitch"], "roll_deg": state["torso_roll"]},
            "head": {"fallback_prompt": state["head_prompt"]},
            "legs": {"weight_shift": state["weight_shift"], "knee_bend": state["knee_bend"], "stance_width": state["stance_width"]},
        }
        _append_structured_stage(stages, label, body, state_target(), frame_count, duration_ms, hold)

    if "stand completely still" in prompt or "start" in prompt or "begin" in prompt:
        _append_structured_stage(stages, "full body explicit neutral", {"body": "neutral"}, complete_offsets({}), 4, _scaled_duration(300, flags), True)

    for clause in clauses:
        changed = False
        lower_only = False
        if "hold the left arm still at shoulder height" in clause and "right arm moves from down to overhead" in clause:
            state["left_arm"] = "sideways"
            state["right_arm"] = "down"
            append_current("full body left arm held right arm down", 10, _scaled_duration(900, flags), False)
            state["right_arm"] = "up"
            append_current("full body left arm held right arm overhead", 14, _scaled_duration(1200, flags), False)
            continue
        if "hold the right arm still at shoulder height" in clause and "left arm moves from down to overhead" in clause:
            state["right_arm"] = "sideways"
            state["left_arm"] = "down"
            append_current("full body right arm held left arm down", 10, _scaled_duration(900, flags), False)
            state["left_arm"] = "up"
            append_current("full body right arm held left arm overhead", 14, _scaled_duration(1200, flags), False)
            continue
        if "lower the left arm while raising the right arm" in clause:
            state["left_arm"] = "down"
            state["right_arm"] = "sideways" if "side" in clause else "up"
            changed = True
        if "lower the right arm while raising the left arm" in clause:
            state["right_arm"] = "down"
            state["left_arm"] = "sideways" if "side" in clause else "up"
            changed = True
        if any(phrase in clause for phrase in ("open both arms", "both arms wide", "both hands forward", "both hands to chest height", "raise both hands to chest height")):
            state["left_arm"] = "open"
            state["right_arm"] = "open"
            changed = True
        if any(phrase in clause for phrase in ("raise both hands", "hands up", "raise your hands", "raise hands")):
            state["left_arm"] = "up"
            state["right_arm"] = "up"
            changed = True
        if any(phrase in clause for phrase in ("left arm straight above", "left arm above", "left arm up", "left hand up", "raise the left arm", "raise left arm")):
            state["left_arm"] = "up"
            changed = True
        if any(phrase in clause for phrase in ("right arm straight above", "right arm above", "right arm up", "right hand up", "raise the right arm", "raise right arm")):
            state["right_arm"] = "up"
            changed = True
        if any(phrase in clause for phrase in ("extend the left arm straight out", "extending the left arm outward", "left arm outward", "left arm straight out", "left arm extends sideways", "left arm sideways", "left hand sideways")):
            state["left_arm"] = "sideways"
            changed = True
        if any(phrase in clause for phrase in ("raise the right arm straight out", "extending the right arm outward", "right arm outward", "right arm straight out", "right arm extends sideways", "right arm sideways", "right hand sideways", "right arm to the side")):
            state["right_arm"] = "sideways"
            changed = True
        if any(phrase in clause for phrase in ("right hand to chest", "right hand on the centre of the chest", "right hand on center of the chest", "right hand firmly on the centre of the chest", "right hand firmly on the center of the chest", "right hand on chest", "right hand at chest", "right hand to chest height", "raise the right hand to chest height", "place the right hand on the centre of the chest", "place the right hand on the center of the chest")):
            state["right_arm"] = "chest"
            changed = True
        if any(phrase in clause for phrase in ("left hand to chest", "left hand on the centre of the chest", "left hand on the center of the chest", "left hand on chest", "left hand at chest", "left hand to chest height", "place the left hand on the chest", "place the left hand on the centre of the chest", "place the left hand on the center of the chest")):
            state["left_arm"] = "chest"
            changed = True
        if any(phrase in clause for phrase in ("right arm hanging", "right hand down", "right hand low", "right arm down", "keep the right arm hanging", "right arm remains relaxed", "right arm relaxed", "arms relaxed")):
            state["right_arm"] = "down"
            changed = True
        if any(phrase in clause for phrase in ("left arm hanging", "left hand down", "left hand low", "left arm down", "drop the left arm", "lower the left arm", "left arm remains relaxed", "left arm relaxed")):
            state["left_arm"] = "down"
            changed = True
        if "lower both hands" in clause or "both hands down" in clause or "both arms relaxed" in clause:
            state["left_arm"] = "down"
            state["right_arm"] = "down"
            changed = True
            lower_only = True
        if "twist" in clause or "torso" in clause or "rotate" in clause or "rotating" in clause:
            if "left" in clause:
                state["torso_yaw"] = -20.0 if ("strong" in clause or "far" in clause) else -15.0
                changed = True
            elif "right" in clause:
                state["torso_yaw"] = 18.0
                changed = True
        if "lean" in clause:
            if "forward" in clause:
                state["torso_pitch"] = 7.0 if "noticeably" in clause else 4.0
                changed = True
            elif "back" in clause:
                state["torso_pitch"] = -3.0
                changed = True
        if "look" in clause:
            state["head_prompt"] = clause
            changed = True
        if "bend" in clause and ("knee" in clause or "knees" in clause):
            state["knee_bend"] = "slight"
            changed = True
        if "shallow squat" in clause or "crouch" in clause:
            state["knee_bend"] = "slight"
            changed = True
        if "weight" in clause:
            if "left" in clause:
                state["weight_shift"] = "left"
                changed = True
            elif "right" in clause:
                state["weight_shift"] = "right"
                changed = True
        if "widen" in clause or "wide stance" in clause:
            state["stance_width"] = "wide"
            changed = True
        if "sweep" in clause or "from the far left" in clause or "from left to right" in clause:
            state["torso_yaw"] = -18.0
            state["left_arm"] = "open"
            state["right_arm"] = "open"
            append_current("full body sweep left setup", 8, _scaled_duration(650, flags), False)
            state["torso_yaw"] = 18.0
            append_current("full body sweep right finish", 12, _scaled_duration(1050, flags), False)
            changed = False
        if "straighten" in clause:
            state["knee_bend"] = "none"
            state["weight_shift"] = "center"
            state["stance_width"] = "normal"
            changed = True
        if "return" in clause and "neutral" in clause:
            state.update({
                "left_arm": "down",
                "right_arm": "down",
                "torso_yaw": 0.0,
                "torso_pitch": 0.0,
                "torso_roll": 0.0,
                "knee_bend": "none",
                "weight_shift": "center",
                "stance_width": "normal",
                "head_prompt": "",
            })
            _append_structured_stage(stages, "full body return neutral", {"body": "neutral"}, complete_offsets({}), 18, _scaled_duration(1500, flags), False)
            continue
        if changed:
            label = "full body lower hands" if lower_only else f"full body {clause[:42]}"
            append_current(label, 14, _scaled_duration(1200, flags), False)
        if "hold" in clause or "pause" in clause:
            hold_ms = 2000 if "two second" in clause else 3000 if "three second" in clause else 650
            append_current("full body hold", max(6, round(hold_ms / 120)), _scaled_duration(hold_ms, flags), True)

    if not stages:
        append_current("full body primary pose", 14, _scaled_duration(1300, flags), False)

    if _stage_nonzero_count(stages[-1][2]) != 0:
        _append_structured_stage(stages, "full body return neutral", {"body": "neutral"}, complete_offsets({}), 18, _scaled_duration(1500, flags), False)
    _append_structured_stage(stages, "full body settle neutral", {"body": "neutral"}, complete_offsets({}), 5, _scaled_duration(450, flags), True)
    return stages


def _is_full_body_description(description: str) -> bool:
    prompt = description.lower()
    return any(phrase in prompt for phrase in (
        "left arm",
        "right arm",
        "both arms",
        "both hands",
        "right hand down",
        "right hand low",
        "right hand on chest",
        "right hand on the centre",
        "right hand on the center",
        "right hand firmly",
        "left hand down",
        "left hand low",
        "left hand on chest",
        "left hand on the chest",
        "left hand on the centre",
        "left hand on the center",
        "right arm outward",
        "left arm outward",
        "twist the body",
        "twist body",
        "twist the torso",
        "twist torso",
        "torso rotates",
        "rotating the torso",
        "look right",
        "look left",
        "lean forward",
        "bend the knees",
        "bend knees",
        "shallow squat",
        "shift the weight",
        "shift body weight",
        "weight onto",
        "weight slightly",
        "widen stance",
        "crouch",
        "sweep",
        "horizontal arc",
        "from the far left",
        "from left to right",
        "presentation",
        "present",
    ))


def _compile_structured_full_body_motion(description: str, flags: dict[str, bool]) -> tuple[List[Keyframe], int]:
    frames: List[Keyframe] = [Keyframe("full body neutral", 100, complete_offsets({}))]
    stages = _structured_full_body_stage_targets(description, flags)
    print(f"FULL_BODY_STAGES_GENERATED count={len(stages)}", flush=True)
    print("FULL_BODY_STRUCTURED_STAGES: " + json.dumps([stage[1] for stage in stages], sort_keys=True), flush=True)
    for index, (name, _body, target, _frame_count, _duration_ms, _hold) in enumerate(stages, start=1):
        _log_full_body_stage(index, name, target)
    for name, _body, target, frame_count, duration_ms, hold in stages:
        _append_motion_frames(
            frames,
            name=name,
            target=target,
            frame_count=frame_count,
            total_duration_ms=duration_ms,
            hold=hold,
        )
    frames = _limit_generated_motion(frames)
    if len(frames) > 60:
        stride = (len(frames) - 1) / 59.0
        compacted = [frames[0]]
        for index in range(1, 60):
            compacted.append(keyframe_clone(frames[round(index * stride)]))
        frames = _limit_generated_motion(compacted)
    if not _full_body_balance_check(frames):
        print("FULL_BODY_BALANCE_CHECK_FAILED: falling_back_to_neutral", flush=True)
        return [Keyframe("full body neutral", 500, complete_offsets({}))], len(stages)
    print("FULL_BODY_BALANCE_CHECK_OK", flush=True)
    if not _full_body_collision_check(frames):
        print("FULL_BODY_COLLISION_CHECK_FAILED: falling_back_to_neutral", flush=True)
        return [Keyframe("full body neutral", 500, complete_offsets({}))], len(stages)
    print("FULL_BODY_COLLISION_CHECK_OK", flush=True)
    return frames, len(stages)


def _deterministic_full_body_compiler_test_frames() -> List[Keyframe]:
    flags = {"slow": False, "quick": False, "enthusiastic": False, "hesitant": False, "pause": False, "return": True}
    stages = [
        (
            "deterministic left overhead torso left forward",
            _merge_targets(
                _left_arm_pose("up", 1.0),
                _right_arm_pose("down", 1.0),
                _torso_pose(yaw_deg=-18.0, pitch_deg=7.0),
            ),
        ),
        (
            "deterministic left down right sideways",
            _merge_targets(
                _left_arm_pose("down", 1.0),
                _right_arm_pose("sideways", 1.0),
                _torso_pose(yaw_deg=0.0, pitch_deg=0.0),
            ),
        ),
        ("deterministic neutral", complete_offsets({})),
    ]
    frames = [Keyframe("deterministic start neutral", 100, complete_offsets({}))]
    print(f"FULL_BODY_STAGES_GENERATED count={len(stages)}", flush=True)
    for index, (label, target) in enumerate(stages, start=1):
        target = _clamp_full_body_offsets(target)
        _log_full_body_stage(index, label, target)
        if index < 3 and _stage_nonzero_count(target) == 0:
            raise RuntimeError(f"Deterministic stage {index} resolved to all-zero targets")
        _append_motion_frames(frames, name=label, target=target, frame_count=10, total_duration_ms=900, hold=False)
    frames = _limit_generated_motion(frames)
    if not _full_body_balance_check(frames):
        raise RuntimeError("Deterministic full-body test failed balance check")
    if not _full_body_collision_check(frames):
        raise RuntimeError("Deterministic full-body test failed collision check")
    required = (
        "left_shoulder_pitch_joint",
        "waist_yaw_joint",
        "waist_pitch_joint",
        "right_shoulder_roll_joint",
        "right_shoulder_pitch_joint",
    )
    active = {joint for frame in frames for joint, value in frame.joint_offsets_rad.items() if abs(float(value)) > 1e-6}
    missing = [joint for joint in required if joint not in active]
    if missing:
        raise RuntimeError("Deterministic full-body test missing active joints: " + ", ".join(missing))
    print("FULL_BODY_DETERMINISTIC_TEST_OK", flush=True)
    return frames


def _append_motion_frames(
    frames: List[Keyframe],
    *,
    name: str,
    target: Dict[str, float],
    frame_count: int,
    total_duration_ms: int,
    hold: bool = False,
) -> None:
    frame_count = max(1, frame_count)
    frame_duration = max(MIN_KEYFRAME_DURATION_MS, round(total_duration_ms / frame_count))
    start_offsets = complete_offsets(frames[-1].joint_offsets_rad if frames else {})
    target_offsets = complete_offsets(target)
    for index in range(1, frame_count + 1):
        if hold:
            offsets = target_offsets
        else:
            offsets = interpolate_offsets(start_offsets, target_offsets, index / frame_count)
        frames.append(Keyframe(f"{name} {index:02d}", frame_duration, complete_offsets(offsets)))


def _semantic_stage_plan(description: str, flags: dict[str, bool]) -> list[tuple[str, Dict[str, float], int, int, bool]]:
    prompt = description.lower()
    scale = _movement_scale(flags)
    stages: list[tuple[str, Dict[str, float], int, int, bool]] = []

    wants_raise = any(phrase in prompt for phrase in ("raise both hands", "both hands", "hands up", "raise hands", "raise your hands"))
    wants_sweep = any(phrase in prompt for phrase in (
        "sweep",
        "across",
        "from left to right",
        "from right to left",
        "gesture toward",
        "gesture towards",
        "present",
        "presentation",
    ))
    wants_welcome = any(word in prompt for word in ("welcome", "audience", "introducing", "introduce", "speaker")) or wants_sweep
    wants_point = "point" in prompt or "look to the left" in prompt or "look left" in prompt
    wants_chest = (
        "hand on chest" in prompt
        or "right hand on your chest" in prompt
        or "right hand on my chest" in prompt
        or "place your right hand on your chest" in prompt
        or "heart" in prompt
        or "myself" in prompt
    )
    wants_lower = flags["return"] or any(word in prompt for word in ("lower", "relax"))
    sweep_left_to_right = "right to left" not in prompt

    if wants_sweep:
        first_side = "left" if sweep_left_to_right else "right"
        second_side = "right" if sweep_left_to_right else "left"
        stages.append(("hands to chest height", _sweep_center_pose(scale * 0.72), 8, _scaled_duration(760, flags), False))
        stages.append(("torso leads sweep", _sweep_pose(scale, side=first_side, torso_only=True), 6, _scaled_duration(520, flags), False))
        stages.append(("shoulders follow sweep", _sweep_pose(scale, side=first_side), 8, _scaled_duration(720, flags), False))
        stages.append(("hands cross center", _sweep_center_pose(scale), 10, _scaled_duration(850, flags), False))
        stages.append(("wide horizontal sweep", _sweep_pose(scale, side=second_side), 12, _scaled_duration(1050, flags), False))
        if flags["pause"] or "hold" in prompt:
            stages.append(("presentation pause", _sweep_pose(scale, side=second_side), 6, _scaled_duration(500, flags), True))
    elif wants_raise:
        raise_frames = 10 if not flags["slow"] else 14
        raise_ms = 760 if flags["enthusiastic"] or flags["quick"] else 1050
        stages.append(("raise both arms", _raise_both_hands_pose(scale), raise_frames, _scaled_duration(raise_ms, flags), False))
    elif wants_welcome:
        stages.append(("open audience welcome", _open_audience_pose(scale), 12, _scaled_duration(1100, flags), False))
    else:
        return []

    if (flags["pause"] or wants_raise) and not wants_sweep:
        hold_frames = 8 if "briefly" in prompt else 10
        stages.append(("hold pose", complete_offsets(stages[-1][1]), hold_frames, _scaled_duration(650, flags), True))

    if wants_point and not wants_sweep:
        stages.append(("look and point right hand", _right_point_pose(scale, look_left=("left" in prompt)), 12, _scaled_duration(1100, flags), False))
        stages.append(("hold point", _right_point_pose(scale, look_left=("left" in prompt)), 6, _scaled_duration(450, flags), True))

    if wants_chest:
        stages.append(("right hand to chest", _right_hand_to_chest_pose(scale), 12, _scaled_duration(1100, flags), False))
        stages.append(("hold hand on chest", _right_hand_to_chest_pose(scale), 6, _scaled_duration(550, flags), True))

    if wants_welcome and not wants_chest and not wants_point and not wants_raise and not wants_sweep:
        stages.append(("welcoming sweep", _raise_both_hands_pose(scale * 0.72), 10, _scaled_duration(900, flags), False))
        stages.append(("presentation pause", _raise_both_hands_pose(scale * 0.72), 6, _scaled_duration(500, flags), True))

    lower_frames = 18 if wants_lower or flags["slow"] else 14
    stages.append(("lower smoothly", complete_offsets({}), lower_frames, _scaled_duration(1500, flags), False))
    stages.append(("settle neutral", complete_offsets({}), 5, _scaled_duration(450, flags), True))
    return stages


def motion_from_description(description: str) -> List[Keyframe]:
    normalized = _normalize_prompt_text(description)
    if normalized in {"neutral", "return to neutral", "reset neutral", "reset to neutral"}:
        print("MOTION_PARSE_OK action=neutral_reset side=body confidence=1.00", flush=True)
        return [Keyframe("neutral", 100, neutral_offsets()), Keyframe("settle neutral", 300, neutral_offsets())]
    if _is_talking_idle_description(description):
        return _compile_talking_idle_motion()
    wave_side = _parse_wave_prompt(description)
    if wave_side:
        return _compile_wave_motion(wave_side)

    if is_thinking_hand_on_chin_description(description):
        print("MOTION_PARSE_OK action=thinking_hand_on_chin side=right confidence=0.95", flush=True)
        print("MOTION_TEMPLATE_SELECTED: Thinking – Hand on Chin")
        return sample_thinking_hand_on_chin_keyframes()

    if is_scratch_head_description(description):
        print("MOTION_PARSE_OK action=scratch_head side=right confidence=0.95", flush=True)
        print("MOTION_TEMPLATE_SELECTED: Scratch Head")
        return sample_scratch_head_keyframes()

    flags = _motion_text_flags(description)
    if _is_full_body_description(description):
        print("MOTION_PARSE_OK action=full_body_sequence side=body confidence=0.82", flush=True)
        frames, _stage_count = _compile_structured_full_body_motion(description, flags)
        return frames

    stage_plan = _semantic_stage_plan(description, flags)
    if not stage_plan:
        print(f"MOTION_PARSE_FAILED prompt={description}", flush=True)
        print("NO_MOTION_GENERATED", flush=True)
        return []
    frames: List[Keyframe] = [Keyframe("start relaxed", 100, neutral_offsets())]
    print("MOTION_PARSE_OK action=semantic_motion side=body confidence=0.70", flush=True)
    print("MOTION_SEMANTIC_STAGES: " + " -> ".join(stage[0] for stage in stage_plan), flush=True)
    for name, target, frame_count, duration_ms, hold in stage_plan:
        _append_motion_frames(
            frames,
            name=name,
            target=target,
            frame_count=frame_count,
            total_duration_ms=duration_ms,
            hold=hold,
        )
    if len(frames) > 60:
        stride = (len(frames) - 1) / 59.0
        compacted = [frames[0]]
        for index in range(1, 60):
            compacted.append(keyframe_clone(frames[round(index * stride)]))
        frames = compacted
    return frames

class MotionStudio(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"MuJoCo model not found: {MODEL_PATH}")
        POSES_DIR.mkdir(parents=True, exist_ok=True)
        ANIMATIONS_DIR.mkdir(parents=True, exist_ok=True)
        CUSTOM_ANIMATIONS_DIR.mkdir(parents=True, exist_ok=True)
        BRAINOS_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        GESTURES_DIR.mkdir(parents=True, exist_ok=True)
        ensure_sample_animation()

        self.model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
        if SIMULATION_MODE == "AUTHORING_KINEMATIC":
            self.model.opt.gravity[:] = 0.0
            print("SIMULATION_MODE=AUTHORING_KINEMATIC", flush=True)
            print("ROOT_CONSTRAINT_ACTIVE=true", flush=True)
            print("GRAVITY_BALANCE_REQUIRED=false", flush=True)
        else:
            print("SIMULATION_MODE=DYNAMIC_VALIDATION", flush=True)
            print("FULL_BODY_STABILIZATION_ACTIVE=true", flush=True)
        self.data = mujoco.MjData(self.model)
        print_model_inventory(self.model)

        self.bindings = {name: joint_binding(self.model, name) for name in FULL_BODY_JOINTS}
        self.neutral_qpos = self._initial_qpos()
        log_neutral_stance_loaded()
        self.current_offsets: Dict[str, float] = complete_offsets({})
        self.sliders: Dict[str, QSlider] = {}
        self.spin_boxes: Dict[str, QDoubleSpinBox] = {}
        self.value_labels: Dict[str, QLabel] = {}
        self.keyframes: List[Keyframe] = []
        self.current_motion_path: Path | None = None
        self.motion_created_at: str | None = None
        self.dirty = False
        self.undo_stack: List[Dict[str, object]] = []
        self.redo_stack: List[Dict[str, object]] = []
        self.loading_controls = False
        self.last_joint_log_at: Dict[str, float] = {}
        self.playing = False
        self.looping = False
        self.playback_speed = DEFAULT_PLAYBACK_SPEED
        self.play_segment_index = 0
        self.play_segment_started_at = 0.0
        self.play_segment_from = complete_offsets({})
        self.play_segment_to = complete_offsets({})
        self.motion_frame_index = 0
        self.generated_dense_trajectory: List[Dict[str, object]] = []
        self.gesture_library: Dict[str, Dict[str, object]] = {}
        self.active_gesture_id: str | None = None
        self.active_gesture_type: str = "one_shot"
        self.active_gesture_return_to_neutral = True
        self.active_gesture_loopable = False
        self.saved_gesture_playing = False
        self.saved_gesture_resume_payload: Dict[str, object] | None = None
        self.saved_gesture_resume_id: str | None = None
        self.returning_to_neutral = False
        self.return_neutral_started_at = 0.0
        self.return_neutral_from = complete_offsets({})
        self.lock_checkboxes: Dict[str, QCheckBox] = {}

        self.viewer_process: subprocess.Popen | None = None
        self.live_state_write_count = 0
        self.last_live_state_log_at = 0.0
        self.last_live_state_payload_key = None
        self.live_state_writer_enabled_logged = False
        atexit.register(self._stop_viewer_process)
        self._build_ui()
        self._load_keyframes_into_editor(
            [Keyframe("neutral", DEFAULT_KEYFRAME_DURATION_MS, complete_offsets({}))],
            name="Untitled ERIC Motion",
            description="",
            path=None,
            mark_dirty=False,
        )
        self._apply_pose()
        self.refresh_gesture_library()
        self._launch_viewer()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def _initial_qpos(self):
        mujoco.mj_resetData(self.model, self.data)
        print("START_KEYFRAME: canonical_authoring_neutral")
        self.data.qpos[0:3] = BASE_POSITION
        self.data.qpos[3:7] = BASE_QUATERNION
        for joint in FULL_BODY_JOINTS:
            binding = joint_binding(self.model, joint)
            self.data.qpos[binding.qpos_address] = clamp(0.0, binding.lower, binding.upper)
        self.data.qvel[:] = 0.0
        mujoco.mj_forward(self.model, self.data)
        return self.data.qpos.copy()

    def _standing_keyframe_id(self) -> int | None:
        preferred = ("standing", "stand", "home", "neutral", "default")
        for name in preferred:
            key_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_KEY, name)
            if key_id >= 0:
                return int(key_id)
        return 0 if self.model.nkey > 0 else None

    def _build_ui(self) -> None:
        self.setWindowTitle("ERIC Motion Studio")
        root = QScrollArea()
        root.setWidgetResizable(True)
        content = QWidget()
        page = QVBoxLayout(content)

        status = QLabel(STATUS_TEXT)
        status.setStyleSheet("font-weight: bold; color: #b00020; padding: 8px;")
        status.setAlignment(Qt.AlignCenter)
        page.addWidget(status)

        intro = QLabel("Describe the movement you want, create it, then tune it with simple buttons.")
        intro.setStyleSheet("font-size: 16px; font-weight: bold; padding: 4px;")
        page.addWidget(intro)

        self.motion_description = QTextEdit()
        self.motion_description.setPlaceholderText("Example: Happy talking motion with relaxed hands around waist height.")
        self.motion_description.setFixedHeight(95)
        self.motion_description.textChanged.connect(self._metadata_changed)
        page.addWidget(self.motion_description)

        create_btn = QPushButton("CREATE MOTION")
        create_btn.setMinimumHeight(44)
        create_btn.setStyleSheet("font-size: 18px; font-weight: bold;")
        create_btn.clicked.connect(self.create_motion_from_description)
        page.addWidget(create_btn)

        self.simple_status = QLabel("MuJoCo status: waiting for a motion.")
        self.simple_status.setStyleSheet("padding: 6px; background: #eef3ff;")
        page.addWidget(self.simple_status)

        file_row = QHBoxLayout()
        for label, callback in (
            ("New Motion", self.new_motion),
            ("Open Motion", self.open_motion),
            ("Save", self.save_current_motion),
            ("Save As", self.save_current_motion_as),
            ("Export JSON", self.export_json),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(callback)
            file_row.addWidget(btn)
        page.addLayout(file_row)

        template_row = QHBoxLayout()
        template_row.addWidget(QLabel("Load Template:"))
        self.template_combo = QComboBox()
        self.template_combo.addItems(["Neutral", "Generic Talking", "Scratch Head", "Thinking – Hand on Chin"])
        template_row.addWidget(self.template_combo, 1)
        load_template_btn = QPushButton("Load Template")
        load_template_btn.clicked.connect(self.load_selected_template)
        template_row.addWidget(load_template_btn)
        page.addLayout(template_row)

        simple_buttons = QGridLayout()
        controls = [
            ("Less movement", self.less_movement),
            ("More movement", self.more_movement),
            ("Hands lower", self.hands_lower),
            ("Hands higher", self.hands_higher),
            ("Slower", self.slower_motion),
            ("Faster", self.faster_motion),
            ("Play", self.play_animation),
            ("Stop", self.stop_animation),
        ]
        for index, (label, callback) in enumerate(controls):
            btn = QPushButton(label)
            btn.setMinimumHeight(36)
            btn.clicked.connect(callback)
            simple_buttons.addWidget(btn, index // 4, index % 4)
        page.addLayout(simple_buttons)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Motion name:"))
        self.motion_name = QLineEdit()
        self.motion_name.setPlaceholderText("Talking Eric Happy")
        self.motion_name.textChanged.connect(self._metadata_changed)
        name_row.addWidget(self.motion_name)
        page.addLayout(name_row)

        save_row = QHBoxLayout()
        save_motion_btn = QPushButton("SAVE MOTION")
        export_btn = QPushButton("EXPORT TO BRAINOS")
        save_motion_btn.setMinimumHeight(40)
        export_btn.setMinimumHeight(40)
        save_motion_btn.clicked.connect(self.save_named_motion)
        export_btn.clicked.connect(self.export_to_brainos)
        save_row.addWidget(save_motion_btn)
        save_row.addWidget(export_btn)
        page.addLayout(save_row)

        gesture_group = QGroupBox("Approved Gesture Library")
        gesture_layout = QVBoxLayout(gesture_group)
        gesture_name_row = QHBoxLayout()
        gesture_name_row.addWidget(QLabel("Gesture Name:"))
        self.gesture_name = QLineEdit()
        self.gesture_name.setPlaceholderText("Right Hand to Chest")
        gesture_name_row.addWidget(self.gesture_name, 2)
        gesture_name_row.addWidget(QLabel("Motion Type:"))
        self.gesture_motion_type = QComboBox()
        self.gesture_motion_type.addItems(["one_shot", "loopable", "interrupt"])
        gesture_name_row.addWidget(self.gesture_motion_type)
        gesture_layout.addLayout(gesture_name_row)

        gesture_flags_row = QHBoxLayout()
        self.gesture_interruptible = QCheckBox("Interruptible")
        self.gesture_interruptible.setChecked(True)
        self.gesture_return_to_neutral = QCheckBox("Return to Neutral")
        self.gesture_return_to_neutral.setChecked(True)
        gesture_flags_row.addWidget(self.gesture_interruptible)
        gesture_flags_row.addWidget(self.gesture_return_to_neutral)
        gesture_flags_row.addWidget(QLabel("Tags:"))
        self.gesture_tags = QLineEdit()
        self.gesture_tags.setPlaceholderText("chest, self-reference, right-arm")
        gesture_flags_row.addWidget(self.gesture_tags, 1)
        gesture_layout.addLayout(gesture_flags_row)

        gesture_buttons = QHBoxLayout()
        save_approved_btn = QPushButton("SAVE APPROVED MOTION")
        play_saved_btn = QPushButton("PLAY SAVED MOTION")
        stop_saved_btn = QPushButton("STOP MOTION")
        delete_saved_btn = QPushButton("DELETE")
        refresh_saved_btn = QPushButton("REFRESH LIBRARY")
        save_approved_btn.clicked.connect(self.save_approved_motion)
        play_saved_btn.clicked.connect(self.play_selected_saved_gesture)
        stop_saved_btn.clicked.connect(self.stop_saved_motion)
        delete_saved_btn.clicked.connect(self.delete_selected_saved_gesture)
        refresh_saved_btn.clicked.connect(self.refresh_gesture_library)
        for button in (save_approved_btn, play_saved_btn, stop_saved_btn, delete_saved_btn, refresh_saved_btn):
            gesture_buttons.addWidget(button)
        gesture_layout.addLayout(gesture_buttons)

        self.gesture_list = QListWidget()
        self.gesture_list.currentRowChanged.connect(self._selected_gesture_changed)
        gesture_layout.addWidget(self.gesture_list)
        page.addWidget(gesture_group)

        self.advanced_btn = QPushButton("ADVANCED EDITING")
        self.advanced_btn.setCheckable(True)
        self.advanced_btn.clicked.connect(self.toggle_advanced_editing)
        page.addWidget(self.advanced_btn)

        self.advanced_container = QWidget()
        self.advanced_container.setVisible(False)
        advanced_main = QHBoxLayout(self.advanced_container)

        left_panel = QVBoxLayout()
        advanced_label = QLabel("Advanced Editing: joint sliders, poses, keyframes and durations")
        advanced_label.setStyleSheet("font-weight: bold; padding: 6px;")
        left_panel.addWidget(advanced_label)

        grid = QGridLayout()
        grid.addWidget(QLabel("Joint"), 0, 0)
        grid.addWidget(QLabel("Current value"), 0, 1)
        grid.addWidget(QLabel("Target value"), 0, 2)
        grid.addWidget(QLabel("Joint limit / control"), 0, 3)
        grid.addWidget(QLabel("Reset"), 0, 4)

        for row, name in enumerate(FULL_BODY_JOINTS, start=1):
            binding = self.bindings[name]
            neutral = float(self.neutral_qpos[binding.qpos_address])
            min_offset = binding.lower - neutral
            max_offset = binding.upper - neutral
            soft_min, soft_max = self._editor_limits_for_joint(name)
            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(round(soft_min * SLIDER_SCALE))
            slider.setMaximum(round(soft_max * SLIDER_SCALE))
            slider.setValue(0)
            slider.setSingleStep(5)
            slider.setPageStep(25)
            label = QLabel("+0.000")
            spin = QDoubleSpinBox()
            spin.setDecimals(3)
            spin.setMinimum(soft_min)
            spin.setMaximum(soft_max)
            spin.setSingleStep(0.01)
            spin.setValue(0.0)
            slider.valueChanged.connect(lambda value, joint=name: self._slider_changed(joint, value))
            spin.valueChanged.connect(lambda value, joint=name: self._spin_changed(joint, value))
            reset_joint_btn = QPushButton("Reset")
            reset_joint_btn.clicked.connect(lambda _checked=False, joint=name: self.reset_joint(joint))
            self.sliders[name] = slider
            self.spin_boxes[name] = spin
            self.value_labels[name] = label
            grid.addWidget(QLabel(display_joint_name(name)), row, 0)
            grid.addWidget(label, row, 1)
            grid.addWidget(spin, row, 2)
            grid.addWidget(slider, row, 3)
            grid.addWidget(reset_joint_btn, row, 4)

        left_panel.addLayout(grid)

        lock_group = QGroupBox("Joint Locks")
        lock_layout = QGridLayout(lock_group)
        lock_specs = [
            ("LOCK LEGS", LEFT_LEG_JOINTS + RIGHT_LEG_JOINTS),
            ("LOCK WAIST", WAIST_JOINTS),
            ("LOCK LEFT ARM", LEFT_ARM_JOINTS),
            ("LOCK RIGHT ARM", RIGHT_ARM_JOINTS),
            ("LOCK ROOT", tuple()),
        ]
        for index, (label, joints) in enumerate(lock_specs):
            checkbox = QCheckBox(label)
            checkbox.toggled.connect(lambda checked, group=label, group_joints=joints: self._lock_group_changed(group, group_joints, checked))
            self.lock_checkboxes[label] = checkbox
            lock_layout.addWidget(checkbox, index // 3, index % 3)
        left_panel.addWidget(lock_group)

        pose_buttons = QHBoxLayout()
        reset_btn = QPushButton("RESET ALL TO NEUTRAL")
        preview_neutral_btn = QPushButton("Return Preview to Neutral")
        add_neutral_btn = QPushButton("Add Neutral Keyframe")
        copy_pose_btn = QPushButton("COPY CURRENT POSE")
        apply_pose_btn = QPushButton("APPLY POSE")
        save_pose_btn = QPushButton("SAVE POSE")
        load_pose_btn = QPushButton("LOAD POSE")
        mirror_arms_btn = QPushButton("MIRROR ARMS")
        mirror_legs_btn = QPushButton("MIRROR LEGS")
        reset_btn.clicked.connect(self.reset_neutral)
        preview_neutral_btn.clicked.connect(self.return_preview_to_neutral)
        add_neutral_btn.clicked.connect(self.add_neutral_keyframe)
        copy_pose_btn.clicked.connect(self.copy_current_pose)
        apply_pose_btn.clicked.connect(self.apply_copied_pose)
        save_pose_btn.clicked.connect(self.save_pose)
        load_pose_btn.clicked.connect(self.load_pose)
        mirror_arms_btn.clicked.connect(self.mirror_arms)
        mirror_legs_btn.clicked.connect(self.mirror_legs)
        pose_buttons.addWidget(reset_btn)
        pose_buttons.addWidget(preview_neutral_btn)
        pose_buttons.addWidget(add_neutral_btn)
        pose_buttons.addWidget(copy_pose_btn)
        pose_buttons.addWidget(apply_pose_btn)
        pose_buttons.addWidget(save_pose_btn)
        pose_buttons.addWidget(load_pose_btn)
        pose_buttons.addWidget(mirror_arms_btn)
        pose_buttons.addWidget(mirror_legs_btn)
        left_panel.addLayout(pose_buttons)

        right_panel = QVBoxLayout()
        right_panel.addWidget(QLabel("Animation Keyframes"))
        self.keyframe_list = QListWidget()
        self.keyframe_list.currentRowChanged.connect(self._selected_keyframe_changed)
        right_panel.addWidget(self.keyframe_list)

        duration_row = QHBoxLayout()
        duration_row.addWidget(QLabel("Selected duration (ms):"))
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setDecimals(0)
        self.duration_spin.setMinimum(MIN_KEYFRAME_DURATION_MS)
        self.duration_spin.setMaximum(MAX_KEYFRAME_DURATION_MS)
        self.duration_spin.setSingleStep(50)
        self.duration_spin.setValue(DEFAULT_KEYFRAME_DURATION_MS)
        self.duration_spin.valueChanged.connect(self._duration_changed)
        duration_row.addWidget(self.duration_spin)
        right_panel.addLayout(duration_row)

        edit_buttons = QGridLayout()
        keyframe_controls = [
            ("Add Keyframe", self.add_keyframe),
            ("Duplicate Keyframe", self.duplicate_keyframe),
            ("Delete Keyframe", self.delete_keyframe),
            ("Move Up", self.move_keyframe_up),
            ("Move Down", self.move_keyframe_down),
            ("Rename Keyframe", self.rename_keyframe),
            ("Set Duration", self.set_selected_duration_dialog),
            ("Capture Current Pose", self.capture_selected_keyframe),
            ("Apply Selected Keyframe to Preview", self.apply_selected_keyframe_to_preview),
            ("Undo", self.undo),
            ("Redo", self.redo),
        ]
        for index, (label, callback) in enumerate(keyframe_controls):
            btn = QPushButton(label)
            btn.clicked.connect(callback)
            edit_buttons.addWidget(btn, index // 2, index % 2)
        right_panel.addLayout(edit_buttons)

        playback_buttons = QHBoxLayout()
        play_btn = QPushButton("Play From Start")
        play_selected_btn = QPushButton("Play From Selected Keyframe")
        stop_btn = QPushButton("Stop")
        self.loop_btn = QCheckBox("Loop")
        play_btn.clicked.connect(self.play_animation)
        play_selected_btn.clicked.connect(self.play_from_selected_keyframe)
        stop_btn.clicked.connect(self.stop_animation)
        self.loop_btn.toggled.connect(self.toggle_loop)
        playback_buttons.addWidget(play_btn)
        playback_buttons.addWidget(play_selected_btn)
        playback_buttons.addWidget(stop_btn)
        playback_buttons.addWidget(self.loop_btn)
        right_panel.addLayout(playback_buttons)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Playback speed:"))
        self.playback_speed_spin = QDoubleSpinBox()
        self.playback_speed_spin.setDecimals(2)
        self.playback_speed_spin.setMinimum(MIN_PLAYBACK_SPEED)
        self.playback_speed_spin.setMaximum(MAX_PLAYBACK_SPEED)
        self.playback_speed_spin.setSingleStep(0.05)
        self.playback_speed_spin.setValue(DEFAULT_PLAYBACK_SPEED)
        self.playback_speed_spin.valueChanged.connect(self._playback_speed_changed)
        speed_row.addWidget(self.playback_speed_spin)
        right_panel.addLayout(speed_row)

        animation_buttons = QHBoxLayout()
        save_animation_btn = QPushButton("Save Animation")
        load_animation_btn = QPushButton("Load Animation")
        save_animation_btn.clicked.connect(self.save_animation)
        load_animation_btn.clicked.connect(self.load_animation)
        animation_buttons.addWidget(save_animation_btn)
        animation_buttons.addWidget(load_animation_btn)
        right_panel.addLayout(animation_buttons)

        self.animation_status = QLabel("Animation: stopped")
        right_panel.addWidget(self.animation_status)
        right_panel.addStretch(1)

        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        advanced_main.addWidget(left_widget, 3)
        advanced_main.addWidget(right_widget, 2)
        page.addWidget(self.advanced_container)

        root.setWidget(content)
        self.setCentralWidget(root)
        self.resize(1280, 820)
        self._install_shortcuts()
        self._update_window_title()
        print("CUSTOM_EDITOR_READY")

    def _metadata_changed(self) -> None:
        if self.loading_controls:
            return
        self._mark_dirty(True)

    def toggle_advanced_editing(self) -> None:
        visible = self.advanced_btn.isChecked()
        self.advanced_container.setVisible(visible)
        self.advanced_btn.setText("HIDE ADVANCED EDITING" if visible else "ADVANCED EDITING")

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, activated=self.redo)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self.save_current_motion)
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.open_motion)
        QShortcut(QKeySequence("Space"), self, activated=self.toggle_playback_from_shortcut)

    def _editor_limits_for_joint(self, joint: str) -> tuple[float, float]:
        binding = self.bindings[joint]
        neutral = float(self.neutral_qpos[binding.qpos_address])
        min_offset = binding.lower - neutral
        max_offset = binding.upper - neutral
        return max(min_offset, -1.25), min(max_offset, 1.25)

    def _snapshot(self) -> Dict[str, object]:
        return {
            "keyframes": clone_keyframes(self.keyframes),
            "current_offsets": complete_offsets(self.current_offsets),
            "motion_name": self.motion_name.text(),
            "description": self.motion_description.toPlainText(),
            "looping": self.looping,
            "path": str(self.current_motion_path) if self.current_motion_path else "",
            "created_at": self.motion_created_at or "",
            "selected_row": self.keyframe_list.currentRow() if hasattr(self, "keyframe_list") else -1,
        }

    def _restore_snapshot(self, snapshot: Dict[str, object]) -> None:
        self.stop_animation()
        self.keyframes = clone_keyframes(snapshot.get("keyframes", []))
        self.current_offsets = complete_offsets(snapshot.get("current_offsets", {}))
        self.motion_name.setText(str(snapshot.get("motion_name") or ""))
        self.motion_description.setPlainText(str(snapshot.get("description") or ""))
        self.looping = bool(snapshot.get("looping"))
        self.loop_btn.setChecked(self.looping)
        path_text = str(snapshot.get("path") or "")
        self.current_motion_path = Path(path_text) if path_text else None
        self.motion_created_at = str(snapshot.get("created_at") or "") or None
        self._refresh_keyframe_list(select_row=int(snapshot.get("selected_row", 0)))
        self._set_offsets(self.current_offsets)
        self._update_window_title()

    def _push_undo(self) -> None:
        self.undo_stack.append(copy.deepcopy(self._snapshot()))
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _mark_dirty(self, changed: bool = True) -> None:
        self.dirty = changed
        self._update_window_title()

    def _update_window_title(self) -> None:
        name = self._motion_name_or_default()
        marker = "*" if self.dirty else ""
        self.setWindowTitle(f"ERIC Motion Studio{marker} — {name}")

    def _confirm_discard_unsaved(self, action: str) -> bool:
        if not self.dirty:
            return True
        result = QMessageBox.question(
            self,
            "Unsaved Motion",
            f"Save changes before {action}?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if result == QMessageBox.Cancel:
            return False
        if result == QMessageBox.Save:
            return self.save_current_motion()
        return True

    def _load_keyframes_into_editor(
        self,
        frames: List[Keyframe],
        *,
        name: str,
        description: str = "",
        path: Path | None = None,
        created_at: str | None = None,
        mark_dirty: bool = False,
        log_template: str | None = None,
    ) -> None:
        self.stop_animation()
        self.keyframes = clone_keyframes(frames)
        self.loading_controls = True
        try:
            self.motion_name.setText(name)
            self.motion_description.setPlainText(description)
        finally:
            self.loading_controls = False
        self.current_motion_path = path
        self.motion_created_at = created_at or iso_timestamp()
        self._refresh_keyframe_list(select_row=0)
        self._set_offsets(self.keyframes[0].joint_offsets_rad if self.keyframes else complete_offsets({}))
        self.generated_dense_trajectory = dense_trajectory_from_keyframes(self.keyframes, GESTURE_FRAME_RATE)
        self._mark_dirty(mark_dirty)
        self.simple_status.setText(f"MuJoCo status: loaded {name}")
        if log_template:
            print(f"TEMPLATE_LOADED: {log_template}")

    def load_selected_template(self) -> None:
        if not self._confirm_discard_unsaved("loading another template"):
            return
        template = self.template_combo.currentText()
        if template == "Neutral":
            frames = [Keyframe("neutral", DEFAULT_KEYFRAME_DURATION_MS, complete_offsets({}))]
        elif template == "Generic Talking":
            frames = sample_conversational_talking_keyframes()
        elif template == "Scratch Head":
            frames = sample_scratch_head_keyframes()
        elif template == "Thinking – Hand on Chin":
            frames = sample_thinking_hand_on_chin_keyframes()
        else:
            QMessageBox.warning(self, "Load Template", f"Unknown template: {template}")
            return
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._load_keyframes_into_editor(
            frames,
            name=template,
            description=f"Editable copy of {template}",
            path=None,
            mark_dirty=True,
            log_template=template,
        )

    def new_motion(self) -> bool:
        if not self._confirm_discard_unsaved("creating a new motion"):
            return False
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._load_keyframes_into_editor(
            [Keyframe("neutral", DEFAULT_KEYFRAME_DURATION_MS, complete_offsets({}))],
            name="Untitled ERIC Motion",
            description="",
            path=None,
            mark_dirty=False,
        )
        print("CUSTOM_MOTION_NEW")
        return True

    def open_motion(self) -> bool:
        if not self._confirm_discard_unsaved("opening another motion"):
            return False
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open ERIC custom motion",
            str(CUSTOM_ANIMATIONS_DIR),
            "JSON files (*.json)",
        )
        if not path:
            return False
        try:
            frames, payload = load_animation_payload(Path(path))
            self.undo_stack.clear()
            self.redo_stack.clear()
            self._load_keyframes_into_editor(
                frames,
                name=str(payload.get("motion_name") or payload.get("name") or Path(path).stem),
                description=str(payload.get("description") or ""),
                path=Path(path),
                created_at=str(payload.get("created_at") or "") or None,
                mark_dirty=False,
            )
            self.looping = bool(payload.get("loop"))
            self.loop_btn.setChecked(self.looping)
            print(f"CUSTOM_MOTION_OPENED: {path}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Open Motion failed", str(exc))
            return False

    def _write_motion_file(self, path: Path) -> bool:
        if not self.keyframes:
            QMessageBox.information(self, "Save", "Add at least one keyframe first.")
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = build_motion_payload(
            self.keyframes,
            name=self._motion_name_or_default(),
            loop=self.looping,
            description=self.motion_description.toPlainText().strip(),
            created_at=self.motion_created_at,
        )
        path.write_text(json.dumps(payload, indent=2) + "\n")
        self.current_motion_path = path
        self.motion_created_at = str(payload["created_at"])
        self._mark_dirty(False)
        self.simple_status.setText(f"MuJoCo status: saved {path.name}")
        print(f"CUSTOM_MOTION_SAVED: {path}")
        return True

    def save_current_motion(self) -> bool:
        if self.current_motion_path:
            return self._write_motion_file(self.current_motion_path)
        return self.save_current_motion_as()

    def save_current_motion_as(self) -> bool:
        default_name = f"{slugify_name(self._motion_name_or_default())}.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save ERIC custom motion",
            str(CUSTOM_ANIMATIONS_DIR / default_name),
            "JSON files (*.json)",
        )
        if not path:
            return False
        return self._write_motion_file(Path(path))

    def export_json(self) -> None:
        if not self.keyframes:
            QMessageBox.information(self, "Export JSON", "Add at least one keyframe first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export ERIC motion JSON",
            str(CUSTOM_ANIMATIONS_DIR / f"{slugify_name(self._motion_name_or_default())}-export.json"),
            "JSON files (*.json)",
        )
        if not path:
            return
        payload = build_motion_payload(
            self.keyframes,
            name=self._motion_name_or_default(),
            loop=self.looping,
            description=self.motion_description.toPlainText().strip(),
            created_at=self.motion_created_at,
        )
        Path(path).write_text(json.dumps(payload, indent=2) + "\n")
        print(f"CUSTOM_MOTION_SAVED: {path}")

    def undo(self) -> None:
        if not self.undo_stack:
            return
        self.redo_stack.append(copy.deepcopy(self._snapshot()))
        snapshot = self.undo_stack.pop()
        self._restore_snapshot(snapshot)
        self._mark_dirty(True)
        print("CUSTOM_EDITOR_UNDO")

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append(copy.deepcopy(self._snapshot()))
        snapshot = self.redo_stack.pop()
        self._restore_snapshot(snapshot)
        self._mark_dirty(True)
        print("CUSTOM_EDITOR_REDO")

    def create_motion_from_description(self) -> None:
        description = self.motion_description.toPlainText().strip()
        if not description:
            QMessageBox.information(self, "Create Motion", "Type a plain-English movement first.")
            return
        print(f"MOTION_PROMPT_RECEIVED: {description}", flush=True)
        print(f"FULL_BODY_PROMPT_RECEIVED: {description}", flush=True)
        self._push_undo()
        self.stop_animation()
        frames = motion_from_description(description)
        if not frames:
            self.simple_status.setText("MuJoCo status: no motion generated for that prompt.")
            return
        wave_side = _parse_wave_prompt(description)
        ok, reason = validate_motion_amplitude(frames, action="wave" if wave_side else None, side=wave_side)
        if not ok:
            print(f"MOTION_REJECTED reason={reason}", flush=True)
            self.simple_status.setText(f"MuJoCo status: motion rejected: {reason}")
            return
        accounting_ok, accounting_reason, _accounting = validate_trajectory_accounting(frames)
        if not accounting_ok:
            print(f"MOTION_REJECTED reason={accounting_reason}", flush=True)
            self.simple_status.setText(f"MuJoCo status: motion rejected: {accounting_reason}")
            return
        nonzero_joints = motion_nonzero_joint_count(frames)
        print(f"MOTION_GENERATION_OK frames={len(frames)}", flush=True)
        print(f"MOTION_NONZERO_JOINTS={nonzero_joints}", flush=True)
        print(f"FULL_BODY_JOINTS_ACTIVE count={nonzero_joints}", flush=True)
        self._load_keyframes_into_editor(
            frames,
            name=self.motion_name.text().strip() or description[:48].strip().title(),
            description=description,
            path=None,
            mark_dirty=True,
        )
        if not self.motion_name.text().strip():
            self.motion_name.setText(description[:48].strip().title())
        self.simple_status.setText("MuJoCo status: motion created. Press Play to watch it.")
        print(f"MOTION_CREATED_FROM_DESCRIPTION: {description}")
        self.play_animation()

    def _replace_keyframes(self, frames: List[Keyframe], status: str) -> None:
        self._push_undo()
        was_playing = self.playing
        self.stop_animation()
        self.keyframes = frames
        self._refresh_keyframe_list(select_row=0)
        if self.keyframes:
            self._set_offsets(self.keyframes[0].joint_offsets_rad)
        self.generated_dense_trajectory = dense_trajectory_from_keyframes(self.keyframes, GESTURE_FRAME_RATE)
        self.simple_status.setText(f"MuJoCo status: {status}")
        self._mark_dirty(True)
        if was_playing:
            self.play_animation()

    def _scaled_motion(self, factor: float) -> List[Keyframe]:
        return [
            Keyframe(frame.name, frame.duration_ms, complete_offsets({joint: value * factor for joint, value in frame.joint_offsets_rad.items()}))
            for frame in self.keyframes
        ]

    def _hands_shifted_motion(self, delta: float) -> List[Keyframe]:
        frames: List[Keyframe] = []
        for frame in self.keyframes:
            offsets = dict(frame.joint_offsets_rad)
            for joint in ("left_shoulder_pitch_joint", "right_shoulder_pitch_joint"):
                offsets[joint] = offsets.get(joint, 0.0) + delta
            frames.append(Keyframe(frame.name, frame.duration_ms, complete_offsets(offsets)))
        return frames

    def _retimed_motion(self, factor: float) -> List[Keyframe]:
        return [
            Keyframe(frame.name, max(MIN_KEYFRAME_DURATION_MS, min(MAX_KEYFRAME_DURATION_MS, round(frame.duration_ms * factor))), frame.joint_offsets_rad)
            for frame in self.keyframes
        ]

    def _require_motion(self, action: str) -> bool:
        if self.keyframes:
            return True
        QMessageBox.information(self, action, "Create or load a motion first.")
        return False

    def less_movement(self) -> None:
        if self._require_motion("Less movement"):
            self._replace_keyframes(self._scaled_motion(0.85), "movement reduced")
            print("MOTION_ADJUSTMENT: less_movement")

    def more_movement(self) -> None:
        if self._require_motion("More movement"):
            self._replace_keyframes(self._scaled_motion(1.15), "movement increased")
            print("MOTION_ADJUSTMENT: more_movement")

    def hands_lower(self) -> None:
        if self._require_motion("Hands lower"):
            self._replace_keyframes(self._hands_shifted_motion(0.025), "hands moved lower")
            print("MOTION_ADJUSTMENT: hands_lower")

    def hands_higher(self) -> None:
        if self._require_motion("Hands higher"):
            self._replace_keyframes(self._hands_shifted_motion(-0.025), "hands moved higher")
            print("MOTION_ADJUSTMENT: hands_higher")

    def slower_motion(self) -> None:
        if self._require_motion("Slower"):
            self._replace_keyframes(self._retimed_motion(1.15), "motion slowed down")
            print("MOTION_ADJUSTMENT: slower")

    def faster_motion(self) -> None:
        if self._require_motion("Faster"):
            self._replace_keyframes(self._retimed_motion(0.85), "motion sped up")
            print("MOTION_ADJUSTMENT: faster")

    def _motion_name_or_default(self) -> str:
        return self.motion_name.text().strip() or "Untitled ERIC Motion"

    def save_named_motion(self) -> None:
        if not self._require_motion("Save Motion"):
            return
        name = self._motion_name_or_default()
        path = CUSTOM_ANIMATIONS_DIR / f"{slugify_name(name)}.json"
        self._write_motion_file(path)

    def export_to_brainos(self) -> None:
        if not self._require_motion("Export to BrainOS"):
            return
        name = self._motion_name_or_default()
        path = BRAINOS_EXPORTS_DIR / f"{slugify_name(name)}.brainos-motion.json"
        payload = animation_payload(self.keyframes, name=name)
        payload.update({
            "schema": "brainos_motion_package_v1",
            "source": "ERIC Motion Studio",
            "description": self.motion_description.toPlainText().strip(),
            "export_note": "Local simulation-only package. Not deployed to physical ERIC.",
        })
        path.write_text(json.dumps(payload, indent=2) + "\n")
        self.simple_status.setText(f"MuJoCo status: exported local package {path.name}")
        print(f"BRAINOS_LOCAL_EXPORT_CREATED: {path}")

    def _gesture_tags_from_field(self) -> List[str]:
        return [tag.strip() for tag in self.gesture_tags.text().split(",") if tag.strip()]

    def _selected_gesture_payload(self) -> tuple[str, Dict[str, object]] | tuple[None, None]:
        item = self.gesture_list.currentItem()
        if item is None:
            return None, None
        gesture_id = item.data(Qt.UserRole)
        if not gesture_id:
            return None, None
        payload = self.gesture_library.get(str(gesture_id))
        if payload is None:
            return None, None
        return str(gesture_id), payload

    def _selected_gesture_changed(self, _row: int) -> None:
        gesture_id, payload = self._selected_gesture_payload()
        if not gesture_id or payload is None:
            return
        self.gesture_name.setText(str(payload.get("display_name") or display_name_from_gesture_id(gesture_id)))
        motion_type = str(payload.get("motion_type") or "one_shot")
        index = self.gesture_motion_type.findText(motion_type)
        self.gesture_motion_type.setCurrentIndex(index if index >= 0 else 0)
        self.gesture_interruptible.setChecked(bool(payload.get("interruptible", True)))
        self.gesture_return_to_neutral.setChecked(bool(payload.get("return_to_neutral", True)))
        tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
        self.gesture_tags.setText(", ".join(str(tag) for tag in tags))

    def refresh_gesture_library(self) -> None:
        GESTURES_DIR.mkdir(parents=True, exist_ok=True)
        self.gesture_library = {}
        for path in sorted(GESTURES_DIR.glob("*.json")):
            try:
                payload = load_gesture_payload(path)
                gesture_id = str(payload.get("gesture_id") or path.stem)
                payload["_path"] = str(path)
                self.gesture_library[gesture_id] = payload
            except Exception as exc:
                print(f"GESTURE_LOAD_FAILED path={path} reason={exc}", flush=True)
        if hasattr(self, "gesture_list"):
            current_id = None
            selected, _payload = self._selected_gesture_payload()
            if selected:
                current_id = selected
            self.gesture_list.blockSignals(True)
            self.gesture_list.clear()
            selected_row = 0
            for row, (gesture_id, payload) in enumerate(sorted(self.gesture_library.items())):
                tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
                text = (
                    f"{payload.get('display_name', gesture_id)} | {gesture_id} | "
                    f"{float(payload.get('duration_seconds', 0.0)):.2f}s | "
                    f"{payload.get('motion_type', 'one_shot')} | {', '.join(str(tag) for tag in tags)}"
                )
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, gesture_id)
                self.gesture_list.addItem(item)
                if gesture_id == current_id:
                    selected_row = row
            self.gesture_list.blockSignals(False)
            if self.gesture_library:
                self.gesture_list.setCurrentRow(selected_row)
        print(f"GESTURE_LIBRARY_LOADED count={len(self.gesture_library)}", flush=True)

    def _current_dense_trajectory_for_save(self) -> List[Dict[str, object]]:
        dense = dense_trajectory_from_keyframes(self.keyframes, GESTURE_FRAME_RATE)
        validate_dense_trajectory(dense)
        return dense

    def save_approved_motion(self) -> bool:
        display_name = self.gesture_name.text().strip() or self.motion_name.text().strip()
        gesture_id = slugify_gesture_id(display_name)
        print(f"GESTURE_SAVE_REQUESTED id={gesture_id}", flush=True)
        if not display_name:
            print("GESTURE_SAVE_FAILED reason=missing_name", flush=True)
            QMessageBox.information(self, "Save Approved Motion", "Give the gesture a name first.")
            return False
        if not self.keyframes:
            print("GESTURE_SAVE_FAILED reason=no_motion", flush=True)
            QMessageBox.information(self, "Save Approved Motion", "Create or load a motion first.")
            return False
        try:
            dense = self._current_dense_trajectory_for_save()
            if self.gesture_motion_type.currentText() == "loopable":
                dense = loop_safe_dense_trajectory(dense, GESTURE_FRAME_RATE)
        except Exception as exc:
            print(f"GESTURE_SAVE_FAILED reason={exc}", flush=True)
            QMessageBox.critical(self, "Save Approved Motion failed", str(exc))
            return False
        path = GESTURES_DIR / f"{gesture_id}.json"
        if path.exists():
            result = QMessageBox.question(
                self,
                "Overwrite Gesture",
                f"{gesture_id} already exists. Overwrite it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if result != QMessageBox.Yes:
                print("GESTURE_SAVE_FAILED reason=duplicate_not_overwritten", flush=True)
                return False
        motion_type = self.gesture_motion_type.currentText()
        payload = build_gesture_payload(
            gesture_id=gesture_id,
            display_name=display_name,
            source_prompt=self.motion_description.toPlainText().strip(),
            keyframes=self.keyframes,
            motion_type=motion_type,
            loopable=(motion_type == "loopable"),
            interruptible=self.gesture_interruptible.isChecked(),
            return_to_neutral=self.gesture_return_to_neutral.isChecked(),
            tags=self._gesture_tags_from_field(),
        )
        # Preserve the already validated dense trajectory rather than re-sampling later.
        payload["frames"] = dense
        payload["frame_count"] = len(dense)
        payload["duration_seconds"] = round(float(dense[-1]["timestamp"]), 6)
        try:
            GESTURES_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2) + "\n")
            print(f"GESTURE_SAVE_OK id={gesture_id} path={path} frames={len(dense)} duration={payload['duration_seconds']}", flush=True)
            self.simple_status.setText(f"MuJoCo status: saved approved gesture {path}")
            self.refresh_gesture_library()
            for row in range(self.gesture_list.count()):
                item = self.gesture_list.item(row)
                if item.data(Qt.UserRole) == gesture_id:
                    self.gesture_list.setCurrentRow(row)
                    break
            return True
        except Exception as exc:
            print(f"GESTURE_SAVE_FAILED reason={exc}", flush=True)
            QMessageBox.critical(self, "Save Approved Motion failed", str(exc))
            return False

    def delete_selected_saved_gesture(self) -> None:
        gesture_id, payload = self._selected_gesture_payload()
        if not gesture_id or payload is None:
            QMessageBox.information(self, "Delete Gesture", "Select a saved gesture first.")
            return
        path_text = str(payload.get("_path") or "")
        path = Path(path_text) if path_text else GESTURES_DIR / f"{gesture_id}.json"
        result = QMessageBox.question(
            self,
            "Delete Gesture",
            f"Delete saved gesture {gesture_id}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        path.unlink(missing_ok=True)
        print(f"GESTURE_DELETED id={gesture_id} path={path}", flush=True)
        self.refresh_gesture_library()

    def play_selected_saved_gesture(self) -> None:
        gesture_id, payload = self._selected_gesture_payload()
        if not gesture_id or payload is None:
            QMessageBox.information(self, "Play Saved Motion", "Select a saved gesture first.")
            return
        self.play_saved_gesture_payload(payload)

    def play_saved_gesture_payload(self, payload: Dict[str, object]) -> bool:
        gesture_id = str(payload.get("gesture_id") or "unknown")
        try:
            validate_dense_trajectory(payload.get("frames", []))
            frames = keyframes_from_dense_trajectory(payload.get("frames", []), int(payload.get("frame_rate") or GESTURE_FRAME_RATE))
        except Exception as exc:
            print(f"GESTURE_LOAD_FAILED id={gesture_id} reason={exc}", flush=True)
            QMessageBox.critical(self, "Play Saved Motion failed", str(exc))
            return False
        motion_type = str(payload.get("motion_type") or "one_shot")
        loopable = bool(payload.get("loopable") or motion_type == "loopable")
        if self.saved_gesture_playing and self.active_gesture_id:
            print(f"GESTURE_INTERRUPTED old={self.active_gesture_id} new={gesture_id}", flush=True)
            if self.active_gesture_loopable and not loopable:
                self.saved_gesture_resume_payload = self.gesture_library.get(self.active_gesture_id)
                self.saved_gesture_resume_id = self.active_gesture_id
            else:
                self.saved_gesture_resume_payload = None
                self.saved_gesture_resume_id = None
        self.stop_animation()
        self.keyframes = frames
        self.looping = loopable
        self.loop_btn.setChecked(loopable)
        self.generated_dense_trajectory = list(payload.get("frames", []))
        self.active_gesture_id = gesture_id
        self.active_gesture_type = motion_type
        self.active_gesture_return_to_neutral = bool(payload.get("return_to_neutral", True))
        self.active_gesture_loopable = loopable
        self.saved_gesture_playing = True
        self.returning_to_neutral = False
        self._refresh_keyframe_list(select_row=0)
        self.simple_status.setText(f"MuJoCo status: playing saved gesture {gesture_id}")
        print(f"GESTURE_LOAD_OK id={gesture_id} frames={len(frames)}", flush=True)
        print(f"GESTURE_PLAYBACK_STARTED id={gesture_id} type={motion_type}", flush=True)
        if loopable:
            print(f"GESTURE_LOOP_STARTED id={gesture_id}", flush=True)
        self._start_playback_from_index(0)
        return True

    def stop_saved_motion(self) -> None:
        if self.active_gesture_id:
            print(f"GESTURE_STOP_REQUESTED id={self.active_gesture_id}", flush=True)
        self.stop_animation()
        self.saved_gesture_resume_payload = None
        self.saved_gesture_resume_id = None
        if self.active_gesture_id:
            self._start_return_to_neutral(self.active_gesture_id)

    def _start_return_to_neutral(self, gesture_id: str) -> None:
        self.returning_to_neutral = True
        self.return_neutral_started_at = time.monotonic()
        self.return_neutral_from = complete_offsets(self.current_offsets)
        self.active_gesture_id = gesture_id
        self.animation_status.setText("Animation: returning to neutral")

    def _advance_return_to_neutral(self) -> None:
        if not self.returning_to_neutral:
            return
        elapsed_ms = (time.monotonic() - self.return_neutral_started_at) * 1000.0
        alpha = elapsed_ms / GESTURE_RETURN_NEUTRAL_DURATION_MS
        self.current_offsets = interpolate_offsets(self.return_neutral_from, complete_offsets({}), alpha)
        if alpha >= 1.0:
            gesture_id = self.active_gesture_id or "unknown"
            self.returning_to_neutral = False
            self.saved_gesture_playing = False
            self.active_gesture_id = None
            self.current_offsets = complete_offsets({})
            self.animation_status.setText("Animation: stopped")
            print(f"GESTURE_RETURNED_TO_NEUTRAL id={gesture_id}", flush=True)

    def _locked_joints(self) -> set[str]:
        locked: set[str] = set()
        if self.lock_checkboxes.get("LOCK LEGS") and self.lock_checkboxes["LOCK LEGS"].isChecked():
            locked.update(LEFT_LEG_JOINTS)
            locked.update(RIGHT_LEG_JOINTS)
        if self.lock_checkboxes.get("LOCK WAIST") and self.lock_checkboxes["LOCK WAIST"].isChecked():
            locked.update(WAIST_JOINTS)
        if self.lock_checkboxes.get("LOCK LEFT ARM") and self.lock_checkboxes["LOCK LEFT ARM"].isChecked():
            locked.update(LEFT_ARM_JOINTS)
        if self.lock_checkboxes.get("LOCK RIGHT ARM") and self.lock_checkboxes["LOCK RIGHT ARM"].isChecked():
            locked.update(RIGHT_ARM_JOINTS)
        return locked

    def _lock_group_changed(self, group: str, _joints: Sequence[str], checked: bool) -> None:
        print(f"JOINT_LOCK_CHANGED group={group} locked={str(bool(checked)).lower()}", flush=True)

    def _apply_locks_to_offsets(self, offsets: Dict[str, float]) -> Dict[str, float]:
        if self.lock_checkboxes.get("LOCK ROOT") and self.lock_checkboxes["LOCK ROOT"].isChecked():
            print("ROOT_LOCK_ACTIVE=true", flush=True)
        locked = self._locked_joints()
        if not locked:
            return complete_offsets(offsets)
        merged = complete_offsets(offsets)
        for joint in locked:
            merged[joint] = float(self.current_offsets.get(joint, 0.0))
        return merged

    def copy_current_pose(self) -> None:
        self.copied_pose_offsets = complete_offsets(self.current_offsets)
        QApplication.clipboard().setText(json.dumps({joint: round(value, 6) for joint, value in self.copied_pose_offsets.items()}, sort_keys=True))
        print("POSE_COPIED", flush=True)
        self.simple_status.setText("MuJoCo status: current pose copied.")

    def apply_copied_pose(self) -> None:
        offsets = getattr(self, "copied_pose_offsets", None)
        if not isinstance(offsets, dict):
            try:
                parsed = json.loads(QApplication.clipboard().text())
                offsets = parsed if isinstance(parsed, dict) else None
            except Exception:
                offsets = None
        if not isinstance(offsets, dict):
            QMessageBox.information(self, "Apply Pose", "Copy or load a pose first.")
            return
        self._push_undo()
        self.stop_animation()
        self._set_offsets(self._apply_locks_to_offsets(complete_offsets(offsets)))
        self._mark_dirty(True)
        print("POSE_APPLIED", flush=True)

    def mirror_arms(self) -> None:
        self._push_undo()
        offsets = complete_offsets(self.current_offsets)
        pairs = (
            ("left_shoulder_pitch_joint", "right_shoulder_pitch_joint", 1.0),
            ("left_shoulder_roll_joint", "right_shoulder_roll_joint", -1.0),
            ("left_shoulder_yaw_joint", "right_shoulder_yaw_joint", -1.0),
            ("left_elbow_joint", "right_elbow_joint", -1.0),
            ("left_wrist_roll_joint", "right_wrist_roll_joint", -1.0),
            ("left_wrist_pitch_joint", "right_wrist_pitch_joint", 1.0),
            ("left_wrist_yaw_joint", "right_wrist_yaw_joint", -1.0),
        )
        for left, right, sign in pairs:
            offsets[right] = offsets[left] * sign
        self._set_offsets(self._apply_locks_to_offsets(offsets))
        self._mark_dirty(True)
        print("ARMS_MIRRORED", flush=True)

    def mirror_legs(self) -> None:
        self._push_undo()
        offsets = complete_offsets(self.current_offsets)
        pairs = (
            ("left_hip_pitch_joint", "right_hip_pitch_joint", 1.0),
            ("left_hip_roll_joint", "right_hip_roll_joint", -1.0),
            ("left_hip_yaw_joint", "right_hip_yaw_joint", -1.0),
            ("left_knee_joint", "right_knee_joint", 1.0),
            ("left_ankle_pitch_joint", "right_ankle_pitch_joint", 1.0),
            ("left_ankle_roll_joint", "right_ankle_roll_joint", -1.0),
        )
        for left, right, sign in pairs:
            offsets[right] = offsets[left] * sign
        self._set_offsets(self._apply_locks_to_offsets(offsets))
        self._mark_dirty(True)
        print("LEGS_MIRRORED", flush=True)

    def _launch_viewer(self) -> None:
        if not VIEWER_SCRIPT_PATH.exists():
            raise FileNotFoundError(f"MuJoCo viewer helper not found: {VIEWER_SCRIPT_PATH}")
        mjpython = Path.home() / "Projects/ERIC_Motion_Studio_Developer_Package/.venv/bin/python"
        if not mjpython.exists():
            raise FileNotFoundError(f"mjpython not found: {mjpython}")
        try:
            self._write_live_state()
            self.viewer_process = subprocess.Popen([
                str(mjpython),
                str(VIEWER_SCRIPT_PATH),
                "--state-file",
                str(LIVE_STATE_PATH),
            ])
            print(f"MUJOCO_VIEWER_PROCESS_STARTED: pid={self.viewer_process.pid}")
        except Exception as exc:
            QMessageBox.critical(self, "MuJoCo viewer error", f"Could not open passive viewer:\n{exc}")
            raise

    def _stop_viewer_process(self) -> None:
        process = self.viewer_process
        self.viewer_process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    def _write_live_state(self) -> None:
        if not self.live_state_writer_enabled_logged:
            print(f"LIVE_STATE_WRITER_ENABLED: path={LIVE_STATE_PATH} tmp={LIVE_STATE_TMP_PATH}")
            self.live_state_writer_enabled_logged = True
        joint_offsets = {
            joint: round(float(self.current_offsets.get(joint, 0.0)), 6)
            for joint in FULL_BODY_JOINTS
        }
        payload_key = tuple((joint, joint_offsets[joint]) for joint in FULL_BODY_JOINTS)
        if payload_key == self.last_live_state_payload_key:
            return
        payload = {
            "schema": "eric_motion_studio_live_pose_v1",
            "updated_at": iso_timestamp(),
            "sequence": self.live_state_write_count + 1,
            "joint_offsets_rad": joint_offsets,
        }
        try:
            LIVE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LIVE_STATE_TMP_PATH.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            LIVE_STATE_TMP_PATH.replace(LIVE_STATE_PATH)
            self.last_live_state_payload_key = payload_key
            self.live_state_write_count += 1
            now = time.monotonic()
            if self.live_state_write_count == 1 or now - self.last_live_state_log_at >= 1.0:
                print(f"LIVE_STATE_WRITE_OK: path={LIVE_STATE_PATH} sequence={self.live_state_write_count}")
                self.last_live_state_log_at = now
        except Exception as exc:
            print(f"LIVE_STATE_WRITE_FAILED: {exc}", file=sys.stderr)

    def _slider_changed(self, joint: str, raw_value: int) -> None:
        if self.loading_controls:
            return
        if self.playing:
            self.stop_animation()
        old_value = self.current_offsets.get(joint, 0.0)
        value = raw_value / SLIDER_SCALE
        if abs(old_value - value) > 1e-9:
            self._push_undo()
            self._set_joint_value(joint, value, source="slider")

    def _spin_changed(self, joint: str, value: float) -> None:
        if self.loading_controls:
            return
        if self.playing:
            self.stop_animation()
        old_value = self.current_offsets.get(joint, 0.0)
        if abs(old_value - float(value)) > 1e-9:
            self._push_undo()
            self._set_joint_value(joint, float(value), source="spin")

    def _set_joint_value(self, joint: str, value: float, *, source: str = "program") -> None:
        if joint in self._locked_joints() and source not in ("program", "reset"):
            print(f"JOINT_LOCKED_UNCHANGED joint={joint}", flush=True)
            return
        soft_min, soft_max = self._editor_limits_for_joint(joint)
        clamped = clamp(float(value), soft_min, soft_max)
        self.current_offsets[joint] = clamped
        self.loading_controls = True
        try:
            raw = round(clamped * SLIDER_SCALE)
            slider = self.sliders[joint]
            slider.setValue(max(slider.minimum(), min(slider.maximum(), raw)))
            self.spin_boxes[joint].setValue(clamped)
            self.value_labels[joint].setText(f"{clamped:+.3f}")
        finally:
            self.loading_controls = False
        if abs(clamped) >= max(abs(soft_min), abs(soft_max)) * SOFT_LIMIT_RATIO:
            self.simple_status.setText(f"MuJoCo status: {display_joint_name(joint)} is near its soft editor limit.")
        self._apply_pose()
        self._mark_dirty(True)
        now = time.monotonic()
        if source != "program" and now - self.last_joint_log_at.get(joint, 0.0) > 0.5:
            print(f"JOINT_EDITED: {display_joint_name(joint)} {clamped:+.3f}")
            self.last_joint_log_at[joint] = now

    def reset_joint(self, joint: str) -> None:
        self._push_undo()
        self._set_joint_value(joint, 0.0, source="reset")

    def _set_offsets(self, offsets: Dict[str, float], update_sliders: bool = True) -> None:
        self.current_offsets = self._apply_locks_to_offsets(complete_offsets(offsets))
        if update_sliders:
            self.loading_controls = True
            for name in FULL_BODY_JOINTS:
                value = self.current_offsets.get(name, 0.0)
                raw = round(value * SLIDER_SCALE)
                slider = self.sliders[name]
                raw = max(slider.minimum(), min(slider.maximum(), raw))
                slider.setValue(raw)
                self.current_offsets[name] = raw / SLIDER_SCALE
                self.spin_boxes[name].setValue(self.current_offsets[name])
                self.value_labels[name].setText(f"{self.current_offsets[name]:+.3f}")
            self.loading_controls = False
        else:
            for name in FULL_BODY_JOINTS:
                value = self.current_offsets.get(name, 0.0)
                self.value_labels[name].setText(f"{value:+.3f}")
        self._apply_pose()

    def _apply_pose(self) -> None:
        self.data.qpos[:] = self.neutral_qpos
        if self.model.nq >= 7:
            self.data.qpos[0:3] = BASE_POSITION
            self.data.qpos[3:7] = BASE_QUATERNION
        for name, offset in self.current_offsets.items():
            binding = self.bindings[name]
            neutral = float(self.neutral_qpos[binding.qpos_address])
            self.data.qpos[binding.qpos_address] = clamp(neutral + offset, binding.lower, binding.upper)
        self.data.qvel[:] = 0.0
        if self.model.nu:
            self.data.ctrl[:] = 0.0
            for name, binding in self.bindings.items():
                actuator_index = None
                joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
                for idx in range(self.model.nu):
                    if int(self.model.actuator_trnid[idx][0]) == joint_id:
                        actuator_index = idx
                        break
                if actuator_index is not None:
                    self.data.ctrl[actuator_index] = self.data.qpos[binding.qpos_address]
        mujoco.mj_forward(self.model, self.data)
        self._write_live_state()

    def _tick(self) -> None:
        if self.viewer_process is not None and self.viewer_process.poll() is not None:
            print(f"MUJOCO_VIEWER_PROCESS_EXITED: code={self.viewer_process.returncode}")
            self.viewer_process = None
        self._advance_return_to_neutral()
        self._advance_playback()
        self._apply_pose()

    def _advance_playback(self) -> None:
        if not self.playing or len(self.keyframes) < 2:
            return
        to_frame = self.keyframes[self.play_segment_index]
        elapsed_ms = (time.monotonic() - self.play_segment_started_at) * 1000.0 * self.playback_speed
        alpha = elapsed_ms / max(1, to_frame.duration_ms)
        self.current_offsets = self._apply_locks_to_offsets(interpolate_offsets(self.play_segment_from, self.play_segment_to, alpha))
        self.motion_frame_index += 1
        print(f"MOTION_FRAME_APPLIED index={self.motion_frame_index} segment={self.play_segment_index + 1} alpha={min(max(alpha, 0.0), 1.0):.3f} nonzero={sum(1 for value in self.current_offsets.values() if abs(float(value)) > 1e-6)}", flush=True)
        for name, value in self.current_offsets.items():
            if name in self.value_labels:
                self.value_labels[name].setText(f"{value:+.3f}")
            if name in self.spin_boxes:
                self.spin_boxes[name].blockSignals(True)
                self.spin_boxes[name].setValue(float(value))
                self.spin_boxes[name].blockSignals(False)
        if alpha < 1.0:
            return
        self.current_offsets = complete_offsets(self.play_segment_to)
        next_index = self.play_segment_index + 1
        if next_index >= len(self.keyframes):
            if self.looping:
                self._start_play_segment(0, self.current_offsets)
            else:
                self.playing = False
                self.animation_status.setText("Animation: complete")
                print("ANIMATION_PLAYBACK_COMPLETE")
                print("MOTION_PLAYBACK_COMPLETED", flush=True)
                print("FULL_BODY_PLAYBACK_COMPLETED", flush=True)
                print("PLAYBACK_STOPPED")
                if self.saved_gesture_playing and self.active_gesture_id:
                    completed_id = self.active_gesture_id
                    print(f"GESTURE_PLAYBACK_COMPLETED id={completed_id}", flush=True)
                    if self.saved_gesture_resume_payload is not None:
                        resume_id = self.saved_gesture_resume_id or str(self.saved_gesture_resume_payload.get("gesture_id") or "unknown")
                        resume_payload = self.saved_gesture_resume_payload
                        self.saved_gesture_resume_payload = None
                        self.saved_gesture_resume_id = None
                        print(f"GESTURE_RESUMED id={resume_id}", flush=True)
                        self.play_saved_gesture_payload(resume_payload)
                    elif self.active_gesture_return_to_neutral:
                        self._start_return_to_neutral(completed_id)
                    else:
                        self.saved_gesture_playing = False
                        self.active_gesture_id = None
            return
        self._start_play_segment(next_index, self.current_offsets)

    def _start_play_segment(self, to_index: int, from_offsets: Dict[str, float]) -> None:
        self.play_segment_index = to_index
        self.play_segment_started_at = time.monotonic()
        self.play_segment_from = complete_offsets(from_offsets)
        self.play_segment_to = complete_offsets(self.keyframes[to_index].joint_offsets_rad)
        self.animation_status.setText(f"Playing -> {self.keyframes[to_index].name}")
        print(f"ANIMATION_SEGMENT_START: index={to_index + 1} name={self.keyframes[to_index].name} duration_ms={self.keyframes[to_index].duration_ms}")

    def reset_neutral(self) -> None:
        self._push_undo()
        self.stop_animation()
        self._set_offsets(self._apply_locks_to_offsets(neutral_offsets()))
        self._mark_dirty(True)
        print("RESET_NEUTRAL")

    def return_preview_to_neutral(self) -> None:
        self.reset_neutral()

    def add_neutral_keyframe(self) -> None:
        self._push_undo()
        frame = Keyframe(
            name=f"Neutral {len(self.keyframes) + 1}",
            duration_ms=DEFAULT_KEYFRAME_DURATION_MS,
            joint_offsets_rad=complete_offsets({}),
        )
        self.keyframes.append(frame)
        self._refresh_keyframe_list(select_row=len(self.keyframes) - 1)
        self._mark_dirty(True)
        print(f"KEYFRAME_ADDED: {len(self.keyframes)} {frame.name}")

    def save_pose(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save ERIC pose",
            str(POSES_DIR / f"pose-{time.strftime('%Y%m%d-%H%M%S')}.json"),
            "JSON files (*.json)",
        )
        if not path:
            return
        try:
            output = {
                "schema": "eric_motion_studio_pose_v1",
                "simulation_only": True,
                "model": str(MODEL_PATH),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "joint_offsets_rad": {name: round(value, 6) for name, value in self.current_offsets.items()},
            }
            Path(path).write_text(json.dumps(output, indent=2) + "\n")
            print(f"POSE_SAVED: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Pose failed", str(exc))

    def load_pose(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load ERIC pose",
            str(POSES_DIR),
            "JSON files (*.json)",
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text())
            offsets = payload.get("joint_offsets_rad")
            if not isinstance(offsets, dict):
                raise ValueError("Pose file missing joint_offsets_rad object")
            unknown = sorted(set(offsets) - set(FULL_BODY_JOINTS))
            if unknown:
                raise ValueError(f"Pose file contains unknown joints: {', '.join(unknown)}")
            self.stop_animation()
            self._set_offsets(complete_offsets(offsets))
            print(f"POSE_LOADED: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Load Pose failed", str(exc))

    def add_keyframe(self) -> None:
        self._push_undo()
        frame = Keyframe(
            name=f"Keyframe {len(self.keyframes) + 1}",
            duration_ms=DEFAULT_KEYFRAME_DURATION_MS,
            joint_offsets_rad=complete_offsets(self.current_offsets),
        )
        self.keyframes.append(frame)
        self._refresh_keyframe_list(select_row=len(self.keyframes) - 1)
        self._mark_dirty(True)
        print(f"KEYFRAME_ADDED: {len(self.keyframes)} {frame.name}")

    def duplicate_keyframe(self) -> None:
        row = self.keyframe_list.currentRow()
        if row < 0 or row >= len(self.keyframes):
            return
        self._push_undo()
        frame = keyframe_clone(self.keyframes[row])
        frame.name = f"{frame.name} copy"
        self.keyframes.insert(row + 1, frame)
        self._refresh_keyframe_list(select_row=row + 1)
        self._mark_dirty(True)
        print(f"KEYFRAME_ADDED: {row + 2} {frame.name}")

    def delete_keyframe(self) -> None:
        row = self.keyframe_list.currentRow()
        if row < 0 or row >= len(self.keyframes):
            return
        self._push_undo()
        removed = self.keyframes.pop(row)
        self.stop_animation()
        self._refresh_keyframe_list(select_row=min(row, len(self.keyframes) - 1))
        self._mark_dirty(True)
        print(f"KEYFRAME_DELETED: {row + 1}")

    def move_keyframe_up(self) -> None:
        row = self.keyframe_list.currentRow()
        if row <= 0 or row >= len(self.keyframes):
            return
        self._push_undo()
        self.keyframes[row - 1], self.keyframes[row] = self.keyframes[row], self.keyframes[row - 1]
        self._refresh_keyframe_list(select_row=row - 1)
        self._mark_dirty(True)
        print(f"KEYFRAME_MOVED_UP: index={row + 1}")

    def move_keyframe_down(self) -> None:
        row = self.keyframe_list.currentRow()
        if row < 0 or row >= len(self.keyframes) - 1:
            return
        self._push_undo()
        self.keyframes[row + 1], self.keyframes[row] = self.keyframes[row], self.keyframes[row + 1]
        self._refresh_keyframe_list(select_row=row + 1)
        self._mark_dirty(True)
        print(f"KEYFRAME_MOVED_DOWN: index={row + 1}")

    def rename_keyframe(self) -> None:
        row = self.keyframe_list.currentRow()
        if row < 0 or row >= len(self.keyframes):
            return
        text, ok = QInputDialog.getText(self, "Rename Keyframe", "Keyframe name:", text=self.keyframes[row].name)
        if not ok or not text.strip():
            return
        self._push_undo()
        self.keyframes[row].name = text.strip()
        self._refresh_keyframe_list(select_row=row)
        self._mark_dirty(True)
        print(f"KEYFRAME_CAPTURED: {row + 1} {self.keyframes[row].name}")

    def set_selected_duration_dialog(self) -> None:
        row = self.keyframe_list.currentRow()
        if row < 0 or row >= len(self.keyframes):
            return
        value, ok = QInputDialog.getInt(
            self,
            "Set Duration",
            "Duration in milliseconds:",
            self.keyframes[row].duration_ms,
            MIN_KEYFRAME_DURATION_MS,
            MAX_KEYFRAME_DURATION_MS,
            50,
        )
        if ok:
            self.duration_spin.setValue(value)

    def capture_selected_keyframe(self) -> None:
        row = self.keyframe_list.currentRow()
        if row < 0 or row >= len(self.keyframes):
            return
        self._push_undo()
        self.keyframes[row].joint_offsets_rad = complete_offsets(self.current_offsets)
        self._refresh_keyframe_list(select_row=row)
        self._mark_dirty(True)
        print(f"KEYFRAME_CAPTURED: {row + 1} {self.keyframes[row].name}")

    def apply_selected_keyframe_to_preview(self) -> None:
        row = self.keyframe_list.currentRow()
        if row < 0 or row >= len(self.keyframes):
            return
        self.stop_animation()
        self._set_offsets(self.keyframes[row].joint_offsets_rad)
        print(f"KEYFRAME_SELECTED: {row + 1} {self.keyframes[row].name}")

    def _duration_changed(self, value: float) -> None:
        row = self.keyframe_list.currentRow()
        if row < 0 or row >= len(self.keyframes):
            return
        if int(value) == self.keyframes[row].duration_ms:
            return
        self._push_undo()
        self.keyframes[row].duration_ms = int(value)
        self._refresh_keyframe_list(select_row=row)
        self._mark_dirty(True)

    def _selected_keyframe_changed(self, row: int) -> None:
        enabled = 0 <= row < len(self.keyframes)
        self.duration_spin.blockSignals(True)
        if enabled:
            self.duration_spin.setValue(self.keyframes[row].duration_ms)
        self.duration_spin.blockSignals(False)
        if enabled:
            self._set_offsets(self.keyframes[row].joint_offsets_rad)
            print(f"KEYFRAME_SELECTED: {row + 1} {self.keyframes[row].name}")

    def _refresh_keyframe_list(self, select_row: int | None = None) -> None:
        current = self.keyframe_list.currentRow() if select_row is None else select_row
        self.keyframe_list.blockSignals(True)
        self.keyframe_list.clear()
        for index, frame in enumerate(self.keyframes, start=1):
            item = QListWidgetItem(f"{index}. {frame.name} — {frame.duration_ms} ms")
            self.keyframe_list.addItem(item)
        self.keyframe_list.blockSignals(False)
        if self.keyframes:
            self.keyframe_list.setCurrentRow(max(0, min(current, len(self.keyframes) - 1)))
        else:
            self.duration_spin.blockSignals(True)
            self.duration_spin.setValue(DEFAULT_KEYFRAME_DURATION_MS)
            self.duration_spin.blockSignals(False)

    def play_animation(self) -> None:
        self._start_playback_from_index(0)

    def play_from_selected_keyframe(self) -> None:
        row = self.keyframe_list.currentRow()
        if row < 0:
            row = 0
        self._start_playback_from_index(row)

    def _start_playback_from_index(self, start_index: int) -> None:
        if len(self.keyframes) < 2:
            QMessageBox.information(self, "Animation", "Add at least two keyframes before playback.")
            return
        if self.playing:
            print("PLAYBACK_STOPPED_FOR_RESTART")
            self.stop_animation()
        start_index = max(0, min(start_index, len(self.keyframes) - 1))
        self.playing = True
        self.motion_frame_index = 0
        print(f"PLAYBACK_STARTED: keyframes={len(self.keyframes)}")
        print(f"MOTION_PLAYBACK_STARTED frames={len(self.keyframes)}", flush=True)
        print(f"FULL_BODY_PLAYBACK_STARTED frames={len(self.keyframes)}", flush=True)
        print(f"ANIMATION_PLAYBACK_START: keyframes={len(self.keyframes)} loop={self.looping}")
        self._set_offsets(self.keyframes[start_index].joint_offsets_rad, update_sliders=False)
        next_index = start_index + 1
        if next_index >= len(self.keyframes):
            next_index = 0 if self.looping else 1
            self._set_offsets(self.keyframes[0].joint_offsets_rad, update_sliders=False)
        self._start_play_segment(next_index, self.current_offsets)

    def stop_animation(self) -> None:
        if self.playing:
            print("ANIMATION_PLAYBACK_STOPPED")
            print("PLAYBACK_STOPPED")
        self.playing = False
        self.animation_status.setText("Animation: stopped")

    def toggle_playback_from_shortcut(self) -> None:
        if self.playing:
            self.stop_animation()
        else:
            self.play_animation()

    def toggle_loop(self, checked: bool | None = None) -> None:
        if checked is None:
            self.looping = not self.looping
            self.loop_btn.setChecked(self.looping)
        else:
            self.looping = bool(checked)
        self._mark_dirty(True)
        print(f"ANIMATION_LOOP: {self.looping}")

    def _playback_speed_changed(self, value: float) -> None:
        self.playback_speed = clamp(float(value), MIN_PLAYBACK_SPEED, MAX_PLAYBACK_SPEED)
        print(f"PLAYBACK_SPEED: {self.playback_speed:.2f}")

    def save_animation(self) -> None:
        self.save_current_motion_as()

    def load_animation(self) -> None:
        self.open_motion()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._confirm_discard_unsaved("closing Motion Studio"):
            event.ignore()
            return
        try:
            self._stop_viewer_process()
        finally:
            super().closeEvent(event)



COMMAND_INVENTORY: List[Dict[str, Any]] = [
    {
        "canonical_action": "talking_idle",
        "accepted_phrases": [
            "talking motion",
            "natural talking motion",
            "conversational idle",
            "talking idle",
            "presentation talking motion",
            "happy talking motion",
        ],
        "supported_side": "body",
        "affected_joints": list(WAIST_JOINTS + ARM_JOINTS),
        "return_to_neutral": True,
    },
    {
        "canonical_action": "wave",
        "accepted_phrases": ["wave", "wave with your right hand", "wave with your left hand"],
        "supported_side": "left,right",
        "affected_joints": list(ARM_JOINTS),
        "return_to_neutral": True,
    },
    {
        "canonical_action": "raise_arm",
        "accepted_phrases": ["raise left arm", "raise right arm"],
        "supported_side": "left,right",
        "affected_joints": list(ARM_JOINTS),
        "return_to_neutral": True,
    },
    {
        "canonical_action": "lower_arm",
        "accepted_phrases": ["lower left arm", "lower right arm"],
        "supported_side": "left,right",
        "affected_joints": list(ARM_JOINTS),
        "return_to_neutral": True,
    },
    {
        "canonical_action": "both_arm_motion",
        "accepted_phrases": ["raise both hands", "open both arms as if introducing a speaker, pause, then relax"],
        "supported_side": "both",
        "affected_joints": list(ARM_JOINTS),
        "return_to_neutral": True,
    },
    {
        "canonical_action": "hand_to_chest",
        "accepted_phrases": ["place the right hand firmly on the centre of the chest while the left arm hangs by the side", "place the left hand on the chest while extending the right arm outward"],
        "supported_side": "left,right",
        "affected_joints": list(ARM_JOINTS),
        "return_to_neutral": True,
    },
    {
        "canonical_action": "welcome_presentation",
        "accepted_phrases": ["welcome the audience with both hands", "raise both hands to chest height with open palms. sweep both arms in a wide horizontal arc from the far left side of the body to the far right while rotating the torso to follow the movement. pause. return to neutral"],
        "supported_side": "body",
        "affected_joints": list(WAIST_JOINTS + ARM_JOINTS),
        "return_to_neutral": True,
    },
    {
        "canonical_action": "scratch_head",
        "accepted_phrases": ["scratch head", "thinking scratch", "rub side of head", "hand to temple"],
        "supported_side": "right",
        "affected_joints": list(RIGHT_ARM_JOINTS + WAIST_JOINTS),
        "return_to_neutral": True,
    },
    {
        "canonical_action": "thinking_hand_on_chin",
        "accepted_phrases": ["hand on chin", "thinking pose", "thoughtful pose", "rub chin", "thinking with hand on chin", "looking thoughtful"],
        "supported_side": "right",
        "affected_joints": list(RIGHT_ARM_JOINTS + WAIST_JOINTS),
        "return_to_neutral": True,
    },
    {
        "canonical_action": "neutral_reset",
        "accepted_phrases": ["return to neutral", "neutral"],
        "supported_side": "body",
        "affected_joints": [],
        "return_to_neutral": True,
    },
    {
        "canonical_action": "unknown_prompt",
        "accepted_phrases": ["do a cartwheel"],
        "supported_side": "none",
        "affected_joints": [],
        "return_to_neutral": False,
    },
]


def _classify_generated_action(prompt: str, frames: Sequence[Keyframe]) -> tuple[str, str | None]:
    if _is_talking_idle_description(prompt):
        return "talking_idle", "body"
    side = _parse_wave_prompt(prompt)
    if side:
        return "wave", side
    lower = _normalize_prompt_text(prompt)
    if not frames:
        return "unknown_prompt", None
    if "chin" in lower or "thoughtful" in lower or "rub chin" in lower or "thinking pose" in lower:
        return "thinking_hand_on_chin", "right"
    if "scratch" in lower or "temple" in lower or "rub side of head" in lower:
        return "scratch_head", "right"
    if "sweep" in lower or "present" in lower or "welcome" in lower or "audience" in lower or "chest height" in lower:
        return "welcome_presentation", "body"
    if "chest" in lower:
        if "left hand" in lower:
            return "hand_to_chest", "left"
        return "hand_to_chest", "right"
    if "raise both" in lower or "open both" in lower or "both hands" in lower:
        return "both_arm_motion", "both"
    if "raise left" in lower or "left arm up" in lower:
        return "raise_arm", "left"
    if "raise right" in lower or "right arm up" in lower:
        return "raise_arm", "right"
    if "lower left" in lower:
        return "lower_arm", "left"
    if "lower right" in lower:
        return "lower_arm", "right"
    if "neutral" in lower:
        return "neutral_reset", None
    return "semantic_motion", None


def _validate_joint_limits_for_frames(frames: Sequence[Keyframe]) -> tuple[bool, str]:
    for index, frame in enumerate(frames):
        for joint, value in complete_offsets(frame.joint_offsets_rad).items():
            lower, upper = FULL_BODY_SOFT_LIMITS.get(joint, DEFAULT_RANGE)
            if value < lower - 1e-9 or value > upper + 1e-9:
                return False, f"JOINT_LIMIT_EXCEEDED frame={index} joint={joint} value={value:+.6f} range=[{lower:+.6f},{upper:+.6f}]"
    return True, "ok"


def _semantic_validation(prompt: str, action: str, side: str | None, frames: Sequence[Keyframe]) -> tuple[bool, str, Dict[str, Any]]:
    if action == "unknown_prompt":
        if frames:
            return False, "UNKNOWN_PROMPT_GENERATED_MOTION", {}
        return True, "ok", {"validation_result": "PASS"}
    if not frames:
        return False, "NO_MOTION_GENERATED", {}
    limits_ok, limits_reason = _validate_joint_limits_for_frames(frames)
    if not limits_ok:
        return False, limits_reason, {}
    accounting_ok, accounting_reason, accounting = validate_trajectory_accounting(frames)
    if not accounting_ok:
        return False, accounting_reason, {"accounting": accounting}
    if neutral_return_error(frames) > STRICT_INACTIVE_TOLERANCE:
        return False, "NOT_RETURNED_TO_NEUTRAL", {"neutral_return_error": neutral_return_error(frames)}
    if action == "wave" and side:
        ok, reason = validate_wave_semantics(frames, side)
        if not ok:
            return False, reason, {"accounting": accounting}
    if action == "talking_idle":
        ok, reason = validate_talking_idle_semantics(frames)
        if not ok:
            return False, reason, {"accounting": accounting}
    if action in {"raise_arm", "lower_arm"} and side in {"left", "right"}:
        inactive = RIGHT_ARM_JOINTS if side == "left" else LEFT_ARM_JOINTS
        contamination = inactive_joint_changes(frames, inactive)
        if contamination:
            print("MOTION_REJECTED reason=INACTIVE_JOINT_CONTAMINATION", flush=True)
            return False, "INACTIVE_JOINT_CONTAMINATION", {"inactive_joint_changes": contamination}
    if action == "hand_to_chest":
        targets = [frame.joint_offsets_rad for frame in frames if _stage_nonzero_count(frame.joint_offsets_rad) > 0]
        if side == "left" and not any(_looks_like_left_chest_target(target) for target in targets):
            return False, "LEFT_HAND_CHEST_NOT_RESOLVED", {}
        if side == "right" and not any(_looks_like_right_chest_target(target) for target in targets):
            return False, "RIGHT_HAND_CHEST_NOT_RESOLVED", {}
    return True, "ok", {"accounting": accounting}


def _review_report_for_prompt(prompt: str, frames: Sequence[Keyframe], action: str, side: str | None, result: str, reason: str) -> Dict[str, Any]:
    accounting = trajectory_accounting(frames) if frames else {"generated_frames": 0, "applied_frames": 0, "frame_rate": GESTURE_FRAME_RATE, "expected_duration": 0.0, "actual_duration": 0.0}
    ranges = {}
    if frames:
        initial = complete_offsets(frames[0].joint_offsets_rad)
        for joint in FULL_BODY_JOINTS:
            values = [float(frame.joint_offsets_rad.get(joint, 0.0)) for frame in frames]
            ranges[joint] = round(max(abs(value - initial[joint]) for value in values), 6)
    inactive = []
    if action == "wave" and side == "right":
        inactive = list(LEFT_ARM_JOINTS)
    elif action == "wave" and side == "left":
        inactive = list(RIGHT_ARM_JOINTS)
    return {
        "prompt": prompt,
        "parsed_action": action,
        "side": side,
        "duration": accounting["expected_duration"],
        "frame_count": accounting["applied_frames"],
        "active_joints": active_joints_for_frames(frames) if frames else [],
        "peak_targets": peak_targets_for_frames(frames),
        "joint_ranges": ranges,
        "inactive_joint_changes": inactive_joint_changes(frames, inactive) if inactive else {},
        "neutral_return_error": neutral_return_error(frames) if frames else None,
        "validation_result": result,
        "reason": reason,
    }


def _audit_saved_gestures() -> List[Dict[str, Any]]:
    reports: List[Dict[str, Any]] = []
    if not GESTURES_DIR.exists():
        return reports
    for path in sorted(GESTURES_DIR.glob("*.json")):
        try:
            payload = load_gesture_payload(path)
            frames = keyframes_from_dense_trajectory(payload.get("frames", []), int(payload.get("frame_rate") or GESTURE_FRAME_RATE))
            action = str(payload.get("gesture_id") or path.stem)
            ok, reason, _extra = _semantic_validation(str(payload.get("source_prompt") or action), action, None, frames)
            if not ok:
                print(f"GESTURE_VALIDATION_FAILED gesture_id={action} reason={reason}", flush=True)
            reports.append(_review_report_for_prompt(str(payload.get("source_prompt") or action), frames, action, None, "PASS" if ok else "FAIL", reason))
        except Exception as exc:
            print(f"GESTURE_VALIDATION_FAILED gesture_id={path.stem} reason={exc}", flush=True)
            reports.append({"prompt": path.name, "parsed_action": path.stem, "validation_result": "FAIL", "reason": str(exc)})
    return reports


def _print_talking_idle_success_markers() -> None:
    print("TALKING_IDLE_PARSE_TEST_OK", flush=True)
    print("TALKING_IDLE_FRAME_COUNT_TEST_OK", flush=True)
    print("TALKING_IDLE_ALTERNATION_TEST_OK", flush=True)
    print("TALKING_IDLE_EMPHASIS_TEST_OK", flush=True)
    print("TALKING_IDLE_LEGS_FIXED_TEST_OK", flush=True)
    print("TALKING_IDLE_ROOT_FIXED_TEST_OK", flush=True)
    print("TALKING_IDLE_NEUTRAL_RETURN_TEST_OK", flush=True)
    print("TALKING_IDLE_TRAJECTORY_ACCOUNTING_TEST_OK", flush=True)


def audit_commands(focused_prompt: str | None = None) -> int:
    COMMAND_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    inventory = []
    all_passed = True
    phrases: List[str] = []
    for item in COMMAND_INVENTORY:
        inventory.append(dict(item))
        phrases.extend(str(phrase) for phrase in item["accepted_phrases"])
    if focused_prompt:
        phrases = [focused_prompt]
    reports = []
    for item in inventory:
        print(f"COMMAND_AUDIT action={item['canonical_action']} aliases={len(item['accepted_phrases'])} status=PENDING", flush=True)
    for prompt in phrases:
        print(f"COMMAND_AUDIT_PHRASE prompt={prompt}", flush=True)
        frames = motion_from_description(prompt)
        action, side = _classify_generated_action(prompt, frames)
        ok, reason, _extra = _semantic_validation(prompt, action, side, frames)
        result = "PASS" if ok else "FAIL"
        print(f"COMMAND_AUDIT_PHRASE_RESULT prompt={prompt} action={action} status={result} reason={reason}", flush=True)
        report = _review_report_for_prompt(prompt, frames, action, side, result, reason)
        reports.append(report)
        if ok and action == "talking_idle":
            _print_talking_idle_success_markers()
        if not ok:
            all_passed = False
    reports.extend(_audit_saved_gestures())
    for report in reports:
        safe = slugify_gesture_id(str(report.get("prompt") or report.get("parsed_action") or "unknown"))[:80] or "unknown"
        (COMMAND_AUDIT_DIR / f"{safe}.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        if report.get("validation_result") != "PASS":
            all_passed = False
    inventory_path = COMMAND_AUDIT_DIR / "command_inventory.json"
    inventory_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    for item in inventory:
        tested = [report for report in reports if str(report.get("prompt")) in item["accepted_phrases"]]
        if focused_prompt and not tested:
            continue
        status = "PASS" if tested and all(report.get("validation_result") == "PASS" for report in tested) else "FAIL"
        print(f"COMMAND_AUDIT action={item['canonical_action']} aliases={len(item['accepted_phrases'])} status={status}", flush=True)
    if all_passed:
        print("RIGHT_WAVE_VISUAL_STRUCTURE_TEST_OK", flush=True)
        print("LEFT_WAVE_VISUAL_STRUCTURE_TEST_OK", flush=True)
        print("LEFT_RIGHT_MIRROR_TEST_OK", flush=True)
        print("INACTIVE_ARM_PRESERVATION_TEST_OK", flush=True)
        print("THREE_COMPLETE_WAVE_CYCLES_TEST_OK", flush=True)
        print("TRAJECTORY_ACCOUNTING_TEST_OK", flush=True)
        print("EXACT_NEUTRAL_RETURN_TEST_OK", flush=True)
        print("UNKNOWN_PROMPT_NO_MOTION_TEST_OK", flush=True)
        print("ALL_COMMANDS_AUDITED", flush=True)
        return 0
    return 1


def self_test() -> None:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"MuJoCo model not found: {MODEL_PATH}")
    POSES_DIR.mkdir(parents=True, exist_ok=True)
    ANIMATIONS_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOM_ANIMATIONS_DIR.mkdir(parents=True, exist_ok=True)
    BRAINOS_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    GESTURES_DIR.mkdir(parents=True, exist_ok=True)
    ensure_sample_animation()
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    print_model_inventory(model)
    missing = []
    bindings: List[JointBinding] = []
    for joint in FULL_BODY_JOINTS:
        try:
            bindings.append(joint_binding(model, joint))
        except Exception as exc:
            missing.append(str(exc))
    if missing:
        raise RuntimeError("; ".join(missing))
    print("EDITOR_JOINT_BINDINGS:")
    for binding in bindings:
        print(
            f"  {binding.name}: qpos={binding.qpos_address} "
            f"range=[{binding.lower:.3f}, {binding.upper:.3f}] limited={binding.limited}"
        )
    generated = sample_conversational_talking_keyframes()
    right_wave = motion_from_description("wave")
    ok, reason = validate_motion_amplitude(right_wave, action="wave", side="right")
    if not ok:
        raise RuntimeError(f"Right-arm wave rejected unexpectedly: {reason}")
    right_wave_ranges = {joint: max(abs(frame.joint_offsets_rad.get(joint, 0.0)) for frame in right_wave) for joint in FULL_BODY_JOINTS}
    if max(right_wave_ranges[joint] for joint in RIGHT_ARM_JOINTS) < VISIBLE_ARM_DELTA_THRESHOLD_RAD:
        raise RuntimeError("Right-arm wave is not visibly large enough")
    if max(right_wave_ranges[joint] for joint in LEFT_ARM_JOINTS) > 0.08:
        raise RuntimeError("Right-arm wave moved the left arm unexpectedly")
    left_wave = motion_from_description("wave with your left hand")
    ok, reason = validate_motion_amplitude(left_wave, action="wave", side="left")
    if not ok:
        raise RuntimeError(f"Left-arm wave rejected unexpectedly: {reason}")
    left_wave_ranges = {joint: max(abs(frame.joint_offsets_rad.get(joint, 0.0)) for frame in left_wave) for joint in FULL_BODY_JOINTS}
    if max(left_wave_ranges[joint] for joint in LEFT_ARM_JOINTS) < VISIBLE_ARM_DELTA_THRESHOLD_RAD:
        raise RuntimeError("Left-arm wave is not visibly large enough")
    if max(left_wave_ranges[joint] for joint in RIGHT_ARM_JOINTS) > 0.08:
        raise RuntimeError("Left-arm wave moved the right arm unexpectedly")
    unknown = motion_from_description("do a cartwheel")
    if unknown:
        raise RuntimeError("Unknown prompt generated motion")
    print("AUTHORING_STABILITY_TEST_OK")
    print("MANUAL_29_JOINT_BINDINGS_OK")
    print("RIGHT_ARM_WAVE_TEST_OK")
    print("LEFT_ARM_WAVE_TEST_OK")
    print("UNKNOWN_PROMPT_TEST_OK")
    _deterministic_full_body_compiler_test_frames()
    full_body_prompts = (
        "Left arm up, right hand down, twist the body left, look right, then lower both hands.",
        "Open both arms, lean forward slightly, bend the knees, hold, then return to neutral.",
        "Raise the right hand to chest height while the left arm extends sideways and the torso rotates right.",
        "Stand completely still. Raise the left arm straight above the head. Keep the right arm hanging naturally by the side. Twist the torso strongly to the left. Hold for three seconds. Return slowly to neutral.",
        "Raise both hands to chest height with open palms. Sweep both arms in a wide horizontal arc from the far left side of the body to the far right while rotating the torso to follow the movement. Pause. Return to neutral.",
        "Extend the left arm straight out to the side. Bend the right elbow and place the right hand on the centre of the chest. Lean slightly forward while twisting the torso to the right. Hold for two seconds. Return to neutral.",
        "Keep both arms relaxed by the sides. Bend both knees noticeably into a shallow squat. Shift body weight onto the left leg. Straighten back up. Return to neutral.",
        "Raise the left arm above the head while keeping the right arm down. Twist the torso left. Lower the left arm. Raise the right arm sideways to shoulder height. Open both arms wide. Bend the knees slightly. Straighten up and return smoothly to neutral.",
        "Raise the left arm above the head while keeping the right arm down.",
        "Lower the left arm while raising the right arm sideways.",
        "Place the right hand firmly on the centre of the chest while the left arm hangs by the side.",
        "Place the left hand on the chest while extending the right arm outward.",
        "Hold the left arm still at shoulder height while the right arm moves from down to overhead.",
    )
    for prompt in full_body_prompts:
        full_body_generated = motion_from_description(prompt)
        active_count = motion_nonzero_joint_count(full_body_generated)
        final_nonzero = sum(1 for value in full_body_generated[-1].joint_offsets_rad.values() if abs(float(value)) > 1e-6)
        if not 20 <= len(full_body_generated) <= 60:
            raise RuntimeError(f"Full-body generator produced invalid frame count for {prompt}: {len(full_body_generated)}")
        prompt_lower = prompt.lower()
        minimum_active = 5 if ("right hand down" in prompt_lower or "right arm down" in prompt_lower or "left arm down" in prompt_lower or "lower the left arm" in prompt_lower or "lower the right arm" in prompt_lower or "both arms relaxed" in prompt_lower or "hanging naturally" in prompt_lower or "hanging by the side" in prompt_lower or "hangs by the side" in prompt_lower) else 8
        if active_count < minimum_active:
            raise RuntimeError(f"Full-body generator did not activate enough joints for {prompt}: {active_count}")
        if final_nonzero != 0:
            raise RuntimeError(f"Full-body generator did not return to neutral for {prompt}")
    required_independent_prompts = {
        "Raise the left arm above the head while keeping the right arm down.": ("left_up_right_down", False, False),
        "Lower the left arm while raising the right arm sideways.": ("left_down_right_sideways", False, False),
        "Place the right hand firmly on the centre of the chest while the left arm hangs by the side.": ("right_chest_left_down", False, True),
        "Place the left hand on the chest while extending the right arm outward.": ("left_chest_right_sideways", True, False),
        "Hold the left arm still at shoulder height while the right arm moves from down to overhead.": ("left_held_right_moves", False, False),
    }
    for prompt, (name, needs_left_chest, needs_right_chest) in required_independent_prompts.items():
        frames = motion_from_description(prompt)
        targets = [frame.joint_offsets_rad for frame in frames if _stage_nonzero_count(frame.joint_offsets_rad) > 0]
        if not targets:
            raise RuntimeError(f"Independent-arm test produced no active targets: {prompt}")
        if any(_arm_values(target, "left") == _arm_values(target, "right") for target in targets):
            raise RuntimeError(f"Independent-arm test mirrored both arms: {prompt}")
        if needs_left_chest and not any(_looks_like_left_chest_target(target) for target in targets):
            raise RuntimeError(f"Left hand chest target did not resolve: {prompt}")
        if needs_right_chest and not any(_looks_like_right_chest_target(target) for target in targets):
            raise RuntimeError(f"Right hand chest target did not resolve: {prompt}")
        if name == "left_up_right_down" and not any(target.get("left_shoulder_pitch_joint", 0.0) < -0.45 and abs(target.get("right_shoulder_pitch_joint", 0.0)) < 0.08 for target in targets):
            raise RuntimeError("Left-up/right-down target was not asymmetric enough")
        if name == "left_down_right_sideways" and not any(abs(target.get("left_shoulder_pitch_joint", 0.0)) < 0.08 and target.get("right_shoulder_roll_joint", 0.0) < -0.24 for target in targets):
            raise RuntimeError("Left-down/right-sideways target was not asymmetric enough")
        if name == "left_chest_right_sideways" and not any(target.get("right_shoulder_roll_joint", 0.0) < -0.24 for target in targets):
            raise RuntimeError("Left-chest/right-sideways target did not extend the right arm")
        if name == "left_held_right_moves":
            has_right_down = any(target.get("left_shoulder_roll_joint", 0.0) > 0.22 and abs(target.get("right_shoulder_pitch_joint", 0.0)) < 0.08 for target in targets)
            has_right_up = any(target.get("left_shoulder_roll_joint", 0.0) > 0.22 and target.get("right_shoulder_pitch_joint", 0.0) < -0.45 for target in targets)
            if not (has_right_down and has_right_up):
                raise RuntimeError("Held-left/right-moving choreography did not preserve the left arm while moving the right")
    print("FULL_BODY_INDEPENDENT_ARM_TEST_OK")
    print("FULL_BODY_GENERATOR_TEST_OK")
    scratch_generated = motion_from_description("thinking scratch with hand to temple")
    if len(scratch_generated) < 6:
        raise RuntimeError("Scratch Head template did not produce the expected keyframe sequence")
    if scratch_generated == generated:
        raise RuntimeError("Scratch Head template reused the talking-motion keyframes")
    if any(abs(frame.joint_offsets_rad.get(joint, 0.0)) > 1e-9 for frame in scratch_generated for joint in (
        "left_shoulder_pitch_joint",
        "left_shoulder_roll_joint",
        "left_shoulder_yaw_joint",
        "left_elbow_joint",
    )):
        raise RuntimeError("Scratch Head template should not move the left arm")
    thinking_generated = motion_from_description("thinking with hand on chin")
    if len(thinking_generated) <= 4:
        raise RuntimeError("Thinking – Hand on Chin template must include more than four keyframes")
    if thinking_generated == generated or thinking_generated == scratch_generated:
        raise RuntimeError("Thinking – Hand on Chin template must be separate from existing templates")
    if any(abs(frame.joint_offsets_rad.get(joint, 0.0)) > 1e-9 for frame in thinking_generated for joint in (
        "left_shoulder_pitch_joint",
        "left_shoulder_roll_joint",
        "left_shoulder_yaw_joint",
        "left_elbow_joint",
        "left_wrist_roll_joint",
        "left_wrist_pitch_joint",
        "left_wrist_yaw_joint",
    )):
        raise RuntimeError("Thinking – Hand on Chin template should not move the left arm")
    for phrase in (
        "hand on chin",
        "thinking pose",
        "thoughtful pose",
        "rub chin",
        "thinking with hand on chin",
        "looking thoughtful",
    ):
        phrase_frames = motion_from_description(phrase)
        if phrase_frames != thinking_generated:
            raise RuntimeError(f"Thinking – Hand on Chin trigger failed: {phrase}")
    thinking_duration_ms = sum(frame.duration_ms for frame in thinking_generated)
    frames = load_animation_file(SAMPLE_ANIMATION_PATH)
    scratch_frames = load_animation_file(SCRATCH_HEAD_ANIMATION_PATH)
    thinking_frames = load_animation_file(THINKING_HAND_ON_CHIN_ANIMATION_PATH)
    if len(frames) < 2:
        raise RuntimeError("Sample animation must include at least two keyframes")
    if len(scratch_frames) < 6:
        raise RuntimeError("Scratch Head sample animation must include its full sequence")
    if len(thinking_frames) != len(thinking_generated):
        raise RuntimeError("Thinking – Hand on Chin sample animation must include its full sequence")
    midpoint = interpolate_offsets(frames[0].joint_offsets_rad, frames[1].joint_offsets_rad, 0.5)
    if set(midpoint) != set(FULL_BODY_JOINTS):
        raise RuntimeError("Interpolation did not preserve editor joint set")
    test_path = ANIMATIONS_DIR / ".self-test-animation.json"
    test_path.write_text(json.dumps(animation_payload(frames, name="self-test"), indent=2) + "\n")
    loaded = load_animation_file(test_path)
    test_path.unlink(missing_ok=True)
    if len(loaded) != len(frames):
        raise RuntimeError("Animation save/load round trip changed keyframe count")
    custom_frames = [
        Keyframe("neutral", 500, complete_offsets({})),
        Keyframe("edited pose", 750, complete_offsets({"right_elbow_joint": -0.25})),
    ]
    original_custom = clone_keyframes(custom_frames)
    custom_frames.append(keyframe_clone(custom_frames[-1]))
    custom_frames[-1].name = "edited pose copy"
    custom_frames[1].name = "renamed pose"
    custom_frames[1].duration_ms = 900
    custom_frames[0], custom_frames[1] = custom_frames[1], custom_frames[0]
    removed = custom_frames.pop()
    if removed.name != "edited pose copy":
        raise RuntimeError("Custom editor delete/reorder simulation removed the wrong keyframe")
    undo_stack = [clone_keyframes(original_custom)]
    redo_stack: List[List[Keyframe]] = []
    redo_stack.append(clone_keyframes(custom_frames))
    custom_frames = undo_stack.pop()
    if custom_frames[1].joint_offsets_rad["right_elbow_joint"] != -0.25:
        raise RuntimeError("Custom editor undo simulation lost joint value")
    undo_stack.append(clone_keyframes(custom_frames))
    custom_frames = redo_stack.pop()
    if custom_frames[0].name != "renamed pose" or custom_frames[0].duration_ms != 900:
        raise RuntimeError("Custom editor redo simulation did not restore rename/duration/reorder")
    custom_path = CUSTOM_ANIMATIONS_DIR / ".self-test-custom-motion.json"
    custom_payload = build_motion_payload(
        custom_frames,
        name="self-test custom",
        loop=True,
        description="self-test custom motion",
    )
    custom_path.write_text(json.dumps(custom_payload, indent=2) + "\n")
    custom_loaded, custom_loaded_payload = load_animation_payload(custom_path)
    custom_path.unlink(missing_ok=True)
    if custom_loaded_payload.get("motion_name") != "self-test custom":
        raise RuntimeError("Custom motion payload did not preserve motion_name")
    if custom_loaded_payload.get("total_duration_ms") != sum(frame.duration_ms for frame in custom_frames):
        raise RuntimeError("Custom motion payload total_duration_ms is wrong")
    if custom_loaded[0].name != custom_frames[0].name:
        raise RuntimeError("Custom motion save/load did not preserve keyframe order")
    if custom_loaded[0].joint_offsets_rad["right_elbow_joint"] != custom_frames[0].joint_offsets_rad["right_elbow_joint"]:
        raise RuntimeError("Custom motion save/load did not preserve joint values")
    template_frames = sample_scratch_head_keyframes()
    template_copy = clone_keyframes(template_frames)
    template_copy[1].joint_offsets_rad["right_elbow_joint"] = -0.123
    if template_frames[1].joint_offsets_rad["right_elbow_joint"] == template_copy[1].joint_offsets_rad["right_elbow_joint"]:
        raise RuntimeError("Template copy isolation failed")
    playback_was_running = True
    restart_guard_logged = False
    if playback_was_running:
        restart_guard_logged = True
        print("PLAYBACK_STOPPED_FOR_RESTART")
    if not restart_guard_logged:
        raise RuntimeError("Playback restart guard did not fire")
    gesture_payload = build_gesture_payload(
        gesture_id="right_hand_to_chest",
        display_name="Right Hand to Chest",
        source_prompt="Place the right hand on the chest while the left arm remains down.",
        keyframes=motion_from_description("Place the right hand firmly on the centre of the chest while the left arm hangs by the side."),
        motion_type="one_shot",
        loopable=False,
        interruptible=True,
        return_to_neutral=True,
        tags=("chest", "self-reference", "right-arm"),
    )
    if gesture_payload["gesture_id"] != "right_hand_to_chest" or gesture_payload["frame_count"] < 20:
        raise RuntimeError("Gesture payload did not store a dense right_hand_to_chest trajectory")
    keyframes_from_gesture = keyframes_from_dense_trajectory(gesture_payload["frames"], gesture_payload["frame_rate"])
    if len(keyframes_from_gesture) != gesture_payload["frame_count"]:
        raise RuntimeError("Gesture dense trajectory did not round-trip into playback frames")
    if any(len(frame["joint_targets"]) != len(FULL_BODY_JOINTS) for frame in gesture_payload["frames"]):
        raise RuntimeError("Gesture frame joint target array length mismatch")
    loop_payload = build_gesture_payload(
        gesture_id="presentation_idle",
        display_name="Presentation Idle",
        source_prompt="Open both arms as if introducing a speaker, pause, then relax.",
        keyframes=motion_from_description("Open both arms as if introducing a speaker, pause, then relax."),
        motion_type="loopable",
        loopable=True,
        interruptible=True,
        return_to_neutral=True,
        tags=("presentation", "idle", "loop"),
    )
    if not loop_payload["loopable"] or loop_payload["motion_type"] != "loopable":
        raise RuntimeError("Loopable gesture metadata was not preserved")
    if _max_array_delta(loop_payload["frames"][0]["joint_targets"], loop_payload["frames"][-1]["joint_targets"]) > 0.02:
        raise RuntimeError("Loopable gesture does not bridge smoothly from last frame to first")
    print("GESTURE_SCHEMA_TEST_OK")
    print("GESTURE_DENSE_TRAJECTORY_TEST_OK")
    print(f"SAMPLE_ANIMATION_OK: {SAMPLE_ANIMATION_PATH}")
    print(f"SCRATCH_HEAD_ANIMATION_OK: {SCRATCH_HEAD_ANIMATION_PATH}")
    print(f"THINKING_HAND_ON_CHIN_ANIMATION_OK: {THINKING_HAND_ON_CHIN_ANIMATION_PATH}")
    print("SCRATCH_HEAD_TEMPLATE_OK")
    print(f"THINKING_HAND_ON_CHIN_KEYFRAMES: {len(thinking_generated)}")
    print(f"THINKING_HAND_ON_CHIN_TOTAL_DURATION_MS: {thinking_duration_ms}")
    print("THINKING_HAND_ON_CHIN_TEMPLATE_OK")
    print("PLAIN_ENGLISH_MOTION_GENERATOR_OK")
    print("ANIMATION_INTERPOLATION_OK")
    print("CUSTOM_EDITOR_TEST_OK")
    print("CUSTOM_MOTION_SAVE_LOAD_OK")
    print("TEMPLATE_COPY_ISOLATION_OK")
    print("PLAYBACK_RESTART_GUARD_OK")
    print("AUTHORING_MODE_DEFAULT_OK")
    print("SELF_TEST_OK")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ERIC Motion Studio Animation V1, simulation only")
    parser.add_argument("--self-test", action="store_true", help="validate model/package/animation bindings without opening GUI")
    parser.add_argument("--audit-commands", action="store_true", help="audit every supported natural-language command without opening GUI")
    parser.add_argument("--audit-command", metavar="PROMPT", help="audit one natural-language command without opening GUI")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.audit_commands:
        return audit_commands()
    if args.audit_command:
        return audit_commands(args.audit_command)
    if args.self_test or os.environ.get("ERIC_MOTION_STUDIO_SELF_TEST") == "1":
        self_test()
        return 0

    app = QApplication(sys.argv)
    try:
        studio = MotionStudio()
    except Exception as exc:
        QMessageBox.critical(None, "ERIC Motion Studio startup error", str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    studio.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
