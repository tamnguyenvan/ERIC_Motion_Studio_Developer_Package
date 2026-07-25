from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# ruff: noqa: E402
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from eric_motion_studio.config import Settings
from eric_motion_studio.gestures import GestureCompiler
from eric_motion_studio.ui.main_window import MotionStudioWindow
from eric_motion_studio.ui.services import (
    ApplicationServices,
    CompilerGestureAuthoringService,
    NullPlaybackOutput,
    UnsavedDecision,
)
from test_ui_controllers import FakeExportService, FakeMotionStore


class FakeDialogs:
    def __init__(self, root: Path) -> None:
        self.open_path: Path | None = None
        self.save_path = root / "saved.json"
        self.pose_path = root / "pose.json"
        self.pose_open_path: Path | None = None
        self.export_path = root / "export.brainos-motion.json"
        self.unsaved_decision = UnsavedDecision.DISCARD
        self.errors: list[tuple[str, str]] = []

    def select_open_motion(self) -> Path | None:
        return self.open_path

    def select_save_motion(self, _suggested_name: str) -> Path | None:
        return self.save_path

    def select_export_path(self, _suggested_name: str) -> Path | None:
        return self.export_path

    def select_open_pose(self) -> Path | None:
        return self.pose_open_path

    def select_save_pose(self, _suggested_name: str) -> Path | None:
        return self.pose_path

    def confirm_unsaved(self, _motion_name: str) -> UnsavedDecision:
        return self.unsaved_decision

    def confirm_delete_motion(self, _motion_name: str) -> bool:
        return True

    def show_error(self, title: str, message: str) -> None:
        self.errors.append((title, message))


class QtCriticalFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        settings = Settings.load(
            environment={
                "HOME": str(self.root),
                "XDG_DATA_HOME": str(self.root / "data"),
                "XDG_STATE_HOME": str(self.root / "state"),
                "XDG_RUNTIME_DIR": str(self.root / "run"),
            }
        )
        self.store = FakeMotionStore()
        self.exports = FakeExportService()
        self.dialogs = FakeDialogs(self.root)
        services = ApplicationServices(
            motions=self.store,
            gestures=CompilerGestureAuthoringService(GestureCompiler.default()),
            exports=self.exports,
            playback=NullPlaybackOutput(),
            dialogs=self.dialogs,
        )
        self.services = services
        self.window = MotionStudioWindow(settings, services)
        self.window.show()
        self.application.processEvents()

    def tearDown(self):
        self.dialogs.unsaved_decision = UnsavedDecision.DISCARD
        self.window.close()
        self.application.processEvents()
        self.temporary.cleanup()

    def test_metadata_keyframe_selection_shortcut_and_status(self):
        self.window.metadata_widget.name_edit.setText("Qt Edited")
        self.window.metadata_widget.name_edit.editingFinished.emit()
        self.application.processEvents()

        self.assertEqual(
            self.window.documents.state.motion.name,
            "Qt Edited",
        )
        self.assertTrue(self.window.documents.state.dirty)
        self.assertEqual(
            self.window.status_panel.dirty_label.text(),
            "Unsaved changes",
        )
        self.assertIn("*", self.window.windowTitle())

        QTest.mouseClick(
            self.window.keyframe_widget.add_button,
            Qt.LeftButton,
        )
        self.application.processEvents()
        self.assertEqual(
            self.window.keyframe_widget.keyframe_list.count(),
            2,
        )
        self.assertEqual(self.window.documents.state.selected_keyframe, 1)

        QTest.keyClick(self.window, Qt.Key_Z, Qt.ControlModifier)
        self.application.processEvents()
        self.assertEqual(
            self.window.keyframe_widget.keyframe_list.count(),
            1,
        )
        self.assertEqual(self.window.status_panel.status_label.text(), "Undo")

    def test_description_edit_commits_once_after_focus_loss(self):
        description = self.window.metadata_widget.description_edit
        description.setFocus()
        QTest.keyClicks(description, "abc")
        self.application.processEvents()

        self.assertEqual(description.toPlainText(), "abc")
        self.assertEqual(self.window.documents.state.motion.description, "")
        self.assertEqual(self.window.documents.state.undo_depth, 0)

        self.window.metadata_widget.name_edit.setFocus()
        self.application.processEvents()

        self.assertEqual(self.window.documents.state.motion.description, "abc")
        self.assertEqual(self.window.documents.state.undo_depth, 1)

    def test_joint_editor_resets_to_default_pose(self):
        spin = self.window.joint_widget.spin_boxes["right_shoulder_pitch_joint"]
        spin.setValue(-0.5)
        self.assertAlmostEqual(spin.value(), -0.5)

        QTest.mouseClick(self.window.joint_widget.reset_button, Qt.LeftButton)
        self.application.processEvents()

        self.assertEqual(spin.value(), 0.0)
        self.assertTrue(
            all(value == 0.0 for value in self.window.joint_widget.current_joints().values)
        )
        self.assertEqual(
            self.window.status_panel.status_label.text(),
            "Pose preview updated",
        )

    def test_joint_editor_resets_one_joint_with_icon_button(self):
        shoulder = self.window.joint_widget.spin_boxes["right_shoulder_pitch_joint"]
        elbow = self.window.joint_widget.spin_boxes["right_elbow_joint"]
        shoulder.setValue(-0.5)
        elbow.setValue(-0.4)

        QTest.mouseClick(
            self.window.joint_widget.reset_buttons["right_shoulder_pitch_joint"],
            Qt.LeftButton,
        )
        self.application.processEvents()

        self.assertEqual(shoulder.value(), 0.0)
        self.assertEqual(elbow.value(), -0.4)

    def test_joint_presets_locks_mirroring_and_neutral_keyframe(self):
        left = self.window.joint_widget.spin_boxes["left_shoulder_pitch_joint"]
        right = self.window.joint_widget.spin_boxes["right_shoulder_pitch_joint"]
        left.setValue(0.1)
        self.window.joint_widget.lock_checkboxes["LOCK LEFT ARM"].setChecked(True)
        self.application.processEvents()
        self.assertFalse(left.isEnabled())

        QTest.mouseClick(self.window.joint_widget.mirror_arms_button, Qt.LeftButton)
        self.assertAlmostEqual(right.value(), 0.1)

        QTest.mouseClick(self.window.joint_widget.add_neutral_button, Qt.LeftButton)
        self.application.processEvents()
        self.assertEqual(len(self.window.documents.state.motion.keyframes), 2)
        self.assertTrue(
            all(
                value == 0.0
                for value in self.window.documents.state.motion.keyframes[-1].joints.values
            )
        )

    def test_pose_copy_apply_preview_neutral_and_save_load(self):
        spin = self.window.joint_widget.spin_boxes["right_shoulder_pitch_joint"]
        spin.setValue(-0.35)
        QTest.mouseClick(self.window.joint_widget.copy_pose_button, Qt.LeftButton)
        spin.setValue(0.2)
        QTest.mouseClick(self.window.joint_widget.apply_pose_button, Qt.LeftButton)
        self.assertAlmostEqual(spin.value(), -0.35)

        QTest.mouseClick(self.window.joint_widget.save_pose_button, Qt.LeftButton)
        self.dialogs.pose_open_path = self.dialogs.pose_path
        spin.setValue(0.2)
        QTest.mouseClick(self.window.joint_widget.load_pose_button, Qt.LeftButton)
        self.application.processEvents()
        self.assertAlmostEqual(spin.value(), -0.35)

        QTest.mouseClick(
            self.window.joint_widget.return_preview_button,
            Qt.LeftButton,
        )
        self.assertEqual(
            self.services.playback.last_frame.joints.get("right_shoulder_pitch_joint"),
            0.0,
        )

    def test_builtin_motion_duplicates_to_saved_custom_editable_copy(self):
        idle = next(
            entry for entry in self.window.library.entries() if entry.canonical_id == "idle_pose"
        )

        self.window._load_library_motion(idle.entry_id)
        first_path = self.window.documents.state.path
        self.assertFalse(self.window.documents.state.dirty)
        self.assertIsNotNone(first_path)
        self.assertEqual(first_path.parent, self.window.settings.motions_dir)
        self.assertTrue(first_path.is_file())
        self.assertNotIn(
            "library_status",
            dict(self.window.documents.state.motion.metadata),
        )

        self.window.documents.rename_selected("Edited keyframe")
        self.assertTrue(self.window.documents.state.dirty)
        self.window.save_action.trigger()
        self.assertFalse(self.window.documents.state.dirty)
        self.assertEqual(self.store.saved[-1][0], first_path)

        custom = next(entry for entry in self.window.library.entries() if entry.path == first_path)
        self.window._duplicate_library_motion(custom.entry_id)
        second_path = self.window.documents.state.path
        self.assertNotEqual(first_path, second_path)
        self.assertTrue(second_path.is_file())
        self.assertFalse(any(self.window.settings.compiled_dir.glob("*.gesture.json")))
        self.assertFalse(hasattr(self.window.gesture_widget, "approve_button"))
        self.assertFalse(hasattr(self.window.gesture_widget, "save_button"))

        second = next(entry for entry in self.window.library.entries() if entry.path == second_path)
        self.window._delete_library_motion(second.entry_id)
        self.assertFalse(second_path.exists())
        self.assertIsNone(self.window.documents.state.path)

    def test_new_motion_is_added_to_custom_library_immediately(self):
        self.window._new_document()

        path = self.window.documents.state.path
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())
        self.assertFalse(self.window.documents.state.dirty)
        self.assertTrue(
            any(entry.path == path for entry in self.window.library.entries()),
        )

    def test_keyframe_rename_duplicate_preview_and_playback_actions(self):
        item = self.window.keyframe_widget.keyframe_list.item(0)
        with patch(
            "eric_motion_studio.ui.widgets.keyframe_editor.QInputDialog.getText",
            return_value=("Renamed by double click", True),
        ):
            self.window.keyframe_widget.keyframe_list.itemDoubleClicked.emit(item)
        self.application.processEvents()
        self.assertEqual(
            self.window.documents.state.motion.keyframes[0].name,
            "Renamed by double click",
        )

        self.window.keyframe_widget.renameRequested.emit(0, "Rest")
        self.application.processEvents()
        self.assertEqual(self.window.documents.state.motion.keyframes[0].name, "Rest")

        QTest.mouseClick(
            self.window.keyframe_widget.duplicate_button,
            Qt.LeftButton,
        )
        self.application.processEvents()
        self.assertEqual(self.window.keyframe_widget.keyframe_list.count(), 2)
        self.assertEqual(self.window.documents.state.selected_keyframe, 1)

        QTest.mouseClick(self.window.keyframe_widget.preview_button, Qt.LeftButton)
        self.application.processEvents()
        self.assertIsNotNone(self.services.playback.last_frame)
        self.assertIn("Selected keyframe applied", self.window.status_panel.status_label.text())

        QTest.mouseClick(self.window.playback_widget.start_button, Qt.LeftButton)
        self.application.processEvents()
        self.assertTrue(self.window.playback.state.playing)
        QTest.mouseClick(self.window.playback_widget.stop_button, Qt.LeftButton)
        self.application.processEvents()

        QTest.mouseClick(self.window.playback_widget.selected_button, Qt.LeftButton)
        self.application.processEvents()
        self.assertTrue(self.window.playback.state.playing)
        self.assertIn("selected keyframe", self.window.status_panel.status_label.text())

    def test_gesture_playback_save_and_export_flows(self):
        self.window.gesture_widget.prompt_edit.setText("wave with your left hand")
        QTest.mouseClick(
            self.window.gesture_widget.compile_button,
            Qt.LeftButton,
        )
        self.application.processEvents()

        self.assertGreater(
            len(self.window.documents.state.motion.keyframes),
            3,
        )
        self.assertIn(
            "Gesture compiled",
            self.window.status_panel.status_label.text(),
        )

        QTest.mouseClick(
            self.window.playback_widget.play_button,
            Qt.LeftButton,
        )
        self.application.processEvents()
        self.assertTrue(self.window.playback.state.playing)
        self.assertEqual(
            self.window.status_panel.status_label.text(),
            "Playback started",
        )
        QTest.mouseClick(
            self.window.playback_widget.pause_button,
            Qt.LeftButton,
        )
        self.assertTrue(self.window.playback.state.paused)

        self.window.save_action.trigger()
        self.application.processEvents()
        self.assertEqual(self.store.saved[-1][0], self.dialogs.save_path)
        self.assertFalse(self.window.documents.state.dirty)
        self.assertEqual(
            self.window.status_panel.dirty_label.text(),
            "Saved",
        )

        self.window.export_action.trigger()
        self.application.processEvents()
        self.assertEqual(
            self.exports.exports[-1][0],
            self.dialogs.export_path,
        )
        self.assertIn(
            "BrainOS local export created",
            self.window.status_panel.status_label.text(),
        )


if __name__ == "__main__":
    unittest.main()
