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
    QVBoxLayout,
)

from eric_motion_studio.infrastructure import PoseLibraryEntry, PoseOrigin


class PoseLibraryWidget(QGroupBox):
    searchRequested = Signal(str)
    previewRequested = Signal(str)
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

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("poseSearchEdit")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText(
            "Search poses… thinking, arms open, left hand raised",
        )

        self.pose_list = QListWidget()
        self.pose_list.setObjectName("poseLibraryList")

        self.create_button = QPushButton("SAVE CURRENT")
        self.create_button.setObjectName("createPoseLibraryButton")
        self.create_button.setToolTip("Save the current joint preview as a custom pose")
        self.update_button = QPushButton("UPDATE")
        self.update_button.setObjectName("updatePoseLibraryButton")
        self.update_button.setToolTip("Replace the selected custom pose with the preview")
        self.duplicate_button = QPushButton("DUPLICATE")
        self.duplicate_button.setObjectName("duplicatePoseLibraryButton")
        self.duplicate_button.setToolTip("Create a custom copy of the selected pose")
        self.rename_button = QPushButton("RENAME")
        self.rename_button.setObjectName("renamePoseLibraryButton")
        self.delete_button = QPushButton("DELETE")
        self.delete_button.setObjectName("deletePoseLibraryButton")
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
                self.refresh_button,
            )
        ):
            actions.addWidget(button, index // 3, index % 3)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Click a pose to apply it to the preview"))
        layout.addWidget(self.search_edit)
        layout.addWidget(self.pose_list, 1)
        layout.addLayout(actions)

        self.search_edit.textChanged.connect(self.searchRequested)
        self.pose_list.currentItemChanged.connect(self._selection_changed)
        self.create_button.clicked.connect(self._request_create)
        self.update_button.clicked.connect(self._request_update)
        self.duplicate_button.clicked.connect(self._request_duplicate)
        self.rename_button.clicked.connect(self._request_rename)
        self.delete_button.clicked.connect(self._request_delete)
        self.refresh_button.clicked.connect(self.refreshRequested)
        self._update_actions(None)

    @property
    def query(self) -> str:
        return self.search_edit.text()

    def set_results(self, entries: tuple[PoseLibraryEntry, ...]) -> None:
        current = self.selected_entry_id()
        self._entries = {entry.entry_id: entry for entry in entries}
        with QSignalBlocker(self.pose_list):
            self.pose_list.clear()
            selected_row = -1
            for row, entry in enumerate(entries):
                prefix = "Built-in" if entry.origin is PoseOrigin.BUILTIN else "My Pose"
                item = QListWidgetItem(f"[{prefix}] {entry.display_name}")
                item.setData(Qt.UserRole, entry.entry_id)
                details = [entry.description] if entry.description else []
                if entry.aliases:
                    details.append(f"Aliases: {', '.join(entry.aliases)}")
                if entry.tags:
                    details.append(f"Tags: {', '.join(entry.tags)}")
                if entry.body_regions:
                    details.append(f"Body: {', '.join(entry.body_regions)}")
                item.setToolTip("\n".join(details))
                self.pose_list.addItem(item)
                if entry.entry_id == current:
                    selected_row = row
            self.pose_list.setCurrentRow(selected_row)
        self._update_actions(self._entries.get(current or ""))

    def selected_entry_id(self) -> str | None:
        item = self.pose_list.currentItem()
        return str(item.data(Qt.UserRole)) if item is not None else None

    def select_entry(self, entry_id: str) -> None:
        for row in range(self.pose_list.count()):
            item = self.pose_list.item(row)
            if str(item.data(Qt.UserRole)) == entry_id:
                with QSignalBlocker(self.pose_list):
                    self.pose_list.setCurrentRow(row)
                self._update_actions(self._entries.get(entry_id))
                return

    def clear_selection(self) -> None:
        with QSignalBlocker(self.pose_list):
            self.pose_list.setCurrentRow(-1)
            self.pose_list.clearSelection()
        self._update_actions(None)

    def _selection_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        entry = self._entries.get(str(current.data(Qt.UserRole))) if current is not None else None
        self._update_actions(entry)
        if entry is not None:
            self.previewRequested.emit(entry.entry_id)

    def _request_create(self) -> None:
        name, accepted = QInputDialog.getText(
            self,
            "Save custom pose",
            "Pose name:",
            QLineEdit.Normal,
            "My Pose",
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
        entry_id = self.selected_entry_id()
        entry = self._entries.get(entry_id or "")
        if entry is None or not entry.editable:
            return
        name, accepted = QInputDialog.getText(
            self,
            "Rename custom pose",
            "Pose name:",
            QLineEdit.Normal,
            entry.display_name,
        )
        if accepted and name.strip() and name.strip() != entry.display_name:
            self.renameRequested.emit(entry.entry_id, name.strip())

    def _request_delete(self) -> None:
        if entry_id := self.selected_entry_id():
            self.deleteRequested.emit(entry_id)

    def _update_actions(self, entry: PoseLibraryEntry | None) -> None:
        editable = entry is not None and entry.editable
        self.update_button.setEnabled(editable)
        self.duplicate_button.setEnabled(entry is not None)
        self.rename_button.setEnabled(editable)
        self.delete_button.setEnabled(editable)
