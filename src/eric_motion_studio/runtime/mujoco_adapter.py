"""MuJoCo model loading and pose application without UI dependencies."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from eric_motion_studio.domain import JointValues
from eric_motion_studio.domain.model import UNITREE_G1, ModelProfile

BASE_POSITION = (0.0, 0.0, 0.79)
BASE_QUATERNION = (1.0, 0.0, 0.0, 0.0)


class SimulationMode(StrEnum):
    AUTHORING_KINEMATIC = "AUTHORING_KINEMATIC"
    DYNAMIC_VALIDATION = "DYNAMIC_VALIDATION"

    @classmethod
    def parse(cls, value: str) -> SimulationMode:
        try:
            return cls(value.strip().upper())
        except ValueError as error:
            choices = ", ".join(mode.value for mode in cls)
            raise ValueError(
                f"Unknown simulation mode {value!r}; expected one of {choices}"
            ) from error


class SafetyViolation(RuntimeError):
    """Raised when a pose or simulated state violates authoring safety rules."""


@dataclass(frozen=True, slots=True)
class JointBinding:
    joint_name: str
    joint_id: int
    qpos_address: int
    actuator_index: int | None
    lower: float
    upper: float


@dataclass(frozen=True, slots=True)
class AppliedPose:
    sequence: int | None
    joint_offsets: tuple[tuple[str, float], ...]
    root_position: tuple[float, float, float]


class MujocoAdapter:
    """Owns one MuJoCo model/data pair and its validated joint bindings."""

    def __init__(
        self,
        model_path: Path,
        *,
        profile: ModelProfile = UNITREE_G1,
        mode: SimulationMode = SimulationMode.AUTHORING_KINEMATIC,
    ) -> None:
        self.model_path = Path(model_path).expanduser().resolve(strict=False)
        if not self.model_path.is_file():
            raise FileNotFoundError(f"MuJoCo model not found: {self.model_path}")

        try:
            import mujoco
        except ImportError as error:
            raise RuntimeError("MuJoCo is required for viewer operation") from error

        self._mujoco = mujoco
        self.profile = profile
        self.mode = mode
        self.model = mujoco.MjModel.from_xml_path(str(self.model_path))
        if mode is SimulationMode.AUTHORING_KINEMATIC:
            self.model.opt.gravity[:] = 0.0
        self.data = mujoco.MjData(self.model)
        self.bindings = self._create_bindings()
        self._reset_to_neutral()
        self.neutral_qpos = self.data.qpos.copy()
        self.neutral_ctrl = self.data.ctrl.copy() if self.model.nu else None

    def _create_bindings(self) -> dict[str, JointBinding]:
        mujoco = self._mujoco
        bindings: dict[str, JointBinding] = {}
        for joint_name in self.profile.joint_names:
            joint_id = mujoco.mj_name2id(
                self.model,
                mujoco.mjtObj.mjOBJ_JOINT,
                joint_name,
            )
            if joint_id < 0:
                raise RuntimeError(f"Required joint missing from model: {joint_name}")
            actuator_index = next(
                (
                    index
                    for index in range(self.model.nu)
                    if int(self.model.actuator_trnid[index][0]) == joint_id
                ),
                None,
            )
            model_lower, model_upper = (
                (float(self.model.jnt_range[joint_id][0]), float(self.model.jnt_range[joint_id][1]))
                if bool(self.model.jnt_limited[joint_id])
                else (-math.inf, math.inf)
            )
            profile_limit = self.profile.limits[joint_name]
            bindings[joint_name] = JointBinding(
                joint_name=joint_name,
                joint_id=int(joint_id),
                qpos_address=int(self.model.jnt_qposadr[joint_id]),
                actuator_index=actuator_index,
                lower=max(model_lower, profile_limit.lower),
                upper=min(model_upper, profile_limit.upper),
            )
        return bindings

    def _reset_to_neutral(self) -> None:
        self._mujoco.mj_resetData(self.model, self.data)
        if self.model.nq < 7:
            raise RuntimeError("MuJoCo model must expose a free root joint")
        self.data.qpos[0:3] = BASE_POSITION
        self.data.qpos[3:7] = BASE_QUATERNION
        self.data.qvel[:] = 0.0
        for binding in self.bindings.values():
            self.data.qpos[binding.qpos_address] = max(
                binding.lower,
                min(binding.upper, 0.0),
            )
        self._mujoco.mj_forward(self.model, self.data)

    def reset(self) -> AppliedPose:
        self._restore_neutral()
        return self.snapshot()

    def _restore_neutral(self) -> None:
        self.data.qpos[:] = self.neutral_qpos
        self.data.qpos[0:3] = BASE_POSITION
        self.data.qpos[3:7] = BASE_QUATERNION
        self.data.qvel[:] = 0.0
        if self.neutral_ctrl is not None:
            self.data.ctrl[:] = self.neutral_ctrl

    def validate_pose(self, joints: JointValues) -> None:
        if joints.profile.model_id != self.profile.model_id:
            raise SafetyViolation(
                f"Pose model {joints.profile.model_id!r} does not match {self.profile.model_id!r}"
            )
        for joint_name, offset in joints.to_mapping().items():
            binding = self.bindings[joint_name]
            neutral = float(self.neutral_qpos[binding.qpos_address])
            target = neutral + offset
            if not math.isfinite(target):
                raise SafetyViolation(f"Non-finite target for {joint_name}")
            if not binding.lower <= target <= binding.upper:
                raise SafetyViolation(
                    f"Target for {joint_name} is outside safe range "
                    f"[{binding.lower:.6f}, {binding.upper:.6f}]"
                )

    def apply_pose(
        self,
        joints: JointValues,
        *,
        sequence: int | None = None,
    ) -> AppliedPose:
        self.validate_pose(joints)
        self._restore_neutral()
        offsets = joints.to_mapping()
        for joint_name, offset in offsets.items():
            binding = self.bindings[joint_name]
            target = float(self.neutral_qpos[binding.qpos_address]) + offset
            self.data.qpos[binding.qpos_address] = target
            if binding.actuator_index is not None:
                self.data.ctrl[binding.actuator_index] = target
        self._mujoco.mj_forward(self.model, self.data)
        self._validate_runtime_state()
        return self.snapshot(sequence=sequence)

    def _validate_runtime_state(self) -> None:
        if not all(math.isfinite(float(value)) for value in self.data.qpos):
            raise SafetyViolation("MuJoCo produced a non-finite position")
        if self.mode is SimulationMode.AUTHORING_KINEMATIC:
            actual = tuple(float(value) for value in self.data.qpos[0:7])
            expected = (*BASE_POSITION, *BASE_QUATERNION)
            if max(abs(a - b) for a, b in zip(actual, expected, strict=True)) > 1e-9:
                raise SafetyViolation("Authoring root moved from its fixed pose")
        else:
            root_height = float(self.data.qpos[2])
            if not 0.45 <= root_height <= 1.05:
                raise SafetyViolation(f"Dynamic root height is unsafe: {root_height:.6f}")

    def snapshot(self, *, sequence: int | None = None) -> AppliedPose:
        offsets = tuple(
            (
                joint_name,
                float(self.data.qpos[binding.qpos_address])
                - float(self.neutral_qpos[binding.qpos_address]),
            )
            for joint_name, binding in self.bindings.items()
        )
        return AppliedPose(
            sequence=sequence,
            joint_offsets=offsets,
            root_position=tuple(float(value) for value in self.data.qpos[0:3]),
        )

    def inventory(self) -> dict[str, Any]:
        return {
            "model_path": str(self.model_path),
            "mode": self.mode.value,
            "joints": len(self.bindings),
            "actuators": sum(
                binding.actuator_index is not None for binding in self.bindings.values()
            ),
        }
