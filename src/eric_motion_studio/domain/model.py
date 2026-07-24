"""Robot model metadata shared by every domain and adapter boundary."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class JointLimit:
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.lower) or not math.isfinite(self.upper):
            raise ValueError("Joint limits must be finite")
        if self.lower > self.upper:
            raise ValueError("Joint lower limit must not exceed upper limit")

    def clamp(self, value: float) -> float:
        return max(self.lower, min(self.upper, value))


@dataclass(frozen=True, slots=True)
class ModelProfile:
    model_id: str
    display_name: str
    joint_names: tuple[str, ...]
    limits: Mapping[str, JointLimit]
    groups: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        if not self.model_id or not self.display_name:
            raise ValueError("Model identity must not be empty")
        if not self.joint_names or len(set(self.joint_names)) != len(self.joint_names):
            raise ValueError("Model joint names must be non-empty and unique")
        if set(self.limits) != set(self.joint_names):
            raise ValueError("Every model joint must have exactly one limit")
        for group_name, joints in self.groups.items():
            unknown = set(joints) - set(self.joint_names)
            if unknown:
                raise ValueError(
                    f"Joint group {group_name!r} contains unknown joints: {sorted(unknown)}"
                )
        object.__setattr__(self, "limits", MappingProxyType(dict(self.limits)))
        object.__setattr__(
            self,
            "groups",
            MappingProxyType({name: tuple(joints) for name, joints in self.groups.items()}),
        )

    def joint_index(self, joint_name: str) -> int:
        try:
            return self.joint_names.index(joint_name)
        except ValueError as error:
            raise KeyError(f"Unknown joint: {joint_name}") from error


LEFT_LEG_JOINTS = (
    "left_hip_pitch_joint",
    "left_hip_roll_joint",
    "left_hip_yaw_joint",
    "left_knee_joint",
    "left_ankle_pitch_joint",
    "left_ankle_roll_joint",
)
RIGHT_LEG_JOINTS = (
    "right_hip_pitch_joint",
    "right_hip_roll_joint",
    "right_hip_yaw_joint",
    "right_knee_joint",
    "right_ankle_pitch_joint",
    "right_ankle_roll_joint",
)
WAIST_JOINTS = (
    "waist_yaw_joint",
    "waist_roll_joint",
    "waist_pitch_joint",
)
LEFT_ARM_JOINTS = (
    "left_shoulder_pitch_joint",
    "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint",
    "left_elbow_joint",
    "left_wrist_roll_joint",
    "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
)
RIGHT_ARM_JOINTS = (
    "right_shoulder_pitch_joint",
    "right_shoulder_roll_joint",
    "right_shoulder_yaw_joint",
    "right_elbow_joint",
    "right_wrist_roll_joint",
    "right_wrist_pitch_joint",
    "right_wrist_yaw_joint",
)
FULL_BODY_JOINTS = (
    *LEFT_LEG_JOINTS,
    *RIGHT_LEG_JOINTS,
    *WAIST_JOINTS,
    *LEFT_ARM_JOINTS,
    *RIGHT_ARM_JOINTS,
)

_LIMIT_VALUES = {
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

UNITREE_G1 = ModelProfile(
    model_id="unitree_g1_29dof",
    display_name="Unitree G1",
    joint_names=FULL_BODY_JOINTS,
    limits={name: JointLimit(lower, upper) for name, (lower, upper) in _LIMIT_VALUES.items()},
    groups={
        "left_leg": LEFT_LEG_JOINTS,
        "right_leg": RIGHT_LEG_JOINTS,
        "legs": (*LEFT_LEG_JOINTS, *RIGHT_LEG_JOINTS),
        "waist": WAIST_JOINTS,
        "left_arm": LEFT_ARM_JOINTS,
        "right_arm": RIGHT_ARM_JOINTS,
        "arms": (*LEFT_ARM_JOINTS, *RIGHT_ARM_JOINTS),
        "editor": (*WAIST_JOINTS, *LEFT_ARM_JOINTS, *RIGHT_ARM_JOINTS),
        "full_body": FULL_BODY_JOINTS,
    },
)
