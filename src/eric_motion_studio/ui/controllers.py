"""Pure UI controllers with no Qt imports."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from eric_motion_studio.domain import (
    JointValues,
    Keyframe,
    Motion,
    PlaybackPlan,
    TrajectoryFrame,
    append_keyframe,
    dense_trajectory,
    insert_keyframe,
    remove_keyframe,
    replace_keyframe,
)
from eric_motion_studio.domain.values import (
    DEFAULT_KEYFRAME_DURATION_MS,
    MAX_KEYFRAME_DURATION_MS,
    MIN_KEYFRAME_DURATION_MS,
)
from eric_motion_studio.ui.services import (
    GestureAuthoringService,
    MotionExportService,
    MotionStore,
    PlaybackOutput,
    UnsavedDecision,
)

DocumentListener = Callable[["DocumentState"], None]
StatusListener = Callable[[str], None]
PlaybackListener = Callable[["PlaybackViewState"], None]
LOGGER = logging.getLogger("eric_motion_studio")


def new_motion(name: str = "Untitled ERIC Motion") -> Motion:
    return Motion(
        name=name,
        keyframes=(
            Keyframe(
                "Neutral 1",
                DEFAULT_KEYFRAME_DURATION_MS,
                JointValues.neutral(),
            ),
        ),
        model_ref="Unitree G1",
    )


@dataclass(frozen=True, slots=True)
class DocumentState:
    motion: Motion
    path: Path | None = None
    dirty: bool = False
    editable: bool = True
    selected_keyframe: int = 0
    undo_depth: int = 0
    redo_depth: int = 0


class DocumentController:
    def __init__(
        self,
        store: MotionStore,
        motion: Motion | None = None,
    ) -> None:
        self.store = store
        self._state = DocumentState(motion or new_motion())
        self._saved_motion = self._state.motion
        self._undo: list[Motion] = []
        self._redo: list[Motion] = []
        self._listeners: list[DocumentListener] = []
        self._status_listeners: list[StatusListener] = []

    @property
    def state(self) -> DocumentState:
        return self._state

    def subscribe(self, listener: DocumentListener) -> None:
        self._listeners.append(listener)
        listener(self._state)

    def subscribe_status(self, listener: StatusListener) -> None:
        self._status_listeners.append(listener)

    def report_status(self, message: str) -> None:
        LOGGER.info("ui_status", extra={"context": {"message": message}})
        for listener in self._status_listeners:
            listener(message)

    def _publish(self) -> None:
        self._state = replace(
            self._state,
            undo_depth=len(self._undo),
            redo_depth=len(self._redo),
        )
        for listener in self._listeners:
            listener(self._state)

    def _replace_motion(
        self,
        motion: Motion,
        *,
        selected_keyframe: int | None = None,
        status: str,
    ) -> None:
        if not self._state.editable:
            self.report_status("Built-in motions are read-only; duplicate to edit")
            return
        self._undo.append(self._state.motion)
        self._redo.clear()
        selection = (
            self._state.selected_keyframe if selected_keyframe is None else selected_keyframe
        )
        selection = max(0, min(selection, len(motion.keyframes) - 1))
        self._state = replace(
            self._state,
            motion=motion,
            dirty=motion != self._saved_motion,
            selected_keyframe=selection,
        )
        self._publish()
        self.report_status(status)

    def new_document(self, name: str = "Untitled ERIC Motion") -> None:
        self._undo.clear()
        self._redo.clear()
        self._state = DocumentState(new_motion(name))
        self._saved_motion = self._state.motion
        self._publish()
        self.report_status("New motion created")

    def open_document(self, path: Path) -> bool:
        try:
            motion = self.store.load(path)
        except Exception as error:
            self.report_status(f"Open failed: {error}")
            return False
        self._undo.clear()
        self._redo.clear()
        self._state = DocumentState(motion=motion, path=path)
        self._saved_motion = motion
        self._publish()
        self.report_status(f"Motion opened: {path.name}")
        return True

    def save(self, path: Path | None = None) -> bool:
        if not self._state.editable:
            self.report_status("Built-in motions are read-only; duplicate to save")
            return False
        target = path or self._state.path
        if target is None:
            self.report_status("Save path required")
            return False
        try:
            self.store.save(target, self._state.motion)
        except Exception as error:
            self.report_status(f"Save failed: {error}")
            return False
        self._saved_motion = self._state.motion
        self._state = replace(self._state, path=target, dirty=False)
        self._publish()
        self.report_status(f"Motion saved: {target.name}")
        return True

    def set_metadata(
        self,
        *,
        name: str,
        description: str,
        loop: bool,
    ) -> None:
        clean_name = name.strip() or "Untitled ERIC Motion"
        updated = replace(
            self._state.motion,
            name=clean_name,
            description=description,
            loop=loop,
        )
        if updated != self._state.motion:
            self._replace_motion(updated, status="Motion metadata updated")

    def select_keyframe(self, index: int) -> None:
        if not 0 <= index < len(self._state.motion.keyframes):
            return
        self._state = replace(self._state, selected_keyframe=index)
        self._publish()

    def add_keyframe(
        self,
        joints: JointValues,
        *,
        name: str | None = None,
    ) -> None:
        index = len(self._state.motion.keyframes)
        frame = Keyframe(
            name or f"Keyframe {index + 1}",
            DEFAULT_KEYFRAME_DURATION_MS,
            joints,
        )
        updated = append_keyframe(self._state.motion, frame)
        self._replace_motion(
            updated,
            selected_keyframe=index,
            status=f"Keyframe added: {frame.name}",
        )

    def add_neutral_keyframe(self) -> None:
        self.add_keyframe(
            JointValues.neutral(self._state.motion.keyframes[0].joints.profile),
            name=f"Neutral {len(self._state.motion.keyframes) + 1}",
        )

    def apply_preset(self, preset: str) -> None:
        LOGGER.info("motion_adjustment_requested", extra={"context": {"preset": preset}})
        factors = {
            "less_movement": 0.85,
            "more_movement": 1.15,
        }
        duration_factors = {
            "slower": 1.15,
            "faster": 0.85,
        }
        if preset in factors:
            factor = factors[preset]
            frames = [
                replace(
                    frame,
                    joints=JointValues.from_mapping(
                        {
                            name: max(
                                frame.joints.profile.limits[name].lower,
                                min(
                                    frame.joints.profile.limits[name].upper,
                                    value * factor,
                                ),
                            )
                            for name, value in frame.joints.to_mapping().items()
                        },
                        frame.joints.profile,
                    ),
                )
                for frame in self._state.motion.keyframes
            ]
            message = "Movement reduced" if preset == "less_movement" else "Movement increased"
        elif preset == "hands_lower":
            frames = [
                replace(
                    frame,
                    joints=JointValues.from_mapping(
                        {
                            **frame.joints.to_mapping(),
                            "left_shoulder_pitch_joint": frame.joints.get(
                                "left_shoulder_pitch_joint"
                            )
                            + 0.025,
                            "right_shoulder_pitch_joint": frame.joints.get(
                                "right_shoulder_pitch_joint"
                            )
                            + 0.025,
                        },
                        frame.joints.profile,
                    ),
                )
                for frame in self._state.motion.keyframes
            ]
            message = "Hands moved lower"
        elif preset in duration_factors:
            factor = duration_factors[preset]
            frames = [
                replace(
                    frame,
                    duration_ms=max(
                        MIN_KEYFRAME_DURATION_MS,
                        min(MAX_KEYFRAME_DURATION_MS, round(frame.duration_ms * factor)),
                    ),
                )
                for frame in self._state.motion.keyframes
            ]
            message = "Motion slowed down" if preset == "slower" else "Motion sped up"
        else:
            raise ValueError(f"Unknown motion preset: {preset}")
        self._replace_motion(replace(self._state.motion, keyframes=tuple(frames)), status=message)

    def less_movement(self) -> None:
        self.apply_preset("less_movement")

    def more_movement(self) -> None:
        self.apply_preset("more_movement")

    def hands_lower(self) -> None:
        self.apply_preset("hands_lower")

    def slower_motion(self) -> None:
        self.apply_preset("slower")

    def faster_motion(self) -> None:
        self.apply_preset("faster")

    def capture_selected(self, joints: JointValues) -> None:
        index = self._state.selected_keyframe
        current = self._state.motion.keyframes[index]
        updated = replace_keyframe(
            self._state.motion,
            index,
            replace(current, joints=joints),
        )
        self._replace_motion(updated, status=f"Keyframe captured: {current.name}")

    def rename_selected(self, name: str) -> None:
        clean_name = name.strip()
        if not clean_name:
            self.report_status("Keyframe name must not be empty")
            return
        index = self._state.selected_keyframe
        current = self._state.motion.keyframes[index]
        if clean_name == current.name:
            return
        updated = replace_keyframe(
            self._state.motion,
            index,
            replace(current, name=clean_name),
        )
        self._replace_motion(updated, status=f"Keyframe renamed: {clean_name}")

    def duplicate_selected(self) -> None:
        index = self._state.selected_keyframe
        current = self._state.motion.keyframes[index]
        base_name = f"{current.name} Copy"
        names = {frame.name for frame in self._state.motion.keyframes}
        name = base_name
        suffix = 2
        while name in names:
            name = f"{base_name} {suffix}"
            suffix += 1
        duplicate = replace(current, name=name)
        updated = insert_keyframe(self._state.motion, index + 1, duplicate)
        self._replace_motion(
            updated,
            selected_keyframe=index + 1,
            status=f"Keyframe duplicated: {name}",
        )

    def set_keyframe_duration(self, duration_ms: int) -> None:
        index = self._state.selected_keyframe
        current = self._state.motion.keyframes[index]
        updated = replace_keyframe(
            self._state.motion,
            index,
            replace(current, duration_ms=duration_ms),
        )
        self._replace_motion(updated, status="Keyframe duration updated")

    def delete_selected(self) -> None:
        if len(self._state.motion.keyframes) == 1:
            self.report_status("A motion must keep at least one keyframe")
            return
        index = self._state.selected_keyframe
        updated = remove_keyframe(self._state.motion, index)
        self._replace_motion(
            updated,
            selected_keyframe=min(index, len(updated.keyframes) - 1),
            status="Keyframe deleted",
        )

    def move_selected(self, offset: int) -> None:
        source = self._state.selected_keyframe
        target = source + offset
        if not 0 <= target < len(self._state.motion.keyframes):
            return
        frames = list(self._state.motion.keyframes)
        frames[source], frames[target] = frames[target], frames[source]
        self._replace_motion(
            replace(self._state.motion, keyframes=tuple(frames)),
            selected_keyframe=target,
            status="Keyframe reordered",
        )

    def load_generated_motion(self, motion: Motion) -> None:
        self._undo.clear()
        self._redo.clear()
        self._saved_motion = motion
        self._state = DocumentState(
            motion=motion,
            editable=True,
            selected_keyframe=0,
        )
        self._publish()
        self.report_status(f"Gesture activated: {motion.name}")

    def load_library_motion(
        self,
        motion: Motion,
        *,
        path: Path | None,
        editable: bool,
    ) -> None:
        self._undo.clear()
        self._redo.clear()
        self._saved_motion = motion
        self._state = DocumentState(
            motion=motion,
            path=path,
            editable=editable,
            selected_keyframe=0,
        )
        self._publish()
        self.report_status(
            f"Custom motion activated: {motion.name}"
            if editable
            else f"Built-in motion activated: {motion.name}"
        )

    def undo(self) -> None:
        if not self._state.editable or not self._undo:
            return
        previous = self._undo.pop()
        self._redo.append(self._state.motion)
        self._state = replace(
            self._state,
            motion=previous,
            dirty=previous != self._saved_motion,
            selected_keyframe=min(
                self._state.selected_keyframe,
                len(previous.keyframes) - 1,
            ),
        )
        self._publish()
        self.report_status("Undo")

    def redo(self) -> None:
        if not self._state.editable or not self._redo:
            return
        next_motion = self._redo.pop()
        self._undo.append(self._state.motion)
        self._state = replace(
            self._state,
            motion=next_motion,
            dirty=next_motion != self._saved_motion,
            selected_keyframe=min(
                self._state.selected_keyframe,
                len(next_motion.keyframes) - 1,
            ),
        )
        self._publish()
        self.report_status("Redo")

    def resolve_unsaved(
        self,
        decision: UnsavedDecision,
        save_path: Path | None = None,
    ) -> bool:
        if not self._state.dirty:
            return True
        if decision is UnsavedDecision.CANCEL:
            return False
        if decision is UnsavedDecision.DISCARD:
            return True
        return self.save(save_path)


class GestureAuthoringController:
    def __init__(
        self,
        service: GestureAuthoringService,
        documents: DocumentController,
    ) -> None:
        self.service = service
        self.documents = documents

    def activate_command(self, prompt: str) -> bool:
        clean_prompt = prompt.strip()
        if not clean_prompt:
            self.documents.report_status("Gesture command is empty")
            return False
        result = self.service.compile(clean_prompt)
        if not result.succeeded or result.motion is None:
            message = result.error or result.resolution.message or "Compilation failed"
            self.documents.report_status(f"Gesture command failed: {message}")
            return False
        self.documents.load_generated_motion(result.motion)
        LOGGER.info(
            "motion_created_from_description",
            extra={
                "context": {
                    "prompt": clean_prompt,
                    "frames": len(result.motion.keyframes),
                }
            },
        )
        return True


class ExportController:
    def __init__(
        self,
        service: MotionExportService,
        documents: DocumentController,
    ) -> None:
        self.service = service
        self.documents = documents

    def export(self, path: Path) -> bool:
        try:
            self.service.export(path, self.documents.state.motion)
        except Exception as error:
            self.documents.report_status(f"Export failed: {error}")
            return False
        self.documents.report_status(f"BrainOS local export created: {path.name}")
        return True


@dataclass(frozen=True, slots=True)
class PlaybackViewState:
    playing: bool = False
    paused: bool = False
    frame_index: int = 0
    frame_count: int = 0
    speed: float = 1.0


class PlaybackController:
    def __init__(self, output: PlaybackOutput) -> None:
        self.output = output
        self._plan: PlaybackPlan | None = None
        self._keyframe_frame_indices: tuple[int, ...] = ()
        self._loop = False
        self._elapsed = 0.0
        self._state = PlaybackViewState()
        self._listeners: list[PlaybackListener] = []
        self._status_listeners: list[StatusListener] = []

    @property
    def state(self) -> PlaybackViewState:
        return self._state

    def subscribe(self, listener: PlaybackListener) -> None:
        self._listeners.append(listener)
        listener(self._state)

    def subscribe_status(self, listener: StatusListener) -> None:
        self._status_listeners.append(listener)

    def _report_output_error(self, error: Exception) -> None:
        self._state = replace(self._state, playing=False, paused=False)
        self._publish()
        for listener in self._status_listeners:
            listener(f"Viewer unavailable: {error}")

    def _publish(self) -> None:
        for listener in self._listeners:
            listener(self._state)

    def set_motion(self, motion: Motion) -> None:
        self._plan = dense_trajectory(motion.keyframes)
        frame_indices = [0]
        current = 0
        for frame in motion.keyframes[1:]:
            current += max(1, round((frame.duration_ms / 1000.0) * self._plan.frame_rate))
            frame_indices.append(min(current, len(self._plan.frames) - 1))
        self._keyframe_frame_indices = tuple(frame_indices)
        self._loop = motion.loop
        self._elapsed = 0.0
        self._state = PlaybackViewState(
            frame_count=len(self._plan.frames),
            speed=self._state.speed,
        )
        self._publish()
        LOGGER.info(
            "trajectory_loaded",
            extra={
                "context": {
                    "keyframes": len(motion.keyframes),
                    "dense_frames": len(self._plan.frames),
                    "duration_ms": motion.total_duration_ms,
                }
            },
        )

    def play(self) -> bool:
        if self._plan is None:
            return False
        try:
            if self._state.frame_index >= len(self._plan.frames) - 1 and not self.seek(0):
                return False
            return self._start_playback()
        except Exception as error:
            self._report_output_error(error)
            return False

    def play_from_start(self) -> bool:
        if self._plan is None or not self.seek(0):
            return False
        return self._start_playback()

    def play_from_keyframe(self, keyframe_index: int) -> bool:
        if not self.seek_keyframe(keyframe_index):
            return False
        return self._start_playback()

    def _start_playback(self) -> bool:
        if self._plan is None:
            return False
        try:
            if self._state.frame_index == 0:
                self.output.apply_frame(self._plan.frames[0])
        except Exception as error:
            self._report_output_error(error)
            return False
        self._state = replace(self._state, playing=True, paused=False)
        self._publish()
        LOGGER.info(
            "playback_started",
            extra={"context": {"frame_index": self._state.frame_index, "speed": self._state.speed}},
        )
        return True

    def pause(self) -> None:
        if self._state.playing:
            self._state = replace(self._state, playing=False, paused=True)
            self._publish()
            LOGGER.info(
                "playback_paused", extra={"context": {"frame_index": self._state.frame_index}}
            )

    def stop(self) -> bool:
        self._elapsed = 0.0
        try:
            self.output.reset()
        except Exception as error:
            self._report_output_error(error)
            return False
        self._state = replace(
            self._state,
            playing=False,
            paused=False,
            frame_index=0,
        )
        self._publish()
        LOGGER.info("playback_stopped")
        return True

    def set_speed(self, speed: float) -> None:
        if not 0.25 <= speed <= 2.0:
            raise ValueError("Playback speed must be between 0.25 and 2.0")
        self._state = replace(self._state, speed=speed)
        self._publish()

    def seek(self, frame_index: int) -> bool:
        if self._plan is None:
            return False
        index = max(0, min(frame_index, len(self._plan.frames) - 1))
        frame = self._plan.frames[index]
        self._elapsed = frame.timestamp
        try:
            self.output.apply_frame(frame)
        except Exception as error:
            self._report_output_error(error)
            return False
        self._state = replace(self._state, frame_index=index)
        self._publish()
        return True

    def seek_keyframe(self, keyframe_index: int) -> bool:
        if not 0 <= keyframe_index < len(self._keyframe_frame_indices):
            return False
        return self.seek(self._keyframe_frame_indices[keyframe_index])

    def preview_keyframe(self, keyframe_index: int) -> bool:
        if not self.seek_keyframe(keyframe_index):
            return False
        self._state = replace(self._state, playing=False, paused=False)
        self._publish()
        return True

    def preview_pose(self, joints: JointValues) -> bool:
        try:
            self.output.apply_frame(
                TrajectoryFrame(timestamp=0.0, joints=joints),
            )
        except Exception as error:
            self._report_output_error(error)
            return False
        self._state = replace(self._state, playing=False, paused=False, frame_index=0)
        self._publish()
        LOGGER.info("pose_preview_applied")
        return True

    def advance(self, elapsed_seconds: float) -> None:
        if not self._state.playing or self._plan is None:
            return
        self._elapsed += elapsed_seconds * self._state.speed
        index = self._state.frame_index
        while (
            index + 1 < len(self._plan.frames)
            and self._plan.frames[index + 1].timestamp <= self._elapsed
        ):
            index += 1
        if index != self._state.frame_index:
            try:
                self.output.apply_frame(self._plan.frames[index])
            except Exception as error:
                self._report_output_error(error)
                return
            self._state = replace(self._state, frame_index=index)
            self._publish()
        if index == len(self._plan.frames) - 1:
            if self._loop:
                self._elapsed = 0.0
                try:
                    self.output.apply_frame(self._plan.frames[0])
                except Exception as error:
                    self._report_output_error(error)
                    return
                self._state = replace(self._state, frame_index=0)
            else:
                self._state = replace(
                    self._state,
                    playing=False,
                    paused=False,
                )
            self._publish()
