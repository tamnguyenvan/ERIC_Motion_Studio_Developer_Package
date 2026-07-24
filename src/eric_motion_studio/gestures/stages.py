"""Validated reusable pose and stage data."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from eric_motion_studio.domain import UNITREE_G1, JointValues, ModelProfile
from eric_motion_studio.domain.values import (
    MAX_KEYFRAME_DURATION_MS,
    MIN_KEYFRAME_DURATION_MS,
)

STAGE_SCHEMA_VERSION = 1


class StageValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Stage:
    pose_id: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class ClausePattern:
    terms: tuple[str, ...]
    pose_id: str


class StageLibrary:
    def __init__(
        self,
        poses: Mapping[str, JointValues],
        sequences: Mapping[str, tuple[Stage, ...]],
        clause_patterns: tuple[ClausePattern, ...],
    ) -> None:
        self.poses = dict(poses)
        self.sequences = dict(sequences)
        self.clause_patterns = clause_patterns

    @classmethod
    def from_path(
        cls,
        path: Path,
        profile: ModelProfile = UNITREE_G1,
    ) -> StageLibrary:
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            raise StageValidationError(f"{path} contains invalid JSON: {error}") from error
        if not isinstance(payload, dict):
            raise StageValidationError("stage library must be an object")
        if payload.get("schema_version") != STAGE_SCHEMA_VERSION:
            raise StageValidationError(f"stage schema_version must be {STAGE_SCHEMA_VERSION}")

        raw_poses = payload.get("poses")
        if not isinstance(raw_poses, dict) or not raw_poses:
            raise StageValidationError("poses must be a non-empty object")
        poses: dict[str, JointValues] = {}
        for pose_id, raw_pose in raw_poses.items():
            if not isinstance(pose_id, str) or not pose_id:
                raise StageValidationError("pose IDs must be non-empty strings")
            if not isinstance(raw_pose, dict):
                raise StageValidationError(f"pose {pose_id!r} must be an object")
            try:
                pose = JointValues.from_mapping(raw_pose, profile)
            except (TypeError, ValueError) as error:
                raise StageValidationError(f"pose {pose_id!r} is invalid: {error}") from error
            violations = [
                name
                for name, value in pose.to_mapping().items()
                if profile.limits[name].clamp(value) != value
            ]
            if violations:
                raise StageValidationError(
                    f"pose {pose_id!r} exceeds limits: {', '.join(violations)}"
                )
            poses[pose_id] = pose

        raw_sequences = payload.get("sequences")
        if not isinstance(raw_sequences, dict):
            raise StageValidationError("sequences must be an object")
        sequences: dict[str, tuple[Stage, ...]] = {}
        for sequence_id, raw_stages in raw_sequences.items():
            if not isinstance(raw_stages, list) or not raw_stages:
                raise StageValidationError(f"sequence {sequence_id!r} must be a non-empty array")
            stages = tuple(
                _stage_from_payload(raw_stage, poses, sequence_id) for raw_stage in raw_stages
            )
            sequences[sequence_id] = stages

        raw_patterns = payload.get("clause_patterns")
        if not isinstance(raw_patterns, list) or not raw_patterns:
            raise StageValidationError("clause_patterns must be a non-empty array")
        patterns = tuple(_pattern_from_payload(raw_pattern, poses) for raw_pattern in raw_patterns)
        return cls(poses, sequences, patterns)

    def pose(self, pose_id: str) -> JointValues:
        try:
            return self.poses[pose_id]
        except KeyError as error:
            raise KeyError(f"Unknown reusable pose: {pose_id}") from error

    def sequence(self, sequence_id: str) -> tuple[Stage, ...]:
        try:
            return self.sequences[sequence_id]
        except KeyError as error:
            raise KeyError(f"Unknown reusable sequence: {sequence_id}") from error


def _stage_from_payload(
    raw_stage: object,
    poses: Mapping[str, JointValues],
    sequence_id: str,
) -> Stage:
    if not isinstance(raw_stage, dict):
        raise StageValidationError(f"sequence {sequence_id!r} stages must be objects")
    pose_id = raw_stage.get("pose")
    duration = raw_stage.get("duration_ms")
    if not isinstance(pose_id, str) or pose_id not in poses:
        raise StageValidationError(f"sequence {sequence_id!r} references an unknown pose")
    if (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or not MIN_KEYFRAME_DURATION_MS <= duration <= MAX_KEYFRAME_DURATION_MS
    ):
        raise StageValidationError(f"sequence {sequence_id!r} contains an invalid duration")
    return Stage(pose_id, duration)


def _pattern_from_payload(
    raw_pattern: object,
    poses: Mapping[str, JointValues],
) -> ClausePattern:
    if not isinstance(raw_pattern, dict):
        raise StageValidationError("clause patterns must be objects")
    terms = raw_pattern.get("terms")
    pose_id = raw_pattern.get("pose")
    if (
        not isinstance(terms, list)
        or not terms
        or any(not isinstance(term, str) or not term for term in terms)
    ):
        raise StageValidationError("clause pattern terms are invalid")
    if not isinstance(pose_id, str) or pose_id not in poses:
        raise StageValidationError("clause pattern references an unknown pose")
    return ClausePattern(tuple(terms), pose_id)
