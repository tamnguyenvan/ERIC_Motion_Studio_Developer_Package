"""Layered built-in and user motion library."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from eric_motion_studio.domain import Gesture, Motion, dense_trajectory
from eric_motion_studio.gestures import GestureCompiler
from eric_motion_studio.infrastructure.formats import (
    AnimationRepository,
    GestureRepository,
)

LIBRARY_ORIGIN_KEY = "library_origin"
LIBRARY_STATUS_KEY = "library_status"
LIBRARY_COMMAND_KEY = "library_command"
LIBRARY_CANONICAL_ID_KEY = "library_canonical_id"


class MotionOrigin(StrEnum):
    BUILTIN = "builtin"
    USER = "user"


class MotionStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


@dataclass(frozen=True, slots=True)
class MotionLibraryEntry:
    entry_id: str
    display_name: str
    origin: MotionOrigin
    status: MotionStatus
    editable: bool
    path: Path | None = None
    canonical_id: str | None = None
    command: str = ""


@dataclass(frozen=True, slots=True)
class ApprovedMotion:
    motion: Motion
    motion_path: Path
    artifact_path: Path


def motion_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "untitled-motion"


def _metadata(motion: Motion, **updates: object) -> tuple[tuple[str, object], ...]:
    values = dict(motion.metadata)
    values.update(updates)
    return tuple(sorted(values.items()))


class MotionLibrary:
    def __init__(
        self,
        motions_dir: Path,
        compiled_dir: Path,
        compiler: GestureCompiler,
        *,
        motions: AnimationRepository | None = None,
        gestures: GestureRepository | None = None,
    ) -> None:
        self.motions_dir = Path(motions_dir)
        self.compiled_dir = Path(compiled_dir)
        self.compiler = compiler
        self.motions = motions or AnimationRepository()
        self.gestures = gestures or GestureRepository()

    def entries(self) -> tuple[MotionLibraryEntry, ...]:
        builtins = tuple(
            MotionLibraryEntry(
                entry_id=f"builtin:{definition.canonical_id}",
                display_name=definition.canonical_id.replace("_", " ").title(),
                origin=MotionOrigin.BUILTIN,
                status=MotionStatus.APPROVED,
                editable=False,
                canonical_id=definition.canonical_id,
                command=definition.aliases[0],
            )
            for definition in self.compiler.registry.definitions
        )
        users: list[MotionLibraryEntry] = []
        for path in sorted(self.motions_dir.glob("*.json")):
            try:
                motion = self.motions.load(path)
            except (OSError, ValueError):
                continue
            metadata = dict(motion.metadata)
            try:
                status = MotionStatus(
                    str(metadata.get(LIBRARY_STATUS_KEY, MotionStatus.DRAFT.value))
                )
            except ValueError:
                status = MotionStatus.DRAFT
            users.append(
                MotionLibraryEntry(
                    entry_id=f"user:{path.name}",
                    display_name=motion.name,
                    origin=MotionOrigin.USER,
                    status=status,
                    editable=True,
                    path=path,
                    command=str(metadata.get(LIBRARY_COMMAND_KEY, "")),
                )
            )
        return (*builtins, *users)

    def load(self, entry_id: str) -> tuple[Motion, Path | None]:
        if entry_id.startswith("builtin:"):
            canonical_id = entry_id.removeprefix("builtin:")
            definition = self.compiler.registry.get(canonical_id)
            result = self.compiler.compile(definition.aliases[0])
            if not result.succeeded or result.motion is None:
                detail = result.error or result.resolution.message or "generation failed"
                raise ValueError(f"Could not create built-in motion: {detail}")
            motion = replace(
                result.motion,
                metadata=_metadata(
                    result.motion,
                    **{
                        LIBRARY_ORIGIN_KEY: MotionOrigin.USER.value,
                        LIBRARY_STATUS_KEY: MotionStatus.DRAFT.value,
                        LIBRARY_COMMAND_KEY: definition.aliases[0],
                        LIBRARY_CANONICAL_ID_KEY: canonical_id,
                    },
                ),
            )
            return motion, None
        path = self._user_path(entry_id)
        return self.motions.load(path), path

    def save(self, motion: Motion, path: Path | None = None) -> Path:
        target = path or self.motions_dir / f"{motion_slug(motion.name)}.json"
        if target.parent != self.motions_dir:
            target = self.motions_dir / target.name
        stored = replace(
            motion,
            metadata=_metadata(
                motion,
                **{
                    LIBRARY_ORIGIN_KEY: MotionOrigin.USER.value,
                    LIBRARY_STATUS_KEY: dict(motion.metadata).get(
                        LIBRARY_STATUS_KEY,
                        MotionStatus.DRAFT.value,
                    ),
                },
            ),
        )
        self.motions.save(target, stored)
        return target

    def approve(self, motion: Motion, path: Path | None = None) -> ApprovedMotion:
        approved = replace(
            motion,
            metadata=_metadata(
                motion,
                **{
                    LIBRARY_ORIGIN_KEY: MotionOrigin.USER.value,
                    LIBRARY_STATUS_KEY: MotionStatus.APPROVED.value,
                },
            ),
        )
        motion_path = self.save(approved, path)
        trajectory = dense_trajectory(approved.keyframes)
        metadata = dict(approved.metadata)
        gesture_id = motion_slug(approved.name).replace("-", "_")
        artifact = Gesture(
            gesture_id=gesture_id,
            display_name=approved.name,
            source_prompt=str(metadata.get(LIBRARY_COMMAND_KEY, approved.description)),
            frames=trajectory.frames,
            frame_rate=trajectory.frame_rate,
            motion_type="loopable" if approved.loop else "one_shot",
            loopable=approved.loop,
            interruptible=True,
            return_to_neutral=True,
            tags=("approved", "user"),
            robot_model=approved.model_ref,
            simulation_only=approved.simulation_only,
            metadata=(("source_motion", motion_path.name),),
        )
        artifact_path = self.compiled_dir / f"{gesture_id}.gesture.json"
        self.gestures.save(artifact_path, artifact)
        return ApprovedMotion(approved, motion_path, artifact_path)

    def delete(self, entry_id: str) -> Path:
        path = self._user_path(entry_id)
        path.unlink()
        return path

    def _user_path(self, entry_id: str) -> Path:
        if not entry_id.startswith("user:"):
            raise ValueError("Built-in motions cannot be modified or deleted")
        name = entry_id.removeprefix("user:")
        if Path(name).name != name:
            raise ValueError("Motion library entry is invalid")
        path = self.motions_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
