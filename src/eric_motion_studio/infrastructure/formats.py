"""Versioned JSON serializers and file repositories.

This module is pure Python and deliberately has no Qt or MuJoCo imports.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from eric_motion_studio.domain.model import UNITREE_G1, ModelProfile
from eric_motion_studio.domain.values import (
    MAX_KEYFRAME_DURATION_MS,
    MIN_KEYFRAME_DURATION_MS,
    Gesture,
    JointValues,
    Keyframe,
    Motion,
    Pose,
    TrajectoryFrame,
)

ANIMATION_SCHEMA = "eric_motion_studio_animation_v1"
ANIMATION_VERSION = 1
POSE_SCHEMA = "eric_motion_studio_pose_v1"
GESTURE_SCHEMA_VERSION = 1
BRAINOS_SCHEMA = "brainos_motion_package_v1"


class SchemaValidationError(ValueError):
    """Raised when a repository boundary receives an invalid payload."""


def _mapping(payload: object, context: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise SchemaValidationError(f"{context} must be an object")
    return payload


def _sequence(payload: object, context: str) -> Sequence[Any]:
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes):
        raise SchemaValidationError(f"{context} must be an array")
    return payload


def _required_string(payload: Mapping[str, Any], name: str, context: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{context}.{name} must be a non-empty string")
    return value


def _boolean(payload: Mapping[str, Any], name: str, default: bool) -> bool:
    value = payload.get(name, default)
    if not isinstance(value, bool):
        raise SchemaValidationError(f"{name} must be a boolean")
    return value


def _finite_number(value: object, context: str) -> float:
    if isinstance(value, bool):
        raise SchemaValidationError(f"{context} must be a finite number")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise SchemaValidationError(f"{context} must be a finite number") from error
    if not math.isfinite(numeric):
        raise SchemaValidationError(f"{context} must be a finite number")
    return numeric


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        return _mapping(json.loads(path.read_text()), str(path))
    except json.JSONDecodeError as error:
        raise SchemaValidationError(f"{path} contains invalid JSON: {error}") from error


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


class AnimationSerializer:
    def __init__(self, profile: ModelProfile = UNITREE_G1) -> None:
        self.profile = profile

    def from_payload(self, raw_payload: object) -> Motion:
        payload = _mapping(raw_payload, "animation")
        if payload.get("schema") != ANIMATION_SCHEMA:
            raise SchemaValidationError(f"animation.schema must be {ANIMATION_SCHEMA!r}")
        if payload.get("version") not in (None, ANIMATION_VERSION):
            raise SchemaValidationError(f"animation.version must be {ANIMATION_VERSION}")

        raw_frames = _sequence(payload.get("keyframes"), "animation.keyframes")
        if not raw_frames:
            raise SchemaValidationError("animation.keyframes must not be empty")
        frames = tuple(
            self._keyframe_from_payload(frame, index) for index, frame in enumerate(raw_frames)
        )
        name = payload.get("motion_name") or payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SchemaValidationError("animation name must be a non-empty string")

        declared_duration = payload.get("total_duration_ms")
        if declared_duration is not None:
            try:
                duration = int(declared_duration)
            except (TypeError, ValueError) as error:
                raise SchemaValidationError(
                    "animation.total_duration_ms must be an integer"
                ) from error
            if duration != sum(frame.duration_ms for frame in frames):
                raise SchemaValidationError("animation.total_duration_ms does not match keyframes")

        return Motion(
            name=name,
            keyframes=frames,
            loop=_boolean(payload, "loop", False),
            description=str(payload.get("description") or ""),
            simulation_only=_boolean(payload, "simulation_only", True),
            model_ref=str(payload.get("model") or self.profile.display_name),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            metadata=tuple(
                (name, value)
                for name, value in payload.items()
                if name
                not in {
                    "schema",
                    "version",
                    "simulation_only",
                    "motion_name",
                    "name",
                    "model",
                    "loop",
                    "total_duration_ms",
                    "created_at",
                    "updated_at",
                    "description",
                    "keyframes",
                }
            ),
        )

    def _keyframe_from_payload(self, raw_frame: object, index: int) -> Keyframe:
        frame = _mapping(raw_frame, f"animation.keyframes[{index}]")
        offsets = frame.get("joint_targets")
        if offsets is None:
            offsets = frame.get("joint_offsets_rad")
        offset_mapping = _mapping(
            offsets,
            f"animation.keyframes[{index}].joint_targets",
        )
        duration = frame.get("duration_ms")
        if not isinstance(duration, int) or isinstance(duration, bool):
            raise SchemaValidationError(
                f"animation.keyframes[{index}].duration_ms must be an integer"
            )
        if not MIN_KEYFRAME_DURATION_MS <= duration <= MAX_KEYFRAME_DURATION_MS:
            raise SchemaValidationError(
                f"animation.keyframes[{index}].duration_ms must be between "
                f"{MIN_KEYFRAME_DURATION_MS} and {MAX_KEYFRAME_DURATION_MS}"
            )
        try:
            joints = JointValues.from_mapping(offset_mapping, self.profile)
        except (TypeError, ValueError) as error:
            raise SchemaValidationError(
                f"animation.keyframes[{index}] has invalid joints: {error}"
            ) from error
        return Keyframe(
            name=str(frame.get("name") or f"Keyframe {index + 1}"),
            duration_ms=duration,
            joints=joints,
        )

    def to_payload(self, motion: Motion) -> dict[str, Any]:
        payload: dict[str, Any] = dict(motion.metadata)
        payload.update(
            {
                "schema": ANIMATION_SCHEMA,
                "version": ANIMATION_VERSION,
                "simulation_only": motion.simulation_only,
                "motion_name": motion.name,
                "name": motion.name,
                "model": motion.model_ref,
                "loop": motion.loop,
                "total_duration_ms": motion.total_duration_ms,
                "created_at": motion.created_at,
                "updated_at": motion.updated_at,
                "keyframes": [self._keyframe_to_payload(frame) for frame in motion.keyframes],
            }
        )
        if motion.description:
            payload["description"] = motion.description
        return payload

    @staticmethod
    def _keyframe_to_payload(frame: Keyframe) -> dict[str, Any]:
        targets = frame.joints.to_mapping(digits=6)
        return {
            "name": frame.name,
            "duration_ms": frame.duration_ms,
            "joint_targets": targets,
            "joint_offsets_rad": dict(targets),
        }


class PoseSerializer:
    def __init__(self, profile: ModelProfile = UNITREE_G1) -> None:
        self.profile = profile

    def from_payload(self, raw_payload: object) -> Pose:
        payload = _mapping(raw_payload, "pose")
        if payload.get("schema") != POSE_SCHEMA:
            raise SchemaValidationError(f"pose.schema must be {POSE_SCHEMA!r}")
        offsets = _mapping(payload.get("joint_offsets_rad"), "pose.joint_offsets_rad")
        try:
            joints = JointValues.from_mapping(offsets, self.profile)
        except (TypeError, ValueError) as error:
            raise SchemaValidationError(f"pose has invalid joints: {error}") from error
        return Pose(
            joints=joints,
            simulation_only=_boolean(payload, "simulation_only", True),
            model_ref=str(payload.get("model") or self.profile.display_name),
            created_at=str(payload.get("created_at") or ""),
            metadata=tuple(
                (name, value)
                for name, value in payload.items()
                if name
                not in {
                    "schema",
                    "simulation_only",
                    "model",
                    "created_at",
                    "joint_offsets_rad",
                }
            ),
        )

    def to_payload(self, pose: Pose) -> dict[str, Any]:
        payload: dict[str, Any] = dict(pose.metadata)
        payload.update(
            {
                "schema": POSE_SCHEMA,
                "simulation_only": pose.simulation_only,
                "model": pose.model_ref,
                "created_at": pose.created_at,
                "joint_offsets_rad": pose.joints.to_mapping(digits=6),
            }
        )
        return payload


class GestureSerializer:
    def __init__(self, profile: ModelProfile = UNITREE_G1) -> None:
        self.profile = profile

    def from_payload(self, raw_payload: object) -> Gesture:
        payload = _mapping(raw_payload, "gesture")
        if payload.get("schema_version") != GESTURE_SCHEMA_VERSION:
            raise SchemaValidationError(f"gesture.schema_version must be {GESTURE_SCHEMA_VERSION}")
        joint_names = _sequence(payload.get("joint_names"), "gesture.joint_names")
        if tuple(joint_names) != self.profile.joint_names:
            raise SchemaValidationError(
                "gesture.joint_names do not match the configured model profile"
            )
        frame_rate = payload.get("frame_rate")
        if not isinstance(frame_rate, int) or isinstance(frame_rate, bool):
            raise SchemaValidationError("gesture.frame_rate must be an integer")
        if frame_rate <= 0:
            raise SchemaValidationError("gesture.frame_rate must be positive")

        raw_frames = _sequence(payload.get("frames"), "gesture.frames")
        if not raw_frames:
            raise SchemaValidationError("gesture.frames must not be empty")
        frames = tuple(
            self._frame_from_payload(frame, index) for index, frame in enumerate(raw_frames)
        )
        if payload.get("frame_count") != len(frames):
            raise SchemaValidationError("gesture.frame_count does not match frames")
        declared_duration = _finite_number(
            payload.get("duration_seconds"),
            "gesture.duration_seconds",
        )
        if abs(declared_duration - frames[-1].timestamp) > 1e-6:
            raise SchemaValidationError("gesture.duration_seconds does not match the final frame")

        raw_tags = _sequence(payload.get("tags", []), "gesture.tags")
        if not all(isinstance(tag, str) for tag in raw_tags):
            raise SchemaValidationError("gesture.tags must contain only strings")
        robot_model = _required_string(payload, "robot_model", "gesture")
        if robot_model != self.profile.display_name:
            raise SchemaValidationError(
                "gesture.robot_model does not match the configured model profile"
            )
        return Gesture(
            gesture_id=_required_string(payload, "gesture_id", "gesture"),
            display_name=_required_string(payload, "display_name", "gesture"),
            source_prompt=str(payload.get("source_prompt") or ""),
            frames=frames,
            frame_rate=frame_rate,
            motion_type=_required_string(payload, "motion_type", "gesture"),
            loopable=_boolean(payload, "loopable", False),
            interruptible=_boolean(payload, "interruptible", True),
            return_to_neutral=_boolean(payload, "return_to_neutral", True),
            tags=tuple(raw_tags),
            robot_model=robot_model,
            simulation_only=_boolean(payload, "simulation_only", True),
            created_at=str(payload.get("created_at") or ""),
            metadata=tuple(
                (name, value)
                for name, value in payload.items()
                if name
                not in {
                    "schema_version",
                    "gesture_id",
                    "display_name",
                    "source_prompt",
                    "created_at",
                    "robot_model",
                    "simulation_only",
                    "frame_rate",
                    "duration_seconds",
                    "frame_count",
                    "motion_type",
                    "loopable",
                    "interruptible",
                    "return_to_neutral",
                    "tags",
                    "joint_names",
                    "frames",
                }
            ),
        )

    def _frame_from_payload(
        self,
        raw_frame: object,
        index: int,
    ) -> TrajectoryFrame:
        frame = _mapping(raw_frame, f"gesture.frames[{index}]")
        timestamp = _finite_number(
            frame.get("timestamp"),
            f"gesture.frames[{index}].timestamp",
        )
        raw_targets = _sequence(
            frame.get("joint_targets"),
            f"gesture.frames[{index}].joint_targets",
        )
        try:
            joints = JointValues(
                tuple(
                    _finite_number(
                        value,
                        f"gesture.frames[{index}].joint_targets",
                    )
                    for value in raw_targets
                ),
                self.profile,
            )
        except ValueError as error:
            raise SchemaValidationError(
                f"gesture.frames[{index}] has invalid joints: {error}"
            ) from error
        return TrajectoryFrame(timestamp, joints)

    def to_payload(self, gesture: Gesture) -> dict[str, Any]:
        if any(frame.joints.profile != self.profile for frame in gesture.frames):
            raise SchemaValidationError(
                "gesture frame profiles do not match the configured model profile"
            )
        payload: dict[str, Any] = dict(gesture.metadata)
        payload.update(
            {
                "schema_version": GESTURE_SCHEMA_VERSION,
                "gesture_id": gesture.gesture_id,
                "display_name": gesture.display_name,
                "source_prompt": gesture.source_prompt,
                "created_at": gesture.created_at,
                "robot_model": gesture.robot_model,
                "simulation_only": gesture.simulation_only,
                "frame_rate": gesture.frame_rate,
                "duration_seconds": round(gesture.duration_seconds, 6),
                "frame_count": len(gesture.frames),
                "motion_type": gesture.motion_type,
                "loopable": gesture.loopable,
                "interruptible": gesture.interruptible,
                "return_to_neutral": gesture.return_to_neutral,
                "tags": list(gesture.tags),
                "joint_names": list(self.profile.joint_names),
                "frames": [
                    {
                        "timestamp": round(frame.timestamp, 6),
                        "joint_targets": list(frame.joints.values),
                    }
                    for frame in gesture.frames
                ],
            }
        )
        return payload


class BrainOSSerializer:
    def __init__(self, profile: ModelProfile = UNITREE_G1) -> None:
        self.animations = AnimationSerializer(profile)

    def from_payload(self, raw_payload: object) -> Motion:
        payload = dict(_mapping(raw_payload, "BrainOS export"))
        if payload.get("schema") != BRAINOS_SCHEMA:
            raise SchemaValidationError(f"BrainOS export.schema must be {BRAINOS_SCHEMA!r}")
        if payload.get("source") != "ERIC Motion Studio":
            raise SchemaValidationError("BrainOS export.source must be 'ERIC Motion Studio'")
        version = payload.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version != 1:
            raise SchemaValidationError("BrainOS export.version must be 1")
        if payload.get("simulation_only") is not True:
            raise SchemaValidationError("BrainOS export.simulation_only must be true")
        payload.pop("source", None)
        payload.pop("export_note", None)
        payload["schema"] = ANIMATION_SCHEMA
        return self.animations.from_payload(payload)

    def to_payload(self, motion: Motion) -> dict[str, Any]:
        if not motion.simulation_only:
            raise SchemaValidationError("BrainOS exports require simulation_only to be true")
        payload = self.animations.to_payload(motion)
        payload.update(
            {
                "schema": BRAINOS_SCHEMA,
                "source": "ERIC Motion Studio",
                "description": motion.description,
                "export_note": ("Local simulation-only package. Not deployed to physical ERIC."),
            }
        )
        return payload


class AnimationRepository:
    def __init__(self, profile: ModelProfile = UNITREE_G1) -> None:
        self.serializer = AnimationSerializer(profile)

    def load(self, path: Path) -> Motion:
        return self.serializer.from_payload(_load_json(path))

    def save(self, path: Path, motion: Motion) -> None:
        _write_json(path, self.serializer.to_payload(motion))


class PoseRepository:
    def __init__(self, profile: ModelProfile = UNITREE_G1) -> None:
        self.serializer = PoseSerializer(profile)

    def load(self, path: Path) -> Pose:
        return self.serializer.from_payload(_load_json(path))

    def save(self, path: Path, pose: Pose) -> None:
        _write_json(path, self.serializer.to_payload(pose))


class GestureRepository:
    def __init__(self, profile: ModelProfile = UNITREE_G1) -> None:
        self.serializer = GestureSerializer(profile)

    def load(self, path: Path) -> Gesture:
        return self.serializer.from_payload(_load_json(path))

    def save(self, path: Path, gesture: Gesture) -> None:
        _write_json(path, self.serializer.to_payload(gesture))


class BrainOSExportRepository:
    def __init__(self, profile: ModelProfile = UNITREE_G1) -> None:
        self.serializer = BrainOSSerializer(profile)

    def load(self, path: Path) -> Motion:
        return self.serializer.from_payload(_load_json(path))

    def save(self, path: Path, motion: Motion) -> None:
        _write_json(path, self.serializer.to_payload(motion))
