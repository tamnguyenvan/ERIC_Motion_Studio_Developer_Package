from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QLabel,
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

    def __init__(self, parent=None) -> None:
        super().__init__("Keyframes", parent)
        self.setObjectName("keyframeEditorPanel")
        self.keyframe_list = QListWidget()
        self.keyframe_list.setObjectName("keyframeList")
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

        buttons = QGridLayout()
        buttons.addWidget(self.add_button, 0, 0)
        buttons.addWidget(self.capture_button, 0, 1)
        buttons.addWidget(self.delete_button, 0, 2)
        buttons.addWidget(self.up_button, 1, 0)
        buttons.addWidget(self.down_button, 1, 1)
        buttons.addWidget(QLabel("Duration"), 2, 0)
        buttons.addWidget(self.duration_spin, 2, 1, 1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(self.keyframe_list, 1)
        layout.addLayout(buttons)

        self.keyframe_list.currentRowChanged.connect(self.selectionChanged)
        self.add_button.clicked.connect(self.addRequested)
        self.capture_button.clicked.connect(self.captureRequested)
        self.delete_button.clicked.connect(self.deleteRequested)
        self.up_button.clicked.connect(lambda: self.moveRequested.emit(-1))
        self.down_button.clicked.connect(lambda: self.moveRequested.emit(1))
        self.duration_spin.valueChanged.connect(self.durationChanged)

    def set_motion(self, motion: Motion, selected_index: int) -> None:
        blockers = (
            QSignalBlocker(self.keyframe_list),
            QSignalBlocker(self.duration_spin),
        )
        self.keyframe_list.clear()
        for index, frame in enumerate(motion.keyframes, start=1):
            self.keyframe_list.addItem(
                QListWidgetItem(
                    f"{index}. {frame.name} — {frame.duration_ms} ms"
                )
            )
        self.keyframe_list.setCurrentRow(selected_index)
        self.duration_spin.setValue(
            motion.keyframes[selected_index].duration_ms
        )
        self.delete_button.setEnabled(len(motion.keyframes) > 1)
        self.up_button.setEnabled(selected_index > 0)
        self.down_button.setEnabled(
            selected_index < len(motion.keyframes) - 1
        )
        del blockers
