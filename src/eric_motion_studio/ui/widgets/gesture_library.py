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
)


class GestureLibraryWidget(QGroupBox):
    compileRequested = Signal(str)
    gestureSelected = Signal(str)
    motionLoadRequested = Signal(str)
    duplicateRequested = Signal(str)
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
        self.load_button = QPushButton("OPEN")
        self.load_button.setObjectName("loadLibraryMotionButton")
        self.load_button.setToolTip("Open the selected custom motion")
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

        prompt_layout = QHBoxLayout()
        prompt_layout.addWidget(self.prompt_edit, 1)
        prompt_layout.addWidget(self.compile_button)

        action_layout = QHBoxLayout()
        for button in (
            self.load_button,
            self.duplicate_button,
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
            lambda _item: self._activate_selected(),
        )
        self.load_button.clicked.connect(self._request_load)
        self.duplicate_button.clicked.connect(self._request_duplicate)
        self.delete_button.clicked.connect(self._request_delete)
        self.refresh_button.clicked.connect(self.refreshRequested)
        self._update_actions(None)

    def set_entries(self, entries: tuple[MotionLibraryEntry, ...]) -> None:
        current = self._selected_entry_id()
        self._entries = {entry.entry_id: entry for entry in entries}
        self.gesture_list.clear()
        selected_row = 0
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
        if entries:
            self.gesture_list.setCurrentRow(selected_row)
        else:
            self._update_actions(None)

    def select_entry(self, entry_id: str) -> None:
        for row in range(self.gesture_list.count()):
            item = self.gesture_list.item(row)
            if str(item.data(256)) == entry_id:
                self.gesture_list.setCurrentRow(row)
                return

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

    def _request_duplicate(self) -> None:
        if entry_id := self._selected_entry_id():
            self.duplicateRequested.emit(entry_id)

    def _request_delete(self) -> None:
        if entry_id := self._selected_entry_id():
            self.deleteRequested.emit(entry_id)

    def _activate_selected(self) -> None:
        entry_id = self._selected_entry_id()
        entry = self._entries.get(entry_id or "")
        if entry is None:
            return
        if entry.origin is MotionOrigin.BUILTIN:
            self.duplicateRequested.emit(entry.entry_id)
        else:
            self.motionLoadRequested.emit(entry.entry_id)

    def _update_actions(self, entry: MotionLibraryEntry | None) -> None:
        self.load_button.setEnabled(entry is not None and entry.origin is MotionOrigin.USER)
        self.duplicate_button.setEnabled(entry is not None)
        self.delete_button.setEnabled(entry is not None and entry.origin is MotionOrigin.USER)
