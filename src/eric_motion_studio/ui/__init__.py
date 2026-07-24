"""Qt user-interface boundary."""

from __future__ import annotations

from eric_motion_studio.config import Settings


def run_gui(settings: Settings) -> int:
    """Start the Phase 1 application shell.

    PySide6 is deliberately imported here rather than at package import time.
    """

    from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

    application = QApplication.instance() or QApplication([])
    window = QMainWindow()
    window.setWindowTitle("ERIC Motion Studio")
    window.setCentralWidget(QLabel("ERIC Motion Studio — simulation only"))
    window.resize(720, 420)
    window.show()
    return int(application.exec())
