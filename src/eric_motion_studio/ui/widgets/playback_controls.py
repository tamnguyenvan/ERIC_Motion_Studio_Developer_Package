from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
)

from eric_motion_studio.ui.controllers import PlaybackViewState


class PlaybackControlsWidget(QGroupBox):
    playRequested = Signal()
    pauseRequested = Signal()
    stopRequested = Signal()
    playFromStartRequested = Signal()
    playFromSelectedRequested = Signal()
    speedChanged = Signal(float)
    seekRequested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__("Playback", parent)
        self.setObjectName("playbackControlsPanel")
        self.play_button = QPushButton("PLAY")
        self.play_button.setObjectName("playButton")
        self.pause_button = QPushButton("PAUSE")
        self.pause_button.setObjectName("pauseButton")
        self.stop_button = QPushButton("STOP")
        self.stop_button.setObjectName("stopButton")
        self.start_button = QPushButton("START")
        self.start_button.setObjectName("playFromStartButton")
        self.selected_button = QPushButton("FROM SELECTED")
        self.selected_button.setObjectName("playFromSelectedKeyframeButton")
        self.timeline = QSlider(Qt.Horizontal)
        self.timeline.setObjectName("playbackTimeline")
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setObjectName("playbackSpeedSpin")
        self.speed_spin.setRange(0.25, 2.0)
        self.speed_spin.setSingleStep(0.25)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setSuffix("×")

        layout = QHBoxLayout(self)
        layout.addWidget(self.play_button)
        layout.addWidget(self.pause_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.start_button)
        layout.addWidget(self.selected_button)
        layout.addWidget(self.timeline, 1)
        layout.addWidget(QLabel("Speed"))
        layout.addWidget(self.speed_spin)

        self.play_button.clicked.connect(self.playRequested)
        self.pause_button.clicked.connect(self.pauseRequested)
        self.stop_button.clicked.connect(self.stopRequested)
        self.start_button.clicked.connect(self.playFromStartRequested)
        self.selected_button.clicked.connect(self.playFromSelectedRequested)
        self.speed_spin.valueChanged.connect(self.speedChanged)
        self.timeline.sliderMoved.connect(self.seekRequested)

    def set_state(self, state: PlaybackViewState) -> None:
        blockers = (
            QSignalBlocker(self.timeline),
            QSignalBlocker(self.speed_spin),
        )
        self.timeline.setRange(0, max(0, state.frame_count - 1))
        self.timeline.setValue(state.frame_index)
        self.speed_spin.setValue(state.speed)
        self.play_button.setEnabled(not state.playing)
        self.pause_button.setEnabled(state.playing)
        self.stop_button.setEnabled(state.playing or state.paused or state.frame_index > 0)
        self.start_button.setEnabled(state.frame_count > 0)
        self.selected_button.setEnabled(state.frame_count > 0)
        del blockers
