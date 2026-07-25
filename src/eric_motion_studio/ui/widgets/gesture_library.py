from __future__ import annotations

from PySide6.QtCore import Signal
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

from eric_motion_studio.gestures import GestureDefinition
from eric_motion_studio.infrastructure import (
    MotionLibraryEntry,
    MotionOrigin,
    MotionStatus,
)


class GestureLibraryWidget(QGroupBox):
    compileRequested = Signal(str)
    gestureSelected = Signal(str)
    motionLoadRequested = Signal(str)
    saveToLibraryRequested = Signal()
    approveRequested = Signal()
    deleteRequested = Signal(str)
    refreshRequested = Signal()

    def __init__(
        self,
        definitions: tuple[GestureDefinition, ...],
        parent=None,
    ) -> None:
        super().__init__("Gesture library", parent)
        self.setObjectName("gestureLibraryPanel")
        self.gesture_list = QListWidget()
        self.gesture_list.setObjectName("gestureList")
        self._definitions = {definition.canonical_id: definition for definition in definitions}
        self._entries: dict[str, MotionLibraryEntry] = {}

        self.prompt_edit = QLineEdit()
        self.prompt_edit.setObjectName("gesturePromptEdit")
        self.prompt_edit.setPlaceholderText("Describe a gesture…")
        self.compile_button = QPushButton("COMPILE & APPLY")
        self.compile_button.setObjectName("compileGestureButton")
        self.load_button = QPushButton("LOAD / EDIT COPY")
        self.load_button.setObjectName("loadLibraryMotionButton")
        self.save_button = QPushButton("SAVE TO LIBRARY")
        self.save_button.setObjectName("saveLibraryMotionButton")
        self.approve_button = QPushButton("APPROVE")
        self.approve_button.setObjectName("approveLibraryMotionButton")
        self.delete_button = QPushButton("DELETE")
        self.delete_button.setObjectName("deleteLibraryMotionButton")
        self.refresh_button = QPushButton("REFRESH")
        self.refresh_button.setObjectName("refreshMotionLibraryButton")

        prompt_layout = QHBoxLayout()
        prompt_layout.addWidget(self.prompt_edit, 1)
        prompt_layout.addWidget(self.compile_button)

        action_layout = QHBoxLayout()
        for button in (
            self.load_button,
            self.save_button,
            self.approve_button,
            self.delete_button,
            self.refresh_button,
        ):
            action_layout.addWidget(button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Built-in and custom motions"))
        layout.addWidget(self.gesture_list, 1)
        layout.addLayout(action_layout)
        layout.addLayout(prompt_layout)

        self.compile_button.clicked.connect(self._request_compile)
        self.prompt_edit.returnPressed.connect(self._request_compile)
        self.gesture_list.currentItemChanged.connect(self._selection_changed)
        self.gesture_list.itemDoubleClicked.connect(
            lambda _item: self._request_load(),
        )
        self.load_button.clicked.connect(self._request_load)
        self.save_button.clicked.connect(self.saveToLibraryRequested)
        self.approve_button.clicked.connect(self.approveRequested)
        self.delete_button.clicked.connect(self._request_delete)
        self.refresh_button.clicked.connect(self.refreshRequested)
        self._update_actions(None)

    def set_entries(self, entries: tuple[MotionLibraryEntry, ...]) -> None:
        current = self._selected_entry_id()
        self._entries = {entry.entry_id: entry for entry in entries}
        self.gesture_list.clear()
        selected_row = 0
        for row, entry in enumerate(entries):
            if entry.origin is MotionOrigin.BUILTIN:
                prefix = "Built-in"
            elif entry.status is MotionStatus.APPROVED:
                prefix = "Approved"
            else:
                prefix = "My Motion"
            item = QListWidgetItem(f"[{prefix}] {entry.display_name}")
            item.setData(256, entry.entry_id)
            details = [f"Origin: {entry.origin.value}", f"Status: {entry.status.value}"]
            if entry.command:
                details.append(f"Command: {entry.command}")
            item.setToolTip("\n".join(details))
            self.gesture_list.addItem(item)
            if entry.entry_id == current:
                selected_row = row
        if entries:
            self.gesture_list.setCurrentRow(selected_row)
        else:
            self._update_actions(None)

    def _request_compile(self) -> None:
        self.compileRequested.emit(self.prompt_edit.text())

    def _selection_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is not None:
            entry = self._entries.get(str(current.data(256)))
            self._update_actions(entry)
            if entry is not None and entry.canonical_id is not None:
                self.gestureSelected.emit(entry.canonical_id)

    def _selected_entry_id(self) -> str | None:
        item = self.gesture_list.currentItem()
        return str(item.data(256)) if item is not None else None

    def _request_load(self) -> None:
        if entry_id := self._selected_entry_id():
            self.motionLoadRequested.emit(entry_id)

    def _request_delete(self) -> None:
        if entry_id := self._selected_entry_id():
            self.deleteRequested.emit(entry_id)

    def _update_actions(self, entry: MotionLibraryEntry | None) -> None:
        self.load_button.setEnabled(entry is not None)
        self.delete_button.setEnabled(entry is not None and entry.origin is MotionOrigin.USER)
