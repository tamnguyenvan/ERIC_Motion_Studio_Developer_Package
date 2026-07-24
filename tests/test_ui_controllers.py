from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from eric_motion_studio.domain import JointValues, Keyframe, Motion
from eric_motion_studio.ui.controllers import (
    DocumentController,
    ExportController,
    GestureAuthoringController,
    PlaybackController,
)
from eric_motion_studio.ui.services import UnsavedDecision


class FakeMotionStore:
    def __init__(self) -> None:
        self.files: dict[Path, Motion] = {}
        self.saved: list[tuple[Path, Motion]] = []

    def load(self, path: Path) -> Motion:
        return self.files[path]

    def save(self, path: Path, motion: Motion) -> None:
        self.files[path] = motion
        self.saved.append((path, motion))


class FakeGestureService:
    def __init__(self, motion: Motion) -> None:
        self.motion = motion
        self.prompts: list[str] = []

    def compile(self, prompt: str):
        self.prompts.append(prompt)
        return SimpleNamespace(
            succeeded=True,
            motion=self.motion,
            error="",
            resolution=SimpleNamespace(message=""),
        )


class FakeExportService:
    def __init__(self) -> None:
        self.exports: list[tuple[Path, Motion]] = []

    def export(self, path: Path, motion: Motion) -> None:
        self.exports.append((path, motion))


class FakePlaybackOutput:
    def __init__(self) -> None:
        self.frames = []
        self.reset_count = 0

    def apply_frame(self, frame) -> None:
        self.frames.append(frame)

    def reset(self) -> None:
        self.reset_count += 1


def two_frame_motion(
    name: str = "Generated",
    *,
    loop: bool = False,
) -> Motion:
    return Motion(
        name=name,
        keyframes=(
            Keyframe("Neutral", 100, JointValues.neutral()),
            Keyframe(
                "Raised",
                300,
                JointValues.from_mapping({"right_shoulder_pitch_joint": -0.5}),
            ),
        ),
        loop=loop,
        created_at="1970-01-01T00:00:00+00:00",
        updated_at="1970-01-01T00:00:00+00:00",
    )


class DocumentControllerTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeMotionStore()
        self.controller = DocumentController(self.store)
        self.statuses: list[str] = []
        self.states = []
        self.controller.subscribe(self.states.append)
        self.controller.subscribe_status(self.statuses.append)

    def test_document_lifecycle_selection_and_undo_redo(self):
        self.controller.set_metadata(
            name="Edited",
            description="Description",
            loop=True,
        )
        self.assertTrue(self.controller.state.dirty)
        self.assertEqual(self.controller.state.motion.name, "Edited")

        raised = JointValues.from_mapping({"right_shoulder_pitch_joint": -0.5})
        self.controller.add_keyframe(raised)
        self.assertEqual(len(self.controller.state.motion.keyframes), 2)
        self.assertEqual(self.controller.state.selected_keyframe, 1)

        self.controller.move_selected(-1)
        self.assertEqual(self.controller.state.selected_keyframe, 0)
        self.assertEqual(
            self.controller.state.motion.keyframes[0].joints,
            raised,
        )

        self.controller.undo()
        self.assertEqual(self.controller.state.selected_keyframe, 0)
        self.controller.redo()
        self.assertEqual(
            self.controller.state.motion.keyframes[0].joints,
            raised,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edited.json"
            self.assertTrue(self.controller.save(path))
            self.assertFalse(self.controller.state.dirty)
            self.assertEqual(self.store.saved[-1][0], path)

            replacement = two_frame_motion("Opened")
            self.store.files[path] = replacement
            self.assertTrue(self.controller.open_document(path))
            self.assertEqual(self.controller.state.motion, replacement)
            self.assertEqual(self.controller.state.undo_depth, 0)

    def test_unsaved_change_decisions(self):
        self.controller.set_metadata(name="Dirty", description="", loop=False)
        self.assertFalse(self.controller.resolve_unsaved(UnsavedDecision.CANCEL))
        self.assertTrue(self.controller.resolve_unsaved(UnsavedDecision.DISCARD))
        self.assertFalse(self.controller.resolve_unsaved(UnsavedDecision.SAVE))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved.json"
            self.assertTrue(
                self.controller.resolve_unsaved(
                    UnsavedDecision.SAVE,
                    path,
                )
            )
            self.assertFalse(self.controller.state.dirty)

    def test_undo_and_redo_compare_against_saved_revision(self):
        self.controller.set_metadata(
            name="Edited",
            description="",
            loop=False,
        )
        self.controller.undo()
        self.assertFalse(self.controller.state.dirty)
        self.controller.redo()
        self.assertTrue(self.controller.state.dirty)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved.json"
            self.assertTrue(self.controller.save(path))
            self.controller.set_metadata(
                name="Edited again",
                description="",
                loop=False,
            )
            self.controller.undo()
            self.assertFalse(self.controller.state.dirty)
            self.controller.redo()
            self.assertTrue(self.controller.state.dirty)

    def test_gesture_authoring_and_export_are_injected(self):
        generated = two_frame_motion()
        gestures = FakeGestureService(generated)
        authoring = GestureAuthoringController(gestures, self.controller)
        exports = FakeExportService()
        exporter = ExportController(exports, self.controller)

        self.assertTrue(authoring.compile_and_apply("wave"))
        self.assertEqual(gestures.prompts, ["wave"])
        self.assertEqual(self.controller.state.motion, generated)
        self.assertIn("Gesture compiled", self.statuses[-1])

        path = Path("/tmp/generated.brainos-motion.json")
        self.assertTrue(exporter.export(path))
        self.assertEqual(exports.exports, [(path, generated)])
        self.assertIn("BrainOS local export created", self.statuses[-1])


class PlaybackControllerTests(unittest.TestCase):
    def test_play_pause_seek_stop_and_completion(self):
        output = FakePlaybackOutput()
        controller = PlaybackController(output)
        states = []
        controller.subscribe(states.append)
        controller.set_motion(two_frame_motion())

        controller.play()
        self.assertTrue(controller.state.playing)
        self.assertEqual(output.frames[-1].timestamp, 0.0)
        controller.advance(0.2)
        self.assertGreater(controller.state.frame_index, 0)
        controller.pause()
        self.assertTrue(controller.state.paused)
        controller.set_speed(2.0)
        controller.play()
        controller.advance(1.0)
        self.assertFalse(controller.state.playing)
        self.assertEqual(
            controller.state.frame_index,
            controller.state.frame_count - 1,
        )
        self.assertTrue(output.frames)

        controller.stop()
        self.assertEqual(controller.state.frame_index, 0)
        self.assertEqual(output.reset_count, 1)
        with self.assertRaises(ValueError):
            controller.set_speed(3.0)

    def test_looping_restarts_at_the_initial_frame(self):
        output = FakePlaybackOutput()
        controller = PlaybackController(output)
        controller.set_motion(two_frame_motion(loop=True))

        controller.play()
        controller.advance(1.0)

        self.assertTrue(controller.state.playing)
        self.assertEqual(controller.state.frame_index, 0)
        self.assertEqual(output.frames[-1].timestamp, 0.0)


if __name__ == "__main__":
    unittest.main()
