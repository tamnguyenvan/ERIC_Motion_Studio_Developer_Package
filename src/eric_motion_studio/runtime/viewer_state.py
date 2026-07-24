"""Versioned, atomic file IPC for the external viewer."""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from eric_motion_studio.domain import JointValues
from eric_motion_studio.domain.model import UNITREE_G1, ModelProfile

LIVE_POSE_SCHEMA = "eric_motion_studio_live_pose_v1"


class MalformedStateError(ValueError):
    """Raised when a viewer state file cannot be safely interpreted."""


class StaleStateError(RuntimeError):
    """Raised when a viewer state file is older than the configured threshold."""


@dataclass(frozen=True, slots=True)
class LivePoseState:
    sequence: int
    updated_at: str
    joints: JointValues

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": LIVE_POSE_SCHEMA,
            "updated_at": self.updated_at,
            "sequence": self.sequence,
            "joint_offsets_rad": self.joints.to_mapping(digits=6),
        }


class ViewerStateStore:
    def __init__(
        self,
        path: Path,
        *,
        profile: ModelProfile = UNITREE_G1,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self.profile = profile
        self.clock = clock
        self._sequence = 0

    def write(self, joints: JointValues) -> LivePoseState:
        if joints.profile.model_id != self.profile.model_id:
            raise ValueError("Viewer state pose uses the wrong model profile")
        self._sequence += 1
        state = LivePoseState(
            sequence=self._sequence,
            updated_at=datetime.now(UTC).isoformat(timespec="milliseconds"),
            joints=joints,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    state.to_payload(),
                    handle,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
        return state

    def read(self, *, max_age_seconds: float | None = None) -> LivePoseState:
        try:
            stat = self.path.stat()
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        if max_age_seconds is not None:
            if max_age_seconds < 0:
                raise ValueError("Maximum state age must not be negative")
            age = max(0.0, self.clock() - stat.st_mtime)
            if age > max_age_seconds:
                raise StaleStateError(
                    f"Viewer state is stale ({age:.3f}s > {max_age_seconds:.3f}s)"
                )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise MalformedStateError(f"Viewer state is not valid JSON: {error.msg}") from error
        if not isinstance(payload, dict):
            raise MalformedStateError("Viewer state must be a JSON object")
        if payload.get("schema") != LIVE_POSE_SCHEMA:
            raise MalformedStateError("Viewer state schema is unsupported")
        sequence = payload.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise MalformedStateError("Viewer state sequence must be a positive integer")
        updated_at = payload.get("updated_at")
        if not isinstance(updated_at, str) or not updated_at:
            raise MalformedStateError("Viewer state timestamp is missing")
        offsets = payload.get("joint_offsets_rad")
        if not isinstance(offsets, dict):
            raise MalformedStateError("Viewer state joint offsets must be an object")
        if set(offsets) != set(self.profile.joint_names):
            raise MalformedStateError(
                "Viewer state must contain exactly the configured model joints"
            )
        if any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(float(value))
            for value in offsets.values()
        ):
            raise MalformedStateError("Viewer state joint offsets must be finite numbers")
        try:
            joints = JointValues.from_mapping(offsets, self.profile)
        except ValueError as error:
            raise MalformedStateError(str(error)) from error
        self._sequence = max(self._sequence, sequence)
        return LivePoseState(sequence, updated_at, joints)
