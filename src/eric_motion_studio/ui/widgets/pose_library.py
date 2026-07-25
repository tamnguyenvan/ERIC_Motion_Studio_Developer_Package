from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

from eric_motion_studio.infrastructure import PoseLibraryEntry, PoseOrigin


class PoseLibraryWidget(QGroupBox):
    searchRequested = Signal(str)
    previewRequested = Signal(str)
    addAsKeyframeRequested = Signal(str)
    createRequested = Signal(str)
    updateRequested = Signal(str)
    duplicateRequested = Signal(str)
    renameRequested = Signal(str, str)
    deleteRequested = Signal(str)
    refreshRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Pose library", parent)
        self.setObjectName("poseLibraryPanel")
        self._entries: dict[str, PoseLibraryEntry] = {}
        self._motion_editable = False
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("poseSearchEdit")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText("Search poses… thinking, arms open, left hand raised")
        self.custom_list = self._make_list("customPoseLibraryList")
        self.system_list = self._make_list("systemPoseLibraryList")
        self.tabs = QTabWidget()
        self.tabs.setObjectName("poseOriginTabs")
        self.tabs.addTab(self.custom_list, "Custom")
        self.tabs.addTab(self.system_list, "System (Built-in)")
        self.pose_list = self.custom_list  # compatibility alias
        self.create_button = QPushButton("SAVE CURRENT")
        self.create_button.setObjectName("createPoseLibraryButton")
        self.update_button = QPushButton("UPDATE")
        self.update_button.setObjectName("updatePoseLibraryButton")
        self.duplicate_button = QPushButton("DUPLICATE")
        self.duplicate_button.setObjectName("duplicatePoseLibraryButton")
        self.rename_button = QPushButton("RENAME")
        self.rename_button.setObjectName("renamePoseLibraryButton")
        self.delete_button = QPushButton("DELETE")
        self.delete_button.setObjectName("deletePoseLibraryButton")
        self.add_keyframe_button = QPushButton("ADD POSE AS KEYFRAME")
        self.add_keyframe_button.setObjectName("addPoseKeyframeButton")
        self.add_keyframe_button.setToolTip(
            "Append the selected pose to the current custom gesture"
        )
        self.refresh_button = QPushButton("REFRESH")
        self.refresh_button.setObjectName("refreshPoseLibraryButton")
        actions = QGridLayout()
        for index, button in enumerate(
            (
                self.create_button,
                self.update_button,
                self.duplicate_button,
                self.rename_button,
                self.delete_button,
                self.add_keyframe_button,
                self.refresh_button,
            )
        ):
            actions.addWidget(button, index // 3, index % 3)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Click a pose to apply it to the preview"))
        layout.addWidget(self.search_edit)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(actions)
        self.search_edit.textChanged.connect(self.searchRequested)
        for widget in (self.custom_list, self.system_list):
            widget.currentItemChanged.connect(self._selection_changed)
        self.tabs.currentChanged.connect(lambda _index: self._update_actions(self._current_entry()))
        self.create_button.clicked.connect(self._request_create)
        self.update_button.clicked.connect(self._request_update)
        self.duplicate_button.clicked.connect(self._request_duplicate)
        self.rename_button.clicked.connect(self._request_rename)
        self.delete_button.clicked.connect(self._request_delete)
        self.add_keyframe_button.clicked.connect(self._request_add_keyframe)
        self.refresh_button.clicked.connect(self.refreshRequested)
        self._update_actions(None)

    @staticmethod
    def _make_list(name: str) -> QListWidget:
        widget = QListWidget()
        widget.setObjectName(name)
        return widget

    @property
    def query(self) -> str:
        return self.search_edit.text()

    def set_motion_editable(self, editable: bool) -> None:
        self._motion_editable = editable
        self._update_actions(self._current_entry())

    def set_results(self, entries: tuple[PoseLibraryEntry, ...]) -> None:
        current = self.selected_entry_id()
        self._entries = {entry.entry_id: entry for entry in entries}
        for origin, widget in (
            (PoseOrigin.USER, self.custom_list),
            (PoseOrigin.BUILTIN, self.system_list),
        ):
            with QSignalBlocker(widget):
                widget.clear()
                for entry in entries:
                    if entry.origin is not origin:
                        continue
                    item = QListWidgetItem(entry.display_name)
                    item.setData(Qt.UserRole, entry.entry_id)
                    details = [entry.description] if entry.description else []
                    if entry.aliases:
                        details.append(f"Aliases: {', '.join(entry.aliases)}")
                    if entry.tags:
                        details.append(f"Tags: {', '.join(entry.tags)}")
                    item.setToolTip("\n".join(details))
                    widget.addItem(item)
        if current:
            self.select_entry(current)
        else:
            self._update_actions(None)

    def _current_list(self) -> QListWidget:
        return self.tabs.currentWidget()  # type: ignore[return-value]

    def selected_entry_id(self) -> str | None:
        item = self._current_list().currentItem()
        return str(item.data(Qt.UserRole)) if item is not None else None

    def select_entry(self, entry_id: str) -> None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return
        widget = self.custom_list if entry.origin is PoseOrigin.USER else self.system_list
        self.tabs.setCurrentWidget(widget)
        for row in range(widget.count()):
            if str(widget.item(row).data(Qt.UserRole)) == entry_id:
                with QSignalBlocker(widget):
                    widget.setCurrentRow(row)
                self._update_actions(entry)
                return

    def clear_selection(self) -> None:
        for widget in (self.custom_list, self.system_list):
            with QSignalBlocker(widget):
                widget.setCurrentRow(-1)
                widget.clearSelection()
        self._update_actions(None)

    def _current_entry(self) -> PoseLibraryEntry | None:
        return self._entries.get(self.selected_entry_id() or "")

    def _selection_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        entry = self._entries.get(str(current.data(Qt.UserRole))) if current is not None else None
        self._update_actions(entry)
        if entry is not None:
            self.previewRequested.emit(entry.entry_id)

    def _request_create(self) -> None:
        name, accepted = QInputDialog.getText(
            self, "Save custom pose", "Pose name:", QLineEdit.Normal, "My Pose"
        )
        if accepted and name.strip():
            self.createRequested.emit(name.strip())

    def _request_update(self) -> None:
        if entry_id := self.selected_entry_id():
            self.updateRequested.emit(entry_id)

    def _request_duplicate(self) -> None:
        if entry_id := self.selected_entry_id():
            self.duplicateRequested.emit(entry_id)

    def _request_rename(self) -> None:
        entry = self._current_entry()
        if entry is None or not entry.editable:
            return
        name, accepted = QInputDialog.getText(
            self, "Rename custom pose", "Pose name:", QLineEdit.Normal, entry.display_name
        )
        if accepted and name.strip() and name.strip() != entry.display_name:
            self.renameRequested.emit(entry.entry_id, name.strip())

    def _request_delete(self) -> None:
        if entry_id := self.selected_entry_id():
            self.deleteRequested.emit(entry_id)

    def _request_add_keyframe(self) -> None:
        if self._motion_editable and (entry_id := self.selected_entry_id()):
            self.addAsKeyframeRequested.emit(entry_id)

    def _update_actions(self, entry: PoseLibraryEntry | None) -> None:
        editable = entry is not None and entry.editable
        self.create_button.setEnabled(self.tabs.currentWidget() is self.custom_list)
        self.update_button.setEnabled(editable)
        self.duplicate_button.setText(
            "MAKE A COPY" if entry and entry.origin is PoseOrigin.BUILTIN else "DUPLICATE"
        )
        self.duplicate_button.setEnabled(entry is not None)
        self.rename_button.setEnabled(editable)
        self.delete_button.setEnabled(editable)
        self.add_keyframe_button.setEnabled(editable and self._motion_editable)
