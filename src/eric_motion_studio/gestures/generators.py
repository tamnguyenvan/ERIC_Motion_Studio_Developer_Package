"""Generator protocol, registry, and deterministic built-in algorithms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from eric_motion_studio.domain import JointValues, Keyframe, Motion, UNITREE_G1
from eric_motion_studio.domain.values import (
    MAX_KEYFRAME_DURATION_MS,
    MIN_KEYFRAME_DURATION_MS,
)
from eric_motion_studio.gestures.definitions import GestureDefinition
from eric_motion_studio.gestures.normalization import normalize_text
from eric_motion_studio.gestures.slots import (
    GestureSlots,
    Intensity,
    Side,
    Speed,
    extract_slots,
)
from eric_motion_studio.gestures.stages import StageLibrary


GENERATED_TIMESTAMP = "1970-01-01T00:00:00+00:00"


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    command: str
    definition: GestureDefinition
    slots: GestureSlots
    stages: StageLibrary


class GestureGenerator(Protocol):
    def generate(self, request: GenerationRequest) -> Motion:
        ...


class GeneratorRegistry:
    def __init__(self) -> None:
        self._generators: dict[str, GestureGenerator] = {}

    def register(self, generator_id: str, generator: GestureGenerator) -> None:
        if not generator_id or generator_id in self._generators:
            raise ValueError(f"Generator ID is invalid or duplicated: {generator_id!r}")
        self._generators[generator_id] = generator

    def get(self, generator_id: str) -> GestureGenerator:
        try:
            return self._generators[generator_id]
        except KeyError as error:
            raise KeyError(f"No generator registered for {generator_id!r}") from error


def _duration(duration_ms: int, slots: GestureSlots) -> int:
    factor = {
        Speed.SLOW: 1.25,
        Speed.NORMAL: 1.0,
        Speed.FAST: 0.75,
    }[slots.speed]
    return max(
        MIN_KEYFRAME_DURATION_MS,
        min(MAX_KEYFRAME_DURATION_MS, round(duration_ms * factor)),
    )


def _scale_pose(pose: JointValues, slots: GestureSlots) -> JointValues:
    factor = {
        Intensity.SUBTLE: 0.65,
        Intensity.NORMAL: 0.85,
        Intensity.STRONG: 1.0,
    }[slots.intensity]
    return JointValues(
        tuple(value * factor for value in pose.values),
        pose.profile,
    )


def _mirror_pose(pose: JointValues) -> JointValues:
    mirrored: dict[str, float] = {}
    sign_flips = (
        "shoulder_roll_joint",
        "shoulder_yaw_joint",
        "elbow_joint",
        "wrist_roll_joint",
        "wrist_yaw_joint",
    )
    for name, value in pose.to_mapping().items():
        target_name = name
        if name.startswith("right_"):
            target_name = f"left_{name.removeprefix('right_')}"
        elif name.startswith("left_"):
            target_name = f"right_{name.removeprefix('left_')}"
        if name == "waist_yaw_joint" or name.endswith(sign_flips):
            value = -value
        mirrored[target_name] = value
    return JointValues.from_mapping(mirrored, pose.profile)


def _merge_poses(*poses: JointValues) -> JointValues:
    if not poses:
        return JointValues.neutral()
    values = [0.0] * len(poses[0].values)
    for pose in poses:
        for index, value in enumerate(pose.values):
            if abs(value) > abs(values[index]):
                values[index] = value
    return JointValues(tuple(values), poses[0].profile)


def _side_pose(pose: JointValues, side: Side | None) -> JointValues:
    if side is Side.LEFT:
        return _mirror_pose(pose)
    if side is Side.BOTH:
        return _merge_poses(pose, _mirror_pose(pose))
    return pose


def _motion(
    request: GenerationRequest,
    frames: list[Keyframe],
) -> Motion:
    return Motion(
        name=request.definition.canonical_id.replace("_", " ").title(),
        keyframes=tuple(frames),
        description=request.command,
        simulation_only=True,
        model_ref=UNITREE_G1.display_name,
        created_at=GENERATED_TIMESTAMP,
        updated_at=GENERATED_TIMESTAMP,
        metadata=(("generator_id", request.definition.generator_id),),
    )


def _hold_duration(slots: GestureSlots) -> int:
    return round(slots.hold_seconds * 1000.0)


class StageSequenceGenerator:
    def __init__(self, sequence_id: str, *, side_aware: bool = False) -> None:
        self.sequence_id = sequence_id
        self.side_aware = side_aware

    def generate(self, request: GenerationRequest) -> Motion:
        stages = request.stages.sequence(self.sequence_id)
        frames: list[Keyframe] = []
        for index, stage in enumerate(stages):
            pose = request.stages.pose(stage.pose_id)
            if self.side_aware:
                pose = _side_pose(pose, request.slots.side)
            pose = _scale_pose(pose, request.slots)
            duration = _duration(stage.duration_ms, request.slots)
            if (
                request.slots.hold_seconds
                and index == len(stages) - 2
            ):
                duration = min(
                    MAX_KEYFRAME_DURATION_MS,
                    duration + _hold_duration(request.slots),
                )
            frames.append(
                Keyframe(
                    name=f"{self.sequence_id} {index + 1}",
                    duration_ms=duration,
                    joints=pose,
                )
            )
        if not request.slots.neutral_return and len(frames) > 1:
            frames.pop()
        return _motion(request, frames)


class WaveGenerator:
    def generate(self, request: GenerationRequest) -> Motion:
        neutral = request.stages.pose("neutral")
        base = _side_pose(
            request.stages.pose("wave_right"),
            request.slots.side,
        )
        base = _scale_pose(base, request.slots)
        frames = [Keyframe("wave neutral", 100, neutral)]
        frames.append(
            Keyframe(
                "wave raise",
                _duration(650, request.slots),
                base,
            )
        )
        yaw_name = (
            "left_shoulder_yaw_joint"
            if request.slots.side is Side.LEFT
            else "right_shoulder_yaw_joint"
        )
        yaw_index = UNITREE_G1.joint_index(yaw_name)
        direction = -1.0 if request.slots.side is Side.LEFT else 1.0
        for cycle in range(3):
            for extremum in (-0.28, 0.28):
                values = list(base.values)
                values[yaw_index] = values[yaw_index] + extremum * direction
                frames.append(
                    Keyframe(
                        f"wave cycle {cycle + 1}",
                        _duration(260, request.slots),
                        JointValues(tuple(values)),
                    )
                )
        if request.slots.hold_seconds:
            frames.append(
                Keyframe(
                    "wave hold",
                    max(MIN_KEYFRAME_DURATION_MS, _hold_duration(request.slots)),
                    base,
                )
            )
        if request.slots.neutral_return:
            frames.append(
                Keyframe(
                    "wave settle",
                    _duration(650, request.slots),
                    neutral,
                )
            )
        return _motion(request, frames)


class ArmGenerator:
    def __init__(self, pose_id: str) -> None:
        self.pose_id = pose_id

    def generate(self, request: GenerationRequest) -> Motion:
        neutral = request.stages.pose("neutral")
        target = _scale_pose(
            _side_pose(
                request.stages.pose(self.pose_id),
                request.slots.side,
            ),
            request.slots,
        )
        active_duration = min(
            MAX_KEYFRAME_DURATION_MS,
            _duration(800, request.slots) + _hold_duration(request.slots),
        )
        frames = [
            Keyframe("arm neutral", 100, neutral),
            Keyframe(self.pose_id, active_duration, target),
        ]
        if request.slots.neutral_return:
            frames.append(
                Keyframe("arm settle", _duration(650, request.slots), neutral)
            )
        return _motion(request, frames)


class HandToChestGenerator:
    def generate(self, request: GenerationRequest) -> Motion:
        neutral = request.stages.pose("neutral")
        chest = _side_pose(
            request.stages.pose("chest_right"),
            request.slots.side,
        )
        normalized = normalize_text(request.command)
        if "extend" in normalized or "outward" in normalized:
            extension = request.stages.pose("extend_right")
            if request.slots.side is Side.RIGHT:
                extension = _mirror_pose(extension)
            chest = _merge_poses(chest, extension)
        chest = _scale_pose(chest, request.slots)
        frames = [
            Keyframe("chest neutral", 100, neutral),
            Keyframe(
                "hand to chest",
                min(
                    MAX_KEYFRAME_DURATION_MS,
                    _duration(900, request.slots) + _hold_duration(request.slots),
                ),
                chest,
            ),
        ]
        if request.slots.neutral_return:
            frames.append(
                Keyframe("chest settle", _duration(700, request.slots), neutral)
            )
        return _motion(request, frames)


class StructuredFullBodyGenerator:
    def generate(self, request: GenerationRequest) -> Motion:
        neutral = request.stages.pose("neutral")
        clauses = request.slots.sequence or (normalize_text(request.command),)
        frames = [Keyframe("structured neutral", 100, neutral)]
        for index, clause in enumerate(clauses, start=1):
            words = set(normalize_text(clause).split())
            scored = [
                (len(words.intersection(pattern.terms)), pattern)
                for pattern in request.stages.clause_patterns
            ]
            score, pattern = max(scored, key=lambda item: item[0])
            if score == 0:
                continue
            pose = request.stages.pose(pattern.pose_id)
            clause_slots = extract_slots(clause)
            pose = _side_pose(pose, clause_slots.side or request.slots.side)
            pose = _scale_pose(pose, request.slots)
            frames.append(
                Keyframe(
                    f"structured stage {index}",
                    _duration(750, request.slots),
                    pose,
                )
            )
        if len(frames) == 1:
            frames.append(
                Keyframe(
                    "structured presentation",
                    _duration(750, request.slots),
                    _scale_pose(request.stages.pose("open_both"), request.slots),
                )
            )
        if request.slots.hold_seconds:
            active = frames[-1]
            frames[-1] = Keyframe(
                active.name,
                min(
                    MAX_KEYFRAME_DURATION_MS,
                    active.duration_ms + _hold_duration(request.slots),
                ),
                active.joints,
            )
        if request.slots.neutral_return:
            frames.append(
                Keyframe(
                    "structured settle",
                    _duration(700, request.slots),
                    neutral,
                )
            )
        return _motion(request, frames)


class NeutralGenerator:
    def generate(self, request: GenerationRequest) -> Motion:
        return _motion(
            request,
            [Keyframe("neutral", 100, request.stages.pose("neutral"))],
        )


def default_generator_registry() -> GeneratorRegistry:
    registry = GeneratorRegistry()
    registry.register("wave", WaveGenerator())
    registry.register(
        "talking_idle",
        StageSequenceGenerator("talking_idle"),
    )
    registry.register(
        "thinking_hand_on_chin",
        StageSequenceGenerator("thinking_hand_on_chin", side_aware=True),
    )
    registry.register(
        "scratch_head",
        StageSequenceGenerator("scratch_head", side_aware=True),
    )
    registry.register("raise_arm", ArmGenerator("raise_right"))
    registry.register("lower_arm", ArmGenerator("lower_right"))
    registry.register(
        "both_arm_motion",
        StageSequenceGenerator("both_arm_motion"),
    )
    registry.register("hand_to_chest", HandToChestGenerator())
    registry.register(
        "welcome_presentation",
        StageSequenceGenerator("welcome_presentation"),
    )
    registry.register("structured_full_body", StructuredFullBodyGenerator())
    registry.register("neutral_reset", NeutralGenerator())
    return registry
