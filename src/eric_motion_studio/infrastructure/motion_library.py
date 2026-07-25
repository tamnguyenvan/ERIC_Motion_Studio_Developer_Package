"""Layered built-in and user motion library."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from eric_motion_studio.domain import Motion
from eric_motion_studio.gestures import GestureCompiler
from eric_motion_studio.infrastructure.formats import AnimationRepository

LIBRARY_ORIGIN_KEY = "library_origin"
LIBRARY_COMMAND_KEY = "library_command"
LIBRARY_CANONICAL_ID_KEY = "library_canonical_id"
_LEGACY_LIBRARY_STATUS_KEY = "library_status"


class MotionOrigin(StrEnum):
    BUILTIN = "builtin"
    USER = "user"


@dataclass(frozen=True, slots=True)
class MotionLibraryEntry:
    entry_id: str
    display_name: str
    origin: MotionOrigin
    editable: bool
    path: Path | None = None
    canonical_id: str | None = None
    command: str = ""


def motion_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "untitled-motion"


def _metadata(motion: Motion, **updates: object) -> tuple[tuple[str, object], ...]:
    values = dict(motion.metadata)
    values.pop(_LEGACY_LIBRARY_STATUS_KEY, None)
    values.update(updates)
    return tuple(sorted(values.items()))


class MotionLibrary:
    def __init__(
        self,
        motions_dir: Path,
        compiler: GestureCompiler,
        *,
        motions: AnimationRepository | None = None,
    ) -> None:
        self.motions_dir = Path(motions_dir)
        self.compiler = compiler
        self.motions = motions or AnimationRepository()

    def entries(self) -> tuple[MotionLibraryEntry, ...]:
        builtins = tuple(
            MotionLibraryEntry(
                entry_id=f"builtin:{definition.canonical_id}",
                display_name=definition.canonical_id.replace("_", " ").title(),
                origin=MotionOrigin.BUILTIN,
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
            users.append(
                MotionLibraryEntry(
                    entry_id=f"user:{path.name}",
                    display_name=motion.name,
                    origin=MotionOrigin.USER,
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
                        LIBRARY_ORIGIN_KEY: MotionOrigin.BUILTIN.value,
                        LIBRARY_COMMAND_KEY: definition.aliases[0],
                        LIBRARY_CANONICAL_ID_KEY: canonical_id,
                    },
                ),
            )
            return motion, None
        path = self._user_path(entry_id)
        return self.motions.load(path), path

    def save(self, motion: Motion, path: Path | None = None) -> Path:
        target = path or self._available_path(motion.name)
        if target.parent != self.motions_dir:
            target = self.motions_dir / target.name
        stored = replace(
            motion,
            metadata=_metadata(
                motion,
                **{
                    LIBRARY_ORIGIN_KEY: MotionOrigin.USER.value,
                },
            ),
        )
        self.motions.save(target, stored)
        return target

    def create(self, motion: Motion) -> tuple[Motion, Path]:
        name = self._available_name(motion.name)
        stored = replace(
            motion,
            name=name,
            metadata=_metadata(
                motion,
                **{LIBRARY_ORIGIN_KEY: MotionOrigin.USER.value},
            ),
        )
        path = self.save(stored)
        return stored, path

    def duplicate(self, entry_id: str) -> tuple[Motion, Path]:
        source, _source_path = self.load(entry_id)
        stored = replace(
            source,
            name=self._available_copy_name(source.name),
            metadata=_metadata(
                source,
                **{LIBRARY_ORIGIN_KEY: MotionOrigin.USER.value},
            ),
        )
        path = self.save(stored)
        return stored, path

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

    def _available_name(self, requested: str) -> str:
        base = requested.strip() or "Untitled ERIC Motion"
        existing = {entry.display_name.casefold() for entry in self.entries()}
        if base.casefold() not in existing:
            return base
        index = 2
        while f"{base} {index}".casefold() in existing:
            index += 1
        return f"{base} {index}"

    def _available_copy_name(self, source_name: str) -> str:
        base = re.sub(r"\s+Copy(?:\s+\d+)?$", "", source_name, flags=re.IGNORECASE)
        existing = {entry.display_name.casefold() for entry in self.entries()}
        candidate = f"{base} Copy"
        if candidate.casefold() not in existing:
            return candidate
        index = 2
        while f"{candidate} {index}".casefold() in existing:
            index += 1
        return f"{candidate} {index}"

    def _available_path(self, display_name: str) -> Path:
        stem = motion_slug(display_name)
        path = self.motions_dir / f"{stem}.json"
        index = 2
        while path.exists():
            path = self.motions_dir / f"{stem}-{index}.json"
            index += 1
        return path
