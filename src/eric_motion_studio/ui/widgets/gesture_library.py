from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from eric_motion_studio.infrastructure import (
    MotionLibraryEntry,
    MotionOrigin,
)


class GestureLibraryWidget(QGroupBox):
    commandRequested = Signal(str)
    activationRequested = Signal(str)
    duplicateRequested = Signal(str)
    deleteRequested = Signal(str)
    refreshRequested = Signal()

    def __init__(
        self,
        parent=None,
    ) -> None:
        super().__init__("Motion library", parent)
        self.setObjectName("gestureLibraryPanel")
        self.gesture_list = QListWidget()
        self.gesture_list.setObjectName("gestureList")
        self._entries: dict[str, MotionLibraryEntry] = {}

        self.prompt_edit = QLineEdit()
        self.prompt_edit.setObjectName("gesturePromptEdit")
        self.prompt_edit.setPlaceholderText("Type a gesture command and press Enter…")
        self.duplicate_button = QPushButton("DUPLICATE")
        self.duplicate_button.setObjectName("duplicateLibraryMotionButton")
        self.duplicate_button.setToolTip(
            "Create and open an editable custom copy",
        )
        self.delete_button = QPushButton("DELETE")
        self.delete_button.setObjectName("deleteLibraryMotionButton")
        self.delete_button.setToolTip("Delete the selected custom motion")
        self.refresh_button = QPushButton("REFRESH")
        self.refresh_button.setObjectName("refreshMotionLibraryButton")
        self.refresh_button.setToolTip("Refresh the motion library")

        action_layout = QHBoxLayout()
        for button in (
            self.duplicate_button,
            self.delete_button,
            self.refresh_button,
        ):
            action_layout.addWidget(button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Click a motion to make it current"))
        layout.addWidget(self.gesture_list, 1)
        layout.addLayout(action_layout)
        layout.addWidget(self.prompt_edit)

        self.prompt_edit.returnPressed.connect(self._request_command)
        self.gesture_list.currentItemChanged.connect(self._selection_changed)
        self.duplicate_button.clicked.connect(self._request_duplicate)
        self.delete_button.clicked.connect(self._request_delete)
        self.refresh_button.clicked.connect(self.refreshRequested)
        self._update_actions(None)

    def set_entries(self, entries: tuple[MotionLibraryEntry, ...]) -> None:
        current = self._selected_entry_id()
        self._entries = {entry.entry_id: entry for entry in entries}
        with QSignalBlocker(self.gesture_list):
            self.gesture_list.clear()
            selected_row = -1
            for row, entry in enumerate(entries):
                prefix = "Built-in" if entry.origin is MotionOrigin.BUILTIN else "My Motion"
                item = QListWidgetItem(f"[{prefix}] {entry.display_name}")
                item.setData(256, entry.entry_id)
                details = [f"Origin: {entry.origin.value}"]
                if entry.command:
                    details.append(f"Command: {entry.command}")
                item.setToolTip("\n".join(details))
                self.gesture_list.addItem(item)
                if entry.entry_id == current:
                    selected_row = row
            self.gesture_list.setCurrentRow(selected_row)
        entry = self._entries.get(current or "")
        self._update_actions(entry)

    def select_entry(self, entry_id: str) -> None:
        for row in range(self.gesture_list.count()):
            item = self.gesture_list.item(row)
            if str(item.data(256)) == entry_id:
                with QSignalBlocker(self.gesture_list):
                    self.gesture_list.setCurrentRow(row)
                self._update_actions(self._entries.get(entry_id))
                return

    def clear_selection(self) -> None:
        with QSignalBlocker(self.gesture_list):
            self.gesture_list.clearSelection()
            self.gesture_list.setCurrentRow(-1)
        self._update_actions(None)

    def _request_command(self) -> None:
        self.commandRequested.emit(self.prompt_edit.text())

    def _selection_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is not None:
            entry = self._entries.get(str(current.data(256)))
            self._update_actions(entry)
            if entry is not None:
                self.activationRequested.emit(entry.entry_id)
        else:
            self._update_actions(None)

    def _selected_entry_id(self) -> str | None:
        item = self.gesture_list.currentItem()
        return str(item.data(256)) if item is not None else None

    def _request_duplicate(self) -> None:
        if entry_id := self._selected_entry_id():
            self.duplicateRequested.emit(entry_id)

    def _request_delete(self) -> None:
        if entry_id := self._selected_entry_id():
            self.deleteRequested.emit(entry_id)

    def _update_actions(self, entry: MotionLibraryEntry | None) -> None:
        self.duplicate_button.setEnabled(entry is not None)
        self.delete_button.setEnabled(entry is not None and entry.origin is MotionOrigin.USER)
