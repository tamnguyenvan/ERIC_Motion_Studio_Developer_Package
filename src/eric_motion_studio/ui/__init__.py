"""Qt user-interface boundary."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from eric_motion_studio.config import Settings


def configure_qt_plugin_path() -> None:
    """Validate PySide6's bundled plugins before creating the Qt application.

    macOS launcher sessions can inherit stale Qt and dynamic-loader overrides
    from another Python installation. PySide6 already knows its isolated
    plugin tree, so removing those overrides lets Qt discover Cocoa normally.
    Linux and headless test environments retain their explicit platform choice.
    """

    try:
        import PySide6
    except Exception as exc:  # pragma: no cover - shown to user at startup
        print(f"ERROR: PySide6 package import failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    pyside_root = Path(PySide6.__file__).resolve().parent
    qt_plugins = pyside_root / "Qt" / "plugins"
    cocoa_plugin = qt_plugins / "platforms" / "libqcocoa.dylib"
    if sys.platform == "darwin":
        for name in (
            "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QT_QPA_PLATFORM",
            "DYLD_LIBRARY_PATH",
            "DYLD_FRAMEWORK_PATH",
        ):
            os.environ.pop(name, None)
        if not cocoa_plugin.is_file():
            print(f"ERROR: Qt Cocoa platform plugin not found: {cocoa_plugin}", file=sys.stderr)
            raise SystemExit(1)
        print(f"QT_PLUGIN_ROOT_VERIFIED: {qt_plugins}")
        print(f"QT_COCOA_PLUGIN_VERIFIED: {cocoa_plugin}")
        print("QT_PLUGIN_DISCOVERY: PySide6 default runtime discovery")


def run_gui(settings: Settings) -> int:
    """Start the ERIC Motion Studio application.

    PySide6 is deliberately imported here rather than at package import time.
    """

    configure_qt_plugin_path()

    from PySide6.QtWidgets import QApplication

    from eric_motion_studio.ui.main_window import MotionStudioWindow

    application = QApplication.instance() or QApplication([])
    window = MotionStudioWindow(settings)
    window.show()
    return int(application.exec())
