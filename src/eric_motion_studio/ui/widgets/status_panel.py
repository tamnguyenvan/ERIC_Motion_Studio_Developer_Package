from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StatusPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("statusPanel")
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusMessage")
        self.dirty_label = QLabel("Saved")
        self.dirty_label.setObjectName("dirtyStatus")
        self.mode_label = QLabel("SIMULATION ONLY")
        self.mode_label.setObjectName("simulationStatus")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.addWidget(self.status_label, 1)
        layout.addWidget(self.dirty_label)
        layout.addWidget(self.mode_label)

    def set_message(self, message: str) -> None:
        self.status_label.setText(message)

    def set_dirty(self, dirty: bool) -> None:
        self.dirty_label.setText("Unsaved changes" if dirty else "Saved")
