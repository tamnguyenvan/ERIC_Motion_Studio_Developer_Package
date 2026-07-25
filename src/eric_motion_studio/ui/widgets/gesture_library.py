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
    QTabWidget,
    QVBoxLayout,
)

from eric_motion_studio.infrastructure import MotionLibraryEntry, MotionOrigin


class GestureLibraryWidget(QGroupBox):
    commandRequested = Signal(str)
    activationRequested = Signal(str)
    duplicateRequested = Signal(str)
    deleteRequested = Signal(str)
    refreshRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Motion library", parent)
        self.setObjectName("gestureLibraryPanel")
        self._entries: dict[str, MotionLibraryEntry] = {}
        self.custom_list = self._make_list("customGestureList")
        self.system_list = self._make_list("systemGestureList")
        self.tabs = QTabWidget()
        self.tabs.setObjectName("gestureOriginTabs")
        self.tabs.addTab(self.custom_list, "Custom")
        self.tabs.addTab(self.system_list, "System (Built-in)")
        self.gesture_list = self.custom_list  # compatibility alias
        self.prompt_edit = QLineEdit()
        self.prompt_edit.setObjectName("gesturePromptEdit")
        self.prompt_edit.setPlaceholderText("Type a gesture command and press Enter…")
        self.duplicate_button = QPushButton("DUPLICATE")
        self.duplicate_button.setObjectName("duplicateLibraryMotionButton")
        self.duplicate_button.setToolTip("Create and open an editable custom copy")
        self.delete_button = QPushButton("DELETE")
        self.delete_button.setObjectName("deleteLibraryMotionButton")
        self.delete_button.setToolTip("Delete the selected custom motion")
        self.refresh_button = QPushButton("REFRESH")
        self.refresh_button.setObjectName("refreshMotionLibraryButton")
        self.refresh_button.setToolTip("Refresh the motion library")
        actions = QHBoxLayout()
        for button in (self.duplicate_button, self.delete_button, self.refresh_button):
            actions.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Click a motion to make it current"))
        layout.addWidget(self.tabs, 1)
        layout.addLayout(actions)
        layout.addWidget(self.prompt_edit)
        self.prompt_edit.returnPressed.connect(
            lambda: self.commandRequested.emit(self.prompt_edit.text())
        )
        for widget in (self.custom_list, self.system_list):
            widget.currentItemChanged.connect(self._selection_changed)
        self.tabs.currentChanged.connect(lambda _index: self._update_actions(self._current_entry()))
        self.duplicate_button.clicked.connect(self._request_duplicate)
        self.delete_button.clicked.connect(self._request_delete)
        self.refresh_button.clicked.connect(self.refreshRequested)
        self._update_actions(None)

    @staticmethod
    def _make_list(name: str) -> QListWidget:
        widget = QListWidget()
        widget.setObjectName(name)
        return widget

    def set_entries(self, entries: tuple[MotionLibraryEntry, ...]) -> None:
        current = self._selected_entry_id()
        self._entries = {entry.entry_id: entry for entry in entries}
        for origin, widget in (
            (MotionOrigin.USER, self.custom_list),
            (MotionOrigin.BUILTIN, self.system_list),
        ):
            with QSignalBlocker(widget):
                widget.clear()
                for entry in entries:
                    if entry.origin is not origin:
                        continue
                    item = QListWidgetItem(entry.display_name)
                    item.setData(256, entry.entry_id)
                    details = [f"Origin: {entry.origin.value}"]
                    if entry.command:
                        details.append(f"Command: {entry.command}")
                    item.setToolTip("\n".join(details))
                    widget.addItem(item)
        if current:
            self.select_entry(current)
        else:
            self._update_actions(None)

    def select_entry(self, entry_id: str) -> None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return
        widget = self.custom_list if entry.origin is MotionOrigin.USER else self.system_list
        self.tabs.setCurrentWidget(widget)
        for row in range(widget.count()):
            if str(widget.item(row).data(256)) == entry_id:
                with QSignalBlocker(widget):
                    widget.setCurrentRow(row)
                self._update_actions(entry)
                return

    def clear_selection(self) -> None:
        for widget in (self.custom_list, self.system_list):
            with QSignalBlocker(widget):
                widget.clearSelection()
                widget.setCurrentRow(-1)
        self._update_actions(None)

    def _current_list(self) -> QListWidget:
        return self.tabs.currentWidget()  # type: ignore[return-value]

    def _selected_entry_id(self) -> str | None:
        item = self._current_list().currentItem()
        return str(item.data(256)) if item is not None else None

    def _current_entry(self) -> MotionLibraryEntry | None:
        return self._entries.get(self._selected_entry_id() or "")

    def _selection_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        entry = self._entries.get(str(current.data(256))) if current is not None else None
        self._update_actions(entry)
        if entry is not None:
            self.activationRequested.emit(entry.entry_id)

    def _request_duplicate(self) -> None:
        if entry_id := self._selected_entry_id():
            self.duplicateRequested.emit(entry_id)

    def _request_delete(self) -> None:
        if entry_id := self._selected_entry_id():
            self.deleteRequested.emit(entry_id)

    def _update_actions(self, entry: MotionLibraryEntry | None) -> None:
        self.duplicate_button.setText(
            "MAKE A COPY" if entry and entry.origin is MotionOrigin.BUILTIN else "DUPLICATE"
        )
        self.duplicate_button.setEnabled(entry is not None)
        self.delete_button.setEnabled(entry is not None and entry.origin is MotionOrigin.USER)
