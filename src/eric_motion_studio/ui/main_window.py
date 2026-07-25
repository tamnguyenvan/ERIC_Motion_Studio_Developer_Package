"""Main window shell that composes focused widgets and pure controllers."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from eric_motion_studio.config import Settings
from eric_motion_studio.runtime import (
    ViewerPlaybackOutput,
    ViewerProcessManager,
    ViewerStateStore,
)
from eric_motion_studio.runtime.viewer_process import ViewerLaunchSettings
from eric_motion_studio.ui.controllers import (
    DocumentController,
    DocumentState,
    ExportController,
    GestureAuthoringController,
    PlaybackController,
    PlaybackViewState,
)
from eric_motion_studio.ui.qt_services import QtDialogService
from eric_motion_studio.ui.services import (
    ApplicationServices,
    CompilerGestureAuthoringService,
    RepositoryMotionExportService,
    RepositoryMotionStore,
    UnsavedDecision,
)
from eric_motion_studio.ui.widgets import (
    GestureLibraryWidget,
    JointEditorWidget,
    KeyframeEditorWidget,
    MotionMetadataWidget,
    PlaybackControlsWidget,
    StatusPanel,
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "untitled-eric-motion"


def default_services(
    parent: QWidget,
    settings: Settings,
) -> ApplicationServices:
    state_store = ViewerStateStore(settings.runtime_state_path)
    viewer_process = ViewerProcessManager(
        ViewerLaunchSettings(
            model_path=settings.model_path,
            state_path=settings.runtime_state_path,
        )
    )
    return ApplicationServices(
        motions=RepositoryMotionStore(),
        gestures=CompilerGestureAuthoringService(),
        exports=RepositoryMotionExportService(),
        playback=ViewerPlaybackOutput(state_store, viewer_process),
        dialogs=QtDialogService(parent, settings),
    )


class MotionStudioWindow(QMainWindow):
    def __init__(
        self,
        settings: Settings,
        services: ApplicationServices | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.services = services or default_services(self, settings)
        self.documents = DocumentController(self.services.motions)
        self.gesture_authoring = GestureAuthoringController(
            self.services.gestures,
            self.documents,
        )
        self.exports = ExportController(self.services.exports, self.documents)
        self.playback = PlaybackController(self.services.playback)
        self._rendered_motion = None

        self.setObjectName("motionStudioMainWindow")
        self.setWindowTitle("ERIC Motion Studio")
        self.resize(1280, 820)

        definitions = getattr(
            getattr(self.services.gestures, "compiler", None),
            "registry",
            None,
        )
        definition_items = definitions.definitions if definitions is not None else ()
        self.metadata_widget = MotionMetadataWidget()
        self.gesture_widget = GestureLibraryWidget(definition_items)
        self.joint_widget = JointEditorWidget()
        self.keyframe_widget = KeyframeEditorWidget()
        self.playback_widget = PlaybackControlsWidget()
        self.status_panel = StatusPanel()

        tabs = QTabWidget()
        tabs.setObjectName("authoringTabs")
        tabs.addTab(self.keyframe_widget, "Keyframes")
        tabs.addTab(self.gesture_widget, "Gestures")
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("editorSplitter")
        splitter.addWidget(tabs)
        splitter.addWidget(self.joint_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.metadata_widget)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.playback_widget)
        layout.addWidget(self.status_panel)
        self.setCentralWidget(central)

        self._create_actions()
        self._connect_signals()

        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(lambda: self.playback.advance(0.033))

        self.documents.subscribe(self._render_document)
        self.documents.subscribe_status(self.status_panel.set_message)
        self.playback.subscribe(self._render_playback)
        self.playback.subscribe_status(self.status_panel.set_message)
        self.status_panel.set_message("Ready")

    def _create_actions(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        edit_menu = self.menuBar().addMenu("&Edit")
        playback_menu = self.menuBar().addMenu("&Playback")

        self.new_action = QAction("&New", self)
        self.new_action.setObjectName("newMotionAction")
        self.new_action.setShortcut(QKeySequence.New)
        self.open_action = QAction("&Open…", self)
        self.open_action.setObjectName("openMotionAction")
        self.open_action.setShortcut(QKeySequence.Open)
        self.save_action = QAction("&Save", self)
        self.save_action.setObjectName("saveMotionAction")
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_as_action = QAction("Save &As…", self)
        self.save_as_action.setObjectName("saveMotionAsAction")
        self.save_as_action.setShortcut(QKeySequence.SaveAs)
        self.export_action = QAction("&Export local BrainOS package…", self)
        self.export_action.setObjectName("exportMotionAction")
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.quit_action = QAction("&Quit", self)
        self.quit_action.setShortcut(QKeySequence.Quit)

        for action in (
            self.new_action,
            self.open_action,
            self.save_action,
            self.save_as_action,
            self.export_action,
            self.quit_action,
        ):
            file_menu.addAction(action)

        self.undo_action = QAction("&Undo", self)
        self.undo_action.setObjectName("undoAction")
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action = QAction("&Redo", self)
        self.redo_action.setObjectName("redoAction")
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.add_keyframe_action = QAction("Add &Keyframe", self)
        self.add_keyframe_action.setObjectName("addKeyframeAction")
        self.add_keyframe_action.setShortcut(QKeySequence("Ctrl+K"))
        self.duplicate_keyframe_action = QAction("&Duplicate Keyframe", self)
        self.duplicate_keyframe_action.setObjectName("duplicateKeyframeAction")
        self.duplicate_keyframe_action.setShortcut(QKeySequence("Ctrl+D"))
        self.preview_keyframe_action = QAction("Preview Selected Keyframe", self)
        self.preview_keyframe_action.setObjectName("previewKeyframeAction")
        self.preview_keyframe_action.setShortcut(QKeySequence("Ctrl+Return"))
        self.play_action = QAction("&Play", self)
        self.play_action.setObjectName("playAction")
        self.play_action.setShortcut(QKeySequence(Qt.Key_Space))

        for action in (
            self.undo_action,
            self.redo_action,
            self.add_keyframe_action,
            self.duplicate_keyframe_action,
            self.preview_keyframe_action,
            self.play_action,
        ):
            edit_menu.addAction(action)
        self.play_from_start_action = QAction("Play from &Start", self)
        self.play_from_start_action.setObjectName("playFromStartAction")
        self.play_from_selected_action = QAction("Play from &Selected Keyframe", self)
        self.play_from_selected_action.setObjectName("playFromSelectedKeyframeAction")
        playback_menu.addAction(self.play_from_start_action)
        playback_menu.addAction(self.play_from_selected_action)

    def _connect_signals(self) -> None:
        self.new_action.triggered.connect(self._new_document)
        self.open_action.triggered.connect(self._open_document)
        self.save_action.triggered.connect(self._save_document)
        self.save_as_action.triggered.connect(lambda: self._save_document(force_path=True))
        self.export_action.triggered.connect(self._export_document)
        self.quit_action.triggered.connect(self.close)
        self.undo_action.triggered.connect(self.documents.undo)
        self.redo_action.triggered.connect(self.documents.redo)
        self.add_keyframe_action.triggered.connect(self._add_keyframe)
        self.duplicate_keyframe_action.triggered.connect(self.documents.duplicate_selected)
        self.preview_keyframe_action.triggered.connect(self._preview_selected)
        self.play_action.triggered.connect(self._play)
        self.play_from_start_action.triggered.connect(self._play_from_start)
        self.play_from_selected_action.triggered.connect(self._play_from_selected)

        self.metadata_widget.metadataChanged.connect(
            lambda name, description, loop: self.documents.set_metadata(
                name=name,
                description=description,
                loop=loop,
            )
        )
        self.keyframe_widget.selectionChanged.connect(self.documents.select_keyframe)
        self.keyframe_widget.addRequested.connect(self._add_keyframe)
        self.keyframe_widget.captureRequested.connect(
            lambda: self.documents.capture_selected(self.joint_widget.current_joints())
        )
        self.keyframe_widget.renameRequested.connect(self._rename_keyframe)
        self.keyframe_widget.duplicateRequested.connect(self.documents.duplicate_selected)
        self.keyframe_widget.previewRequested.connect(self._preview_selected)
        self.keyframe_widget.deleteRequested.connect(self.documents.delete_selected)
        self.keyframe_widget.moveRequested.connect(self.documents.move_selected)
        self.keyframe_widget.durationChanged.connect(self.documents.set_keyframe_duration)
        self.joint_widget.jointsChanged.connect(
            lambda _joints: self.status_panel.set_message("Pose preview updated")
        )
        self.gesture_widget.compileRequested.connect(self.gesture_authoring.compile_and_apply)
        self.gesture_widget.gestureSelected.connect(self._select_gesture)

        self.playback_widget.playRequested.connect(self._play)
        self.playback_widget.playFromStartRequested.connect(self._play_from_start)
        self.playback_widget.playFromSelectedRequested.connect(self._play_from_selected)
        self.playback_widget.pauseRequested.connect(self._pause)
        self.playback_widget.stopRequested.connect(self._stop)
        self.playback_widget.speedChanged.connect(self.playback.set_speed)
        self.playback_widget.seekRequested.connect(self.playback.seek)

    def _render_document(self, state: DocumentState) -> None:
        motion_changed = state.motion is not self._rendered_motion
        self._rendered_motion = state.motion
        self.metadata_widget.set_motion(state.motion)
        self.keyframe_widget.set_motion(
            state.motion,
            state.selected_keyframe,
        )
        selected = state.motion.keyframes[state.selected_keyframe]
        self.joint_widget.set_joints(selected.joints)
        self.status_panel.set_dirty(state.dirty)
        self.undo_action.setEnabled(state.undo_depth > 0)
        self.redo_action.setEnabled(state.redo_depth > 0)
        marker = " *" if state.dirty else ""
        self.setWindowTitle(f"{state.motion.name}{marker} — ERIC Motion Studio")
        if motion_changed:
            self.playback.set_motion(state.motion)

    def _render_playback(self, state: PlaybackViewState) -> None:
        self.playback_widget.set_state(state)
        if state.playing and not self.timer.isActive():
            self.timer.start()
        elif not state.playing and self.timer.isActive():
            self.timer.stop()

    def _select_gesture(self, canonical_id: str) -> None:
        try:
            definition = self.services.gestures.compiler.registry.get(canonical_id)
        except (AttributeError, KeyError):
            return
        self.gesture_widget.prompt_edit.setText(definition.aliases[0])
        self.status_panel.set_message(f"Gesture selected: {canonical_id}")

    def _ensure_safe_to_replace(self) -> bool:
        state = self.documents.state
        if not state.dirty:
            return True
        decision = self.services.dialogs.confirm_unsaved(state.motion.name)
        save_path = state.path
        if decision is UnsavedDecision.SAVE and save_path is None:
            save_path = self.services.dialogs.select_save_motion(_slugify(state.motion.name))
            if save_path is None:
                return False
        return self.documents.resolve_unsaved(decision, save_path)

    def _new_document(self) -> None:
        if self._ensure_safe_to_replace():
            self.documents.new_document()

    def _open_document(self) -> None:
        if not self._ensure_safe_to_replace():
            return
        path = self.services.dialogs.select_open_motion()
        if path is not None:
            self.documents.open_document(path)

    def _save_document(self, force_path: bool = False) -> bool:
        path: Path | None = None if force_path else self.documents.state.path
        if path is None:
            path = self.services.dialogs.select_save_motion(
                _slugify(self.documents.state.motion.name)
            )
        return path is not None and self.documents.save(path)

    def _export_document(self) -> None:
        path = self.services.dialogs.select_export_path(_slugify(self.documents.state.motion.name))
        if path is not None:
            self.exports.export(path)

    def _add_keyframe(self) -> None:
        self.documents.add_keyframe(self.joint_widget.current_joints())

    def _rename_keyframe(self, index: int, name: str) -> None:
        if index != self.documents.state.selected_keyframe:
            self.documents.select_keyframe(index)
        self.documents.rename_selected(name)

    def _preview_selected(self) -> None:
        index = self.documents.state.selected_keyframe
        if self.playback.preview_keyframe(index):
            self.status_panel.set_message("Selected keyframe applied to preview")

    def _play(self) -> None:
        if self.playback.play():
            self.status_panel.set_message("Playback started")

    def _play_from_start(self) -> None:
        if self.playback.play_from_start():
            self.status_panel.set_message("Playback started from beginning")

    def _play_from_selected(self) -> None:
        index = self.documents.state.selected_keyframe
        if self.playback.play_from_keyframe(index):
            self.status_panel.set_message("Playback started from selected keyframe")

    def _pause(self) -> None:
        self.playback.pause()
        self.status_panel.set_message("Playback paused")

    def _stop(self) -> None:
        if self.playback.stop():
            self.status_panel.set_message("Playback stopped")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._ensure_safe_to_replace():
            try:
                self.services.playback.close()
            except Exception as error:
                self.status_panel.set_message(f"Viewer shutdown failed: {error}")
            event.accept()
        else:
            event.ignore()
