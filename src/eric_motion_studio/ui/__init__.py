"""Qt user-interface boundary."""

from __future__ import annotations

from eric_motion_studio.config import Settings


def run_gui(settings: Settings) -> int:
    """Start the ERIC Motion Studio application.

    PySide6 is deliberately imported here rather than at package import time.
    """

    from PySide6.QtWidgets import QApplication

    from eric_motion_studio.ui.main_window import MotionStudioWindow

    application = QApplication.instance() or QApplication([])
    window = MotionStudioWindow(settings)
    window.show()
    return int(application.exec())
