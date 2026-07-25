from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from eric_motion_studio.domain import Motion
from eric_motion_studio.domain.values import (
    MAX_KEYFRAME_DURATION_MS,
    MIN_KEYFRAME_DURATION_MS,
)


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

    def __init__(self, parent=None) -> None:
        super().__init__("Keyframes", parent)
        self.setObjectName("keyframeEditorPanel")
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

        self.add_button = QPushButton("ADD")
        self.add_button.setObjectName("addKeyframeButton")
        self.capture_button = QPushButton("CAPTURE")
        self.capture_button.setObjectName("captureKeyframeButton")
        self.delete_button = QPushButton("DELETE")
        self.delete_button.setObjectName("deleteKeyframeButton")
        self.up_button = QPushButton("↑")
        self.up_button.setObjectName("moveKeyframeUpButton")
        self.down_button = QPushButton("↓")
        self.down_button.setObjectName("moveKeyframeDownButton")
        self.duplicate_button = QPushButton("DUPLICATE")
        self.duplicate_button.setObjectName("duplicateKeyframeButton")
        self.preview_button = QPushButton("PREVIEW")
        self.preview_button.setObjectName("previewKeyframeButton")

        buttons = QGridLayout()
        buttons.addWidget(self.add_button, 0, 0)
        buttons.addWidget(self.capture_button, 0, 1)
        buttons.addWidget(self.delete_button, 0, 2)
        buttons.addWidget(self.up_button, 1, 0)
        buttons.addWidget(self.down_button, 1, 1)
        buttons.addWidget(self.duplicate_button, 1, 2)
        buttons.addWidget(self.preview_button, 2, 0, 1, 3)
        buttons.addWidget(QLabel("Duration"), 3, 0)
        buttons.addWidget(self.duration_spin, 3, 1, 1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(self.keyframe_list, 1)
        layout.addLayout(buttons)

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
        self.delete_button.setEnabled(len(motion.keyframes) > 1)
        self.up_button.setEnabled(selected_index > 0)
        self.down_button.setEnabled(selected_index < len(motion.keyframes) - 1)
        self.duplicate_button.setEnabled(bool(motion.keyframes))
        self.preview_button.setEnabled(bool(motion.keyframes))
        del blockers

    def _begin_rename(self, item: QListWidgetItem) -> None:
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
