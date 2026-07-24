from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


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
        self.export_path = root / "export.brainos-motion.json"
        self.unsaved_decision = UnsavedDecision.DISCARD
        self.errors: list[tuple[str, str]] = []

    def select_open_motion(self) -> Path | None:
        return self.open_path

    def select_save_motion(self, _suggested_name: str) -> Path | None:
        return self.save_path

    def select_export_path(self, _suggested_name: str) -> Path | None:
        return self.export_path

    def confirm_unsaved(self, _motion_name: str) -> UnsavedDecision:
        return self.unsaved_decision

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
            gestures=CompilerGestureAuthoringService(
                GestureCompiler.default()
            ),
            exports=self.exports,
            playback=NullPlaybackOutput(),
            dialogs=self.dialogs,
        )
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

    def test_gesture_playback_save_and_export_flows(self):
        self.window.gesture_widget.prompt_edit.setText(
            "wave with your left hand"
        )
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
