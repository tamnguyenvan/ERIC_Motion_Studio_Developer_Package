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
from eric_motion_studio.domain import JointValues, Pose
from eric_motion_studio.gestures import GestureCompiler
from eric_motion_studio.gestures.normalization import normalize_text
from eric_motion_studio.infrastructure import (
    MotionLibrary,
    MotionOrigin,
    PoseLibrary,
    migrate_legacy_user_files,
)
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
    RepositoryPoseStore,
    UnsavedDecision,
)
from eric_motion_studio.ui.widgets import (
    GestureLibraryWidget,
    JointEditorWidget,
    KeyframeEditorWidget,
    MotionMetadataWidget,
    PlaybackControlsWidget,
    PoseLibraryWidget,
    StatusPanel,
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "untitled-eric-motion"


def default_services(
    parent: QWidget,
    settings: Settings,
) -> ApplicationServices:
    migrate_legacy_user_files(
        settings.data_dir,
        settings.motions_dir,
        settings.poses_dir,
        settings.compiled_dir,
    )
    state_store = ViewerStateStore(settings.runtime_state_path)
    viewer_process = ViewerProcessManager(
        ViewerLaunchSettings(
            model_path=settings.model_path,
            state_path=settings.runtime_state_path,
        )
    )
    gesture_service = CompilerGestureAuthoringService()
    return ApplicationServices(
        motions=RepositoryMotionStore(),
        gestures=gesture_service,
        exports=RepositoryMotionExportService(),
        playback=ViewerPlaybackOutput(state_store, viewer_process),
        dialogs=QtDialogService(parent, settings),
        poses=RepositoryPoseStore(),
        library=MotionLibrary(
            settings.motions_dir,
            gesture_service.compiler,
        ),
        pose_library=PoseLibrary(
            settings.poses_dir,
            settings.resource_root / "pose_definitions" / "builtins.json",
            settings.resource_root / "gesture_stages" / "builtin_stages.json",
        ),
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
        self.pose_store = self.services.poses or RepositoryPoseStore()
        compiler = getattr(self.services.gestures, "compiler", None) or GestureCompiler.default(
            settings.resource_root
        )
        self.library = self.services.library or MotionLibrary(
            settings.motions_dir,
            compiler,
        )
        self.pose_library = self.services.pose_library or PoseLibrary(
            settings.poses_dir,
            settings.resource_root / "pose_definitions" / "builtins.json",
            settings.resource_root / "gesture_stages" / "builtin_stages.json",
        )
        self.documents = DocumentController(self.services.motions)
        self.gesture_authoring = GestureAuthoringController(
            self.services.gestures,
            self.documents,
        )
        self.exports = ExportController(self.services.exports, self.documents)
        self.playback = PlaybackController(self.services.playback)
        self._rendered_motion = None
        self._active_library_entry_id: str | None = None
        self._active_pose_entry_id: str | None = None

        self.setObjectName("motionStudioMainWindow")
        self.setWindowTitle("ERIC Motion Studio")
        self.resize(1280, 820)

        self.metadata_widget = MotionMetadataWidget()
        self.gesture_widget = GestureLibraryWidget()
        self.gesture_widget.set_entries(self.library.entries())
        self.pose_widget = PoseLibraryWidget()
        self.pose_widget.set_results(self.pose_library.entries())
        self.joint_widget = JointEditorWidget()
        self.keyframe_widget = KeyframeEditorWidget()
        self.playback_widget = PlaybackControlsWidget()
        self.status_panel = StatusPanel()

        tabs = QTabWidget()
        tabs.setObjectName("authoringTabs")
        tabs.addTab(self.keyframe_widget, "Keyframes")
        tabs.addTab(self.gesture_widget, "Gestures")
        tabs.addTab(self.pose_widget, "Poses")
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
        self._start_viewer_on_startup()

    def _start_viewer_on_startup(self) -> None:
        start = getattr(self.services.playback, "start", None)
        if start is None:
            return
        try:
            start()
        except Exception as error:
            self.status_panel.set_message(f"Viewer startup failed: {error}")
            return
        self.status_panel.set_message("Viewer started")

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
        self.import_pose_action = QAction("&Import Pose…", self)
        self.import_pose_action.setObjectName("importPoseAction")
        self.export_pose_action = QAction("Export Current &Pose…", self)
        self.export_pose_action.setObjectName("exportPoseAction")
        self.quit_action = QAction("&Quit", self)
        self.quit_action.setShortcut(QKeySequence.Quit)

        for action in (
            self.new_action,
            self.open_action,
            self.save_action,
            self.save_as_action,
            self.export_action,
            self.import_pose_action,
            self.export_pose_action,
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
        self.import_pose_action.triggered.connect(self._load_pose)
        self.export_pose_action.triggered.connect(
            lambda: self._save_pose(self.joint_widget.current_joints())
        )
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
        self.keyframe_widget.selectionChanged.connect(self._select_keyframe)
        self.keyframe_widget.addRequested.connect(self._add_keyframe)
        self.keyframe_widget.captureRequested.connect(
            lambda: self.documents.capture_selected(self.joint_widget.current_joints())
        )
        self.keyframe_widget.renameRequested.connect(self._rename_keyframe)
        self.keyframe_widget.duplicateRequested.connect(self.documents.duplicate_selected)
        self.keyframe_widget.previewRequested.connect(self._preview_selected)
        self.keyframe_widget.presetRequested.connect(self.documents.apply_preset)
        self.keyframe_widget.deleteRequested.connect(self.documents.delete_selected)
        self.keyframe_widget.moveRequested.connect(self.documents.move_selected)
        self.keyframe_widget.durationChanged.connect(self.documents.set_keyframe_duration)
        self.joint_widget.jointsChanged.connect(
            lambda _joints: self.status_panel.set_message("Pose preview updated")
        )
        self.joint_widget.returnPreviewNeutralRequested.connect(self._return_preview_to_neutral)
        self.joint_widget.addNeutralKeyframeRequested.connect(self.documents.add_neutral_keyframe)
        self.gesture_widget.commandRequested.connect(self._activate_gesture_command)
        self.gesture_widget.activationRequested.connect(self._activate_library_motion)
        self.gesture_widget.duplicateRequested.connect(self._duplicate_library_motion)
        self.gesture_widget.deleteRequested.connect(self._delete_library_motion)
        self.gesture_widget.commandsSaveRequested.connect(self._save_custom_commands)
        self.gesture_widget.refreshRequested.connect(self._refresh_library)
        self.pose_widget.searchRequested.connect(self._search_poses)
        self.pose_widget.previewRequested.connect(self._preview_library_pose)
        self.pose_widget.addAsKeyframeRequested.connect(self._append_pose_keyframe)
        self.pose_widget.createRequested.connect(self._create_library_pose)
        self.pose_widget.updateRequested.connect(self._update_library_pose)
        self.pose_widget.duplicateRequested.connect(self._duplicate_library_pose)
        self.pose_widget.renameRequested.connect(self._rename_library_pose)
        self.pose_widget.deleteRequested.connect(self._delete_library_pose)
        self.pose_widget.refreshRequested.connect(self._refresh_pose_library)

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
        self.metadata_widget.set_editable(state.editable)
        self.metadata_widget.set_motion(state.motion)
        self.keyframe_widget.set_editable(state.editable)
        self.keyframe_widget.set_motion(
            state.motion,
            state.selected_keyframe,
        )
        self.joint_widget.set_motion_editable(state.editable)
        self.joint_widget.set_editor_active(True, "keyframe")
        self.pose_widget.set_motion_editable(state.editable)
        selected = state.motion.keyframes[state.selected_keyframe]
        self.joint_widget.set_joints(selected.joints)
        self.status_panel.set_dirty(state.dirty)
        self.save_action.setEnabled(state.editable)
        self.save_as_action.setEnabled(state.editable)
        self.undo_action.setEnabled(state.editable and state.undo_depth > 0)
        self.redo_action.setEnabled(state.editable and state.redo_depth > 0)
        self.add_keyframe_action.setEnabled(state.editable)
        self.duplicate_keyframe_action.setEnabled(state.editable)
        marker = " *" if state.dirty else ""
        mode = "" if state.editable else " [Built-in · Read-only]"
        self.setWindowTitle(f"{state.motion.name}{marker}{mode} — ERIC Motion Studio")
        if motion_changed:
            self.playback.set_motion(state.motion)

    def _render_playback(self, state: PlaybackViewState) -> None:
        self.playback_widget.set_state(state)
        if state.playing and not self.timer.isActive():
            self.timer.start()
        elif not state.playing and self.timer.isActive():
            self.timer.stop()

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
        resolved = self.documents.resolve_unsaved(decision, save_path)
        if resolved and decision is UnsavedDecision.SAVE:
            self._refresh_library()
        return resolved

    def _restore_active_library_selection(self) -> None:
        if self._active_library_entry_id is None:
            self.gesture_widget.clear_selection()
        else:
            self.gesture_widget.select_entry(self._active_library_entry_id)

    def _prepare_motion_switch(self) -> bool:
        if not self._ensure_safe_to_replace():
            self._restore_active_library_selection()
            return False
        if self.playback.state.playing or self.playback.state.paused:
            self.playback.stop()
        return True

    def _new_document(self) -> None:
        if not self._prepare_motion_switch():
            return
        self.documents.new_document()
        try:
            motion, path = self.library.create(self.documents.state.motion)
        except Exception as error:
            self.services.dialogs.show_error("Create motion failed", str(error))
            return
        self.documents.load_library_motion(
            motion,
            path=path,
            editable=True,
        )
        self._active_library_entry_id = f"user:{path.name}"
        self._refresh_library()
        self.playback.preview_keyframe(0)
        self.status_panel.set_message(f"Custom motion created: {path.name}")

    def _open_document(self) -> None:
        if not self._prepare_motion_switch():
            return
        path = self.services.dialogs.select_open_motion()
        if path is not None and self.documents.open_document(path):
            self._active_library_entry_id = None
            self.gesture_widget.clear_selection()
            self.playback.preview_keyframe(0)

    def _save_document(self, force_path: bool = False) -> bool:
        path: Path | None = None if force_path else self.documents.state.path
        if path is None:
            path = self.services.dialogs.select_save_motion(
                _slugify(self.documents.state.motion.name)
            )
        saved = path is not None and self.documents.save(path)
        if saved:
            self._refresh_library()
        return saved

    def _refresh_library(self) -> None:
        self.gesture_widget.set_entries(self.library.entries())
        self._restore_active_library_selection()

    def _activate_library_motion(self, entry_id: str) -> None:
        if entry_id == self._active_library_entry_id:
            return
        entry = next(
            (item for item in self.library.entries() if item.entry_id == entry_id),
            None,
        )
        if entry is None:
            self._restore_active_library_selection()
            return
        if not self._prepare_motion_switch():
            return
        try:
            motion, path = self.library.load(entry_id)
        except Exception as error:
            self.services.dialogs.show_error("Activate motion failed", str(error))
            self._restore_active_library_selection()
            return
        self.documents.load_library_motion(
            motion,
            path=path,
            editable=entry.editable,
        )
        self._active_library_entry_id = entry_id
        self.gesture_widget.select_entry(entry_id)
        self.playback.preview_keyframe(0)

    def _activate_gesture_command(self, prompt: str) -> None:
        if not prompt.strip():
            self.gesture_authoring.activate_command(prompt)
            return
        if not self._prepare_motion_switch():
            return
        normalized = normalize_text(prompt)
        custom = next(
            (
                entry
                for entry in self.library.entries()
                if entry.origin is MotionOrigin.USER
                and normalized
                in {normalize_text(command) for command in (entry.command, *entry.aliases)}
            ),
            None,
        )
        if custom is not None:
            self._activate_library_motion(custom.entry_id)
            return
        if not self.gesture_authoring.activate_command(prompt):
            self._restore_active_library_selection()
            return
        self._active_library_entry_id = None
        self.gesture_widget.clear_selection()
        self.playback.preview_keyframe(0)

    def _save_custom_commands(self, entry_id: str, raw_commands: str) -> None:
        entry = next((item for item in self.library.entries() if item.entry_id == entry_id), None)
        if entry is None or entry.origin is not MotionOrigin.USER:
            return
        commands = tuple(
            dict.fromkeys(
                normalize_text(value) for value in raw_commands.split(",") if normalize_text(value)
            )
        )
        builtin_commands = {
            normalize_text(command)
            for definition in self.gesture_authoring.service.compiler.registry.definitions
            for command in (*definition.aliases, *definition.triggers)
        }
        other_custom = {
            normalize_text(command)
            for item in self.library.entries()
            if item.entry_id != entry_id and item.origin is MotionOrigin.USER
            for command in (item.command, *item.aliases)
        }
        collisions = sorted(set(commands) & (builtin_commands | other_custom))
        if collisions:
            self.services.dialogs.show_error(
                "Save commands failed",
                f"Command already in use: {', '.join(collisions)}",
            )
            return
        try:
            self.library.update_commands(entry_id, commands)
        except Exception as error:
            self.services.dialogs.show_error("Save commands failed", str(error))
            return
        self._refresh_library()
        self.gesture_widget.select_entry(entry_id)
        self.status_panel.set_message("Custom gesture commands saved")

    def _duplicate_library_motion(self, entry_id: str) -> None:
        if not self._prepare_motion_switch():
            return
        try:
            motion, path = self.library.duplicate(entry_id)
        except Exception as error:
            self.services.dialogs.show_error("Duplicate motion failed", str(error))
            return
        self.documents.load_library_motion(
            motion,
            path=path,
            editable=True,
        )
        self._active_library_entry_id = f"user:{path.name}"
        self._refresh_library()
        self.playback.preview_keyframe(0)
        self.status_panel.set_message(f"Custom motion created: {path.name}")

    def _delete_library_motion(self, entry_id: str) -> None:
        entry = next(
            (item for item in self.library.entries() if item.entry_id == entry_id),
            None,
        )
        if entry is None or not self.services.dialogs.confirm_delete_motion(entry.display_name):
            return
        try:
            deleted = self.library.delete(entry_id)
        except Exception as error:
            self.services.dialogs.show_error("Delete motion failed", str(error))
            return
        if self.documents.state.path == deleted:
            self.documents.new_document()
            self._active_library_entry_id = None
        self._refresh_library()
        self.status_panel.set_message(f"Motion deleted: {deleted.name}")

    def _export_document(self) -> None:
        path = self.services.dialogs.select_export_path(_slugify(self.documents.state.motion.name))
        if path is not None:
            self.exports.export(path)

    def _add_keyframe(self) -> None:
        self.documents.add_keyframe(self.joint_widget.current_joints())

    def _select_keyframe(self, index: int) -> None:
        if index < 0:
            self.joint_widget.set_editor_active(False)
            return
        self.documents.select_keyframe(index)
        self.joint_widget.set_editor_active(True, "keyframe")

    def _return_preview_to_neutral(self) -> None:
        if self.playback.preview_pose(JointValues.neutral(self.joint_widget.profile)):
            self.status_panel.set_message("Preview returned to neutral")

    def _search_poses(self, query: str) -> None:
        self.pose_widget.set_results(self.pose_library.search(query))

    def _refresh_pose_library(self) -> None:
        self.pose_widget.set_results(self.pose_library.search(self.pose_widget.query))
        if self._active_pose_entry_id is not None:
            self.pose_widget.select_entry(self._active_pose_entry_id)

    def _preview_library_pose(self, entry_id: str) -> None:
        try:
            pose, _path = self.pose_library.load(entry_id)
        except Exception as error:
            self.services.dialogs.show_error("Preview pose failed", str(error))
            return
        if self.playback.state.playing or self.playback.state.paused:
            self.playback.stop()
        self.joint_widget.set_joints(pose.joints, respect_locks=True)
        self.joint_widget.set_editor_active(True, "pose preview")
        if not self.playback.preview_pose(self.joint_widget.current_joints()):
            return
        self._active_pose_entry_id = entry_id
        self.pose_widget.select_entry(entry_id)
        metadata = dict(pose.metadata)
        name = str(metadata.get("pose_name") or "Pose")
        self.status_panel.set_message(f"Pose applied to preview: {name}")

    def _append_pose_keyframe(self, entry_id: str) -> None:
        if not self.documents.state.editable:
            self.status_panel.set_message(
                "Duplicate the current built-in gesture before adding a pose keyframe"
            )
            return
        try:
            pose, _path = self.pose_library.load(entry_id)
        except Exception as error:
            self.services.dialogs.show_error("Add pose keyframe failed", str(error))
            return
        if self.playback.state.playing or self.playback.state.paused:
            self.playback.stop()
        self.joint_widget.set_joints(pose.joints, respect_locks=True)
        metadata = dict(pose.metadata)
        name = str(metadata.get("pose_name") or "Pose")
        self.documents.add_keyframe(self.joint_widget.current_joints(), name=name)
        self.status_panel.set_message(f"Pose keyframe added: {name}")

    def _create_library_pose(self, name: str) -> None:
        try:
            _pose, path = self.pose_library.create(
                self.joint_widget.current_joints(),
                name,
            )
        except Exception as error:
            self.services.dialogs.show_error("Save custom pose failed", str(error))
            return
        self._active_pose_entry_id = f"user:{path.name}"
        self.pose_widget.search_edit.clear()
        self._refresh_pose_library()
        self.status_panel.set_message(f"Custom pose saved: {path.name}")

    def _update_library_pose(self, entry_id: str) -> None:
        try:
            _pose, path = self.pose_library.update(
                entry_id,
                self.joint_widget.current_joints(),
            )
        except Exception as error:
            self.services.dialogs.show_error("Update custom pose failed", str(error))
            return
        self._active_pose_entry_id = entry_id
        self._refresh_pose_library()
        self.status_panel.set_message(f"Custom pose updated: {path.name}")

    def _duplicate_library_pose(self, entry_id: str) -> None:
        try:
            _pose, path = self.pose_library.duplicate(entry_id)
        except Exception as error:
            self.services.dialogs.show_error("Duplicate pose failed", str(error))
            return
        self._active_pose_entry_id = f"user:{path.name}"
        self.pose_widget.search_edit.clear()
        self._refresh_pose_library()
        self._preview_library_pose(self._active_pose_entry_id)

    def _rename_library_pose(self, entry_id: str, name: str) -> None:
        try:
            _pose, path = self.pose_library.rename(entry_id, name)
        except Exception as error:
            self.services.dialogs.show_error("Rename pose failed", str(error))
            return
        self._active_pose_entry_id = entry_id
        self._refresh_pose_library()
        self.status_panel.set_message(f"Custom pose renamed: {path.name}")

    def _delete_library_pose(self, entry_id: str) -> None:
        entry = next(
            (item for item in self.pose_library.entries() if item.entry_id == entry_id),
            None,
        )
        if entry is None or not self.services.dialogs.confirm_delete_pose(entry.display_name):
            return
        try:
            deleted = self.pose_library.delete(entry_id)
        except Exception as error:
            self.services.dialogs.show_error("Delete pose failed", str(error))
            return
        if self._active_pose_entry_id == entry_id:
            self._active_pose_entry_id = None
        self._refresh_pose_library()
        self.status_panel.set_message(f"Custom pose deleted: {deleted.name}")

    def _save_pose(self, joints: JointValues) -> None:
        path = self.services.dialogs.select_save_pose("pose")
        if path is None:
            return
        try:
            self.pose_store.save(path, Pose(joints=joints))
        except Exception as error:
            self.services.dialogs.show_error("Save pose failed", str(error))
            return
        self.status_panel.set_message(f"Pose saved: {path.name}")

    def _load_pose(self) -> None:
        path = self.services.dialogs.select_open_pose()
        if path is None:
            return
        try:
            pose = self.pose_store.load(path)
            self.joint_widget.set_joints(pose.joints, respect_locks=True)
        except Exception as error:
            self.services.dialogs.show_error("Load pose failed", str(error))
            return
        self._active_pose_entry_id = None
        self.pose_widget.clear_selection()
        self.joint_widget.jointsChanged.emit(self.joint_widget.current_joints())
        self.status_panel.set_message(f"Pose loaded: {path.name}")

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
