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


class GestureLibraryWidget(QGroupBox):
    compileRequested = Signal(str)
    gestureSelected = Signal(str)

    def __init__(
        self,
        definitions: tuple[GestureDefinition, ...],
        parent=None,
    ) -> None:
        super().__init__("Gesture library", parent)
        self.setObjectName("gestureLibraryPanel")
        self.gesture_list = QListWidget()
        self.gesture_list.setObjectName("gestureList")
        for definition in definitions:
            item = QListWidgetItem(definition.canonical_id.replace("_", " ").title())
            item.setData(256, definition.canonical_id)
            item.setToolTip(", ".join(definition.aliases))
            self.gesture_list.addItem(item)

        self.prompt_edit = QLineEdit()
        self.prompt_edit.setObjectName("gesturePromptEdit")
        self.prompt_edit.setPlaceholderText("Describe a gesture…")
        self.compile_button = QPushButton("COMPILE & APPLY")
        self.compile_button.setObjectName("compileGestureButton")

        prompt_layout = QHBoxLayout()
        prompt_layout.addWidget(self.prompt_edit, 1)
        prompt_layout.addWidget(self.compile_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Available definitions"))
        layout.addWidget(self.gesture_list, 1)
        layout.addLayout(prompt_layout)

        self.compile_button.clicked.connect(self._request_compile)
        self.prompt_edit.returnPressed.connect(self._request_compile)
        self.gesture_list.currentItemChanged.connect(self._selection_changed)

    def _request_compile(self) -> None:
        self.compileRequested.emit(self.prompt_edit.text())

    def _selection_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is not None:
            self.gestureSelected.emit(str(current.data(256)))
