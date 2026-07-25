from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
)

from eric_motion_studio.domain import Motion
from eric_motion_studio.domain.values import (
    MAX_KEYFRAME_DURATION_MS,
    MIN_KEYFRAME_DURATION_MS,
)
from eric_motion_studio.ui.icons import load_icon


class KeyframeEditorWidget(QGroupBox):
    selectionChanged = Signal(int)
    addRequested = Signal()
    captureRequested = Signal()
    deleteRequested = Signal()
    moveRequested = Signal(int)
    durationChanged = Signal(int)
    renameRequested = Signal(int, str)
    duplicateRequested = Signal()
    previewRequested = Signal()
    presetRequested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__("Keyframes", parent)
        self.setObjectName("keyframeEditorPanel")
        self._editable = True
        self.keyframe_list = QListWidget()
        self.keyframe_list.setObjectName("keyframeList")
        self.keyframe_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.duration_spin = QSpinBox()
        self.duration_spin.setObjectName("keyframeDurationSpin")
        self.duration_spin.setRange(
            MIN_KEYFRAME_DURATION_MS,
            MAX_KEYFRAME_DURATION_MS,
        )
        self.duration_spin.setSingleStep(50)
        self.duration_spin.setSuffix(" ms")

        self.add_button = QToolButton()
        self.add_button.setObjectName("addKeyframeButton")
        self.add_button.setIcon(load_icon("add_keyframe.png"))
        self.add_button.setText("+")
        self.add_button.setToolTip("Add keyframe")
        self.capture_button = QPushButton("CAPTURE")
        self.capture_button.setObjectName("captureKeyframeButton")
        self.delete_button = QToolButton()
        self.delete_button.setObjectName("deleteKeyframeButton")
        self.delete_button.setIcon(load_icon("delete_keyframe.png"))
        self.delete_button.setText("×")
        self.delete_button.setToolTip("Delete selected keyframe")
        self.up_button = QToolButton()
        self.up_button.setObjectName("moveKeyframeUpButton")
        self.up_button.setIcon(load_icon("move_up.png"))
        self.up_button.setText("↑")
        self.up_button.setToolTip("Move selected keyframe up")
        self.down_button = QToolButton()
        self.down_button.setObjectName("moveKeyframeDownButton")
        self.down_button.setIcon(load_icon("move_down.png"))
        self.down_button.setText("↓")
        self.down_button.setToolTip("Move selected keyframe down")
        self.duplicate_button = QToolButton()
        self.duplicate_button.setObjectName("duplicateKeyframeButton")
        self.duplicate_button.setIcon(load_icon("duplicate_keyframe.png"))
        self.duplicate_button.setText("⧉")
        self.duplicate_button.setToolTip("Duplicate selected keyframe")
        self.preview_button = QPushButton("PREVIEW")
        self.preview_button.setObjectName("previewKeyframeButton")

        buttons = QGridLayout()
        toolbar = QHBoxLayout()
        toolbar.setSpacing(2)
        toolbar.setAlignment(Qt.AlignLeft)
        for button in (
            self.add_button,
            self.delete_button,
            self.up_button,
            self.down_button,
            self.duplicate_button,
        ):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        buttons.addLayout(toolbar, 0, 0, 1, 3)
        buttons.addWidget(self.capture_button, 1, 0, 1, 3)
        buttons.addWidget(self.preview_button, 2, 0, 1, 3)
        buttons.addWidget(QLabel("Duration"), 3, 0)
        buttons.addWidget(self.duration_spin, 3, 1, 1, 2)

        presets = QHBoxLayout()
        self.preset_buttons: list[QPushButton] = []
        for label, preset in (
            ("Less movement", "less_movement"),
            ("More movement", "more_movement"),
            ("Hands lower", "hands_lower"),
            ("Slower", "slower"),
            ("Faster", "faster"),
        ):
            button = QPushButton(label)
            button.setObjectName(f"{preset}PresetButton")
            button.setToolTip(f"Apply preset: {label}")
            button.clicked.connect(
                lambda _checked=False, value=preset: self.presetRequested.emit(value)
            )
            self.preset_buttons.append(button)
            presets.addWidget(button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.keyframe_list, 1)
        layout.addLayout(buttons)
        layout.addLayout(presets)

        self.keyframe_list.currentRowChanged.connect(self.selectionChanged)
        self.keyframe_list.itemDoubleClicked.connect(self._begin_rename)
        self.add_button.clicked.connect(self.addRequested)
        self.capture_button.clicked.connect(self.captureRequested)
        self.delete_button.clicked.connect(self.deleteRequested)
        self.up_button.clicked.connect(lambda: self.moveRequested.emit(-1))
        self.down_button.clicked.connect(lambda: self.moveRequested.emit(1))
        self.duplicate_button.clicked.connect(self.duplicateRequested)
        self.preview_button.clicked.connect(self.previewRequested)
        self.duration_spin.valueChanged.connect(self.durationChanged)

    def set_motion(self, motion: Motion, selected_index: int) -> None:
        blockers = (
            QSignalBlocker(self.keyframe_list),
            QSignalBlocker(self.duration_spin),
        )
        self.keyframe_list.clear()
        for index, frame in enumerate(motion.keyframes, start=1):
            item = QListWidgetItem(frame.name)
            item.setToolTip(f"Keyframe {index} · {frame.duration_ms} ms")
            item.setData(Qt.UserRole, frame.name)
            self.keyframe_list.addItem(item)
        self.keyframe_list.setCurrentRow(selected_index)
        self.duration_spin.setValue(motion.keyframes[selected_index].duration_ms)
        self.add_button.setEnabled(self._editable)
        self.capture_button.setEnabled(self._editable)
        self.delete_button.setEnabled(self._editable and len(motion.keyframes) > 1)
        self.up_button.setEnabled(self._editable and selected_index > 0)
        self.down_button.setEnabled(self._editable and selected_index < len(motion.keyframes) - 1)
        self.duplicate_button.setEnabled(self._editable and bool(motion.keyframes))
        self.preview_button.setEnabled(bool(motion.keyframes))
        self.duration_spin.setEnabled(self._editable)
        for button in self.preset_buttons:
            button.setEnabled(self._editable)
        del blockers

    def set_editable(self, editable: bool) -> None:
        self._editable = editable

    def _begin_rename(self, item: QListWidgetItem) -> None:
        if not self._editable:
            return
        row = self.keyframe_list.row(item)
        original = str(item.data(Qt.UserRole) or item.text())
        name, accepted = QInputDialog.getText(
            self,
            "Rename keyframe",
            "Name:",
            QLineEdit.Normal,
            original,
        )
        if accepted and name.strip() and name.strip() != original:
            self.renameRequested.emit(row, name.strip())
