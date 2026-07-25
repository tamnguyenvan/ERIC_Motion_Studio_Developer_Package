from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SOURCE_ROOT)
    return environment


def _run_module(*arguments: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "eric_motion_studio", *arguments],
        cwd=ROOT,
        env=_environment(),
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class CutoverTests(unittest.TestCase):
    def test_focused_and_full_command_audits_use_active_package(self):
        focused = _run_module("--audit-command", "wave right hand")
        self.assertIn(
            "COMMAND_AUDIT_PHRASE_RESULT prompt=wave right hand action=wave status=PASS",
            focused.stdout,
        )

        complete = _run_module("--audit-commands")
        self.assertIn("ALL_COMMANDS_AUDITED", complete.stdout)
        self.assertIn("status=PASS", complete.stdout)

    def test_active_self_test_covers_cutover_regressions(self):
        completed = _run_module("--self-test", timeout=120)
        for marker in (
            "RESOURCE_LAYOUT_TEST_OK",
            "AUTHORING_REGRESSION_OK",
            "PLAYBACK_REGRESSION_OK",
            "FILE_COMPATIBILITY_REGRESSION_OK",
            "EXPORT_REGRESSION_OK",
            "VIEWER_SYNCHRONIZATION_REGRESSION_OK",
            "ALL_COMMANDS_AUDITED",
            "SELF_TEST_OK",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, completed.stdout)

    def test_all_implemented_gestures_apply_in_mujoco(self):
        completed = _run_module("--audit-mujoco-gestures", timeout=120)

        self.assertIn(
            "MUJOCO_ALL_GESTURES_AUDITED gestures=25 frames=1758 status=PASS",
            completed.stdout,
        )

    def test_cutover_path_resource_and_launcher_audit(self):
        completed = subprocess.run(
            [sys.executable, "tools/cutover_audit.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertIn("CUTOVER_RESOURCE_AUDIT_OK", completed.stdout)
        self.assertIn("CUTOVER_PATH_AUDIT_OK", completed.stdout)
        self.assertIn("CUTOVER_LAUNCHER_AUDIT_OK", completed.stdout)

    def test_legacy_tree_is_explicitly_read_only(self):
        notice = (ROOT / "codebase" / "README.md").read_text(encoding="utf-8")
        self.assertIn("Read-Only Legacy Backup", notice)
        self.assertIn("not a supported application source tree", notice)


if __name__ == "__main__":
    unittest.main()
