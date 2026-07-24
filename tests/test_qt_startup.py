from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch


class QtStartupTests(unittest.TestCase):
    def test_linux_preserves_explicit_qt_platform_for_headless_runs(self):
        from eric_motion_studio.ui import configure_qt_plugin_path

        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}, clear=False):
            configure_qt_plugin_path()
            if sys.platform != "darwin":
                self.assertEqual(os.environ["QT_QPA_PLATFORM"], "offscreen")

    def test_macos_cleanup_removes_stale_qt_and_dynamic_loader_overrides(self):
        from eric_motion_studio.ui import configure_qt_plugin_path

        names = (
            "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QT_QPA_PLATFORM",
            "DYLD_LIBRARY_PATH",
            "DYLD_FRAMEWORK_PATH",
        )
        original_platform = sys.platform
        try:
            with (
                patch.object(sys, "platform", "darwin"),
                patch.dict(
                    os.environ,
                    {name: "/stale/path" for name in names},
                    clear=False,
                ),
            ):
                with patch("pathlib.Path.is_file", return_value=True):
                    configure_qt_plugin_path()
                for name in names:
                    self.assertNotIn(name, os.environ)
        finally:
            sys.platform = original_platform


if __name__ == "__main__":
    unittest.main()
