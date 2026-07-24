"""Injected service interfaces and default non-Qt implementations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from eric_motion_studio.domain import Motion, TrajectoryFrame
from eric_motion_studio.gestures import CompilationResult, GestureCompiler
from eric_motion_studio.infrastructure import (
    AnimationRepository,
    BrainOSExportRepository,
)


class UnsavedDecision(StrEnum):
    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"


class MotionStore(Protocol):
    def load(self, path: Path) -> Motion:
        ...

    def save(self, path: Path, motion: Motion) -> None:
        ...


class GestureAuthoringService(Protocol):
    def compile(self, prompt: str) -> CompilationResult:
        ...


class MotionExportService(Protocol):
    def export(self, path: Path, motion: Motion) -> None:
        ...


class PlaybackOutput(Protocol):
    def apply_frame(self, frame: TrajectoryFrame) -> None:
        ...

    def reset(self) -> None:
        ...


class DialogService(Protocol):
    def select_open_motion(self) -> Path | None:
        ...

    def select_save_motion(self, suggested_name: str) -> Path | None:
        ...

    def select_export_path(self, suggested_name: str) -> Path | None:
        ...

    def confirm_unsaved(self, motion_name: str) -> UnsavedDecision:
        ...

    def show_error(self, title: str, message: str) -> None:
        ...


class RepositoryMotionStore:
    def __init__(self, repository: AnimationRepository | None = None) -> None:
        self.repository = repository or AnimationRepository()

    def load(self, path: Path) -> Motion:
        return self.repository.load(path)

    def save(self, path: Path, motion: Motion) -> None:
        self.repository.save(path, motion)


class CompilerGestureAuthoringService:
    def __init__(self, compiler: GestureCompiler | None = None) -> None:
        self.compiler = compiler or GestureCompiler.default()

    def compile(self, prompt: str) -> CompilationResult:
        return self.compiler.compile(prompt)


class RepositoryMotionExportService:
    def __init__(
        self,
        repository: BrainOSExportRepository | None = None,
    ) -> None:
        self.repository = repository or BrainOSExportRepository()

    def export(self, path: Path, motion: Motion) -> None:
        self.repository.save(path, motion)


class NullPlaybackOutput:
    def __init__(self) -> None:
        self.last_frame: TrajectoryFrame | None = None

    def apply_frame(self, frame: TrajectoryFrame) -> None:
        self.last_frame = frame

    def reset(self) -> None:
        self.last_frame = None


@dataclass(slots=True)
class ApplicationServices:
    motions: MotionStore
    gestures: GestureAuthoringService
    exports: MotionExportService
    playback: PlaybackOutput
    dialogs: DialogService
