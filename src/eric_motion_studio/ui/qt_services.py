"""Qt implementations of injected dialog services."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from eric_motion_studio.config import Settings
from eric_motion_studio.ui.services import DialogService, UnsavedDecision


class QtDialogService(DialogService):
    def __init__(self, parent: QWidget, settings: Settings) -> None:
        self.parent = parent
        self.settings = settings

    def select_open_motion(self) -> Path | None:
        path, _filter = QFileDialog.getOpenFileName(
            self.parent,
            "Open ERIC motion",
            str(self.settings.data_dir),
            "ERIC motion (*.json);;JSON files (*.json)",
        )
        return Path(path) if path else None

    def select_save_motion(self, suggested_name: str) -> Path | None:
        path, _filter = QFileDialog.getSaveFileName(
            self.parent,
            "Save ERIC motion",
            str(self.settings.data_dir / f"{suggested_name}.json"),
            "ERIC motion (*.json)",
        )
        return Path(path) if path else None

    def select_export_path(self, suggested_name: str) -> Path | None:
        path, _filter = QFileDialog.getSaveFileName(
            self.parent,
            "Export local BrainOS motion",
            str(self.settings.export_dir / f"{suggested_name}.brainos-motion.json"),
            "BrainOS local motion (*.brainos-motion.json)",
        )
        return Path(path) if path else None

    def confirm_unsaved(self, motion_name: str) -> UnsavedDecision:
        result = QMessageBox.warning(
            self.parent,
            "Unsaved changes",
            f"Save changes to {motion_name}?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if result == QMessageBox.Save:
            return UnsavedDecision.SAVE
        if result == QMessageBox.Discard:
            return UnsavedDecision.DISCARD
        return UnsavedDecision.CANCEL

    def show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self.parent, title, message)
