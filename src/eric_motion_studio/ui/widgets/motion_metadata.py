from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QTextEdit,
)

from eric_motion_studio.domain import Motion


class _DescriptionEdit(QTextEdit):
    editingFinished = Signal()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.editingFinished.emit()


class MotionMetadataWidget(QGroupBox):
    metadataChanged = Signal(str, str, bool)

    def __init__(self, parent=None) -> None:
        super().__init__("Motion metadata", parent)
        self.setObjectName("motionMetadataPanel")
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("motionNameEdit")
        self.description_edit = _DescriptionEdit()
        self.description_edit.setObjectName("motionDescriptionEdit")
        self.description_edit.setMaximumHeight(90)
        self.loop_check = QCheckBox("Loop playback")
        self.loop_check.setObjectName("motionLoopCheck")

        layout = QFormLayout(self)
        layout.addRow("Name", self.name_edit)
        layout.addRow("Description", self.description_edit)
        layout.addRow("", self.loop_check)

        self.name_edit.editingFinished.connect(self._emit_metadata)
        self.description_edit.editingFinished.connect(self._emit_metadata)
        self.loop_check.toggled.connect(self._emit_metadata)

    def _emit_metadata(self) -> None:
        self.metadataChanged.emit(
            self.name_edit.text(),
            self.description_edit.toPlainText(),
            self.loop_check.isChecked(),
        )

    def set_motion(self, motion: Motion) -> None:
        blockers = (
            QSignalBlocker(self.name_edit),
            QSignalBlocker(self.description_edit),
            QSignalBlocker(self.loop_check),
        )
        self.name_edit.setText(motion.name)
        self.description_edit.setPlainText(motion.description)
        self.loop_check.setChecked(motion.loop)
        del blockers

    def set_editable(self, editable: bool) -> None:
        self.name_edit.setReadOnly(not editable)
        self.description_edit.setReadOnly(not editable)
        self.loop_check.setEnabled(editable)
