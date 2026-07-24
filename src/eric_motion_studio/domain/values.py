"""Immutable motion, gesture, joint, and playback value objects."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Mapping

from eric_motion_studio.domain.model import ModelProfile, UNITREE_G1


DEFAULT_KEYFRAME_DURATION_MS = 900
MIN_KEYFRAME_DURATION_MS = 100
MAX_KEYFRAME_DURATION_MS = 10_000
DEFAULT_FRAME_RATE = 30
MIN_PLAYBACK_SPEED = 0.25
MAX_PLAYBACK_SPEED = 2.0


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class JointValues:
    values: tuple[float, ...]
    profile: ModelProfile = field(default=UNITREE_G1, compare=False, repr=False)

    def __post_init__(self) -> None:
        if len(self.values) != len(self.profile.joint_names):
            raise ValueError(
                f"Expected {len(self.profile.joint_names)} joint values, "
                f"received {len(self.values)}"
            )
        normalized = tuple(float(value) for value in self.values)
        if any(not math.isfinite(value) for value in normalized):
            raise ValueError("Joint values must be finite")
        object.__setattr__(self, "values", normalized)

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, object] | None = None,
        profile: ModelProfile = UNITREE_G1,
    ) -> "JointValues":
        source = values or {}
        unknown = sorted(set(source) - set(profile.joint_names))
        if unknown:
            raise ValueError(f"Unknown joints: {', '.join(unknown)}")
        if any(isinstance(value, bool) for value in source.values()):
            raise ValueError("Joint values must be numbers, not booleans")
        return cls(
            tuple(float(source.get(name, 0.0)) for name in profile.joint_names),
            profile,
        )

    @classmethod
    def neutral(cls, profile: ModelProfile = UNITREE_G1) -> "JointValues":
        return cls(tuple(0.0 for _ in profile.joint_names), profile)

    def get(self, joint_name: str) -> float:
        return self.values[self.profile.joint_index(joint_name)]

    def to_mapping(self, *, digits: int | None = None) -> dict[str, float]:
        if digits is None:
            return dict(zip(self.profile.joint_names, self.values, strict=True))
        return {
            name: round(value, digits)
            for name, value in zip(
                self.profile.joint_names,
                self.values,
                strict=True,
            )
        }


@dataclass(frozen=True, slots=True)
class Keyframe:
    name: str
    duration_ms: int
    joints: JointValues

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Keyframe name must not be empty")
        if not isinstance(self.duration_ms, int) or isinstance(self.duration_ms, bool):
            raise ValueError("Keyframe duration must be an integer")
        if not MIN_KEYFRAME_DURATION_MS <= self.duration_ms <= MAX_KEYFRAME_DURATION_MS:
            raise ValueError(
                f"Keyframe duration must be between {MIN_KEYFRAME_DURATION_MS} "
                f"and {MAX_KEYFRAME_DURATION_MS} milliseconds"
            )

    @property
    def joint_offsets_rad(self) -> dict[str, float]:
        return self.joints.to_mapping()


@dataclass(frozen=True, slots=True)
class Motion:
    name: str
    keyframes: tuple[Keyframe, ...]
    loop: bool = False
    description: str = ""
    simulation_only: bool = True
    model_ref: str = "Unitree G1"
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)
    metadata: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "keyframes", tuple(self.keyframes))
        object.__setattr__(self, "metadata", tuple(self.metadata))
        if not self.name.strip():
            raise ValueError("Motion name must not be empty")
        if not self.keyframes:
            raise ValueError("Motion must contain at least one keyframe")
        profiles = {
            (frame.joints.profile.model_id, frame.joints.profile.joint_names)
            for frame in self.keyframes
        }
        if len(profiles) != 1:
            raise ValueError("Motion keyframes must use one model profile")

    @property
    def total_duration_ms(self) -> int:
        return sum(frame.duration_ms for frame in self.keyframes)


@dataclass(frozen=True, slots=True)
class Pose:
    joints: JointValues
    simulation_only: bool = True
    model_ref: str = "Unitree G1"
    created_at: str = field(default_factory=utc_timestamp)
    metadata: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", tuple(self.metadata))


@dataclass(frozen=True, slots=True)
class TrajectoryFrame:
    timestamp: float
    joints: JointValues

    def __post_init__(self) -> None:
        if not math.isfinite(self.timestamp) or self.timestamp < 0.0:
            raise ValueError("Trajectory timestamp must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class Gesture:
    gesture_id: str
    display_name: str
    source_prompt: str
    frames: tuple[TrajectoryFrame, ...]
    frame_rate: int = DEFAULT_FRAME_RATE
    motion_type: str = "one_shot"
    loopable: bool = False
    interruptible: bool = True
    return_to_neutral: bool = True
    tags: tuple[str, ...] = ()
    robot_model: str = "Unitree G1"
    simulation_only: bool = True
    created_at: str = field(default_factory=utc_timestamp)
    metadata: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "frames", tuple(self.frames))
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "metadata", tuple(self.metadata))
        if not self.gesture_id.strip() or not self.display_name.strip():
            raise ValueError("Gesture identity must not be empty")
        if not self.frames:
            raise ValueError("Gesture must contain at least one trajectory frame")
        if self.frame_rate <= 0:
            raise ValueError("Gesture frame rate must be positive")
        previous = -1.0
        profiles = {
            (frame.joints.profile.model_id, frame.joints.profile.joint_names)
            for frame in self.frames
        }
        if len(profiles) != 1:
            raise ValueError("Gesture frames must use one model profile")
        for frame in self.frames:
            if frame.timestamp < previous:
                raise ValueError("Gesture frame timestamps must be ordered")
            previous = frame.timestamp

    @property
    def duration_seconds(self) -> float:
        return self.frames[-1].timestamp


@dataclass(frozen=True, slots=True)
class PlaybackState:
    playing: bool = False
    frame_index: int = 0
    elapsed_seconds: float = 0.0
    speed: float = 1.0

    def __post_init__(self) -> None:
        if self.frame_index < 0 or self.elapsed_seconds < 0.0:
            raise ValueError("Playback position must be non-negative")
        if not MIN_PLAYBACK_SPEED <= self.speed <= MAX_PLAYBACK_SPEED:
            raise ValueError(
                f"Playback speed must be between {MIN_PLAYBACK_SPEED} "
                f"and {MAX_PLAYBACK_SPEED}"
            )


@dataclass(frozen=True, slots=True)
class PlaybackPlan:
    frames: tuple[TrajectoryFrame, ...]
    frame_rate: int = DEFAULT_FRAME_RATE

    def __post_init__(self) -> None:
        object.__setattr__(self, "frames", tuple(self.frames))
        if self.frame_rate <= 0:
            raise ValueError("Playback frame rate must be positive")
        if not self.frames:
            raise ValueError("Playback plan must contain at least one frame")

    @property
    def duration_seconds(self) -> float:
        return self.frames[-1].timestamp
