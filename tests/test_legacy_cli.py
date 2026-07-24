from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "codebase" / "ERIC-Gesture-Lab"
ENTRY_POINT = LAB / "eric_motion_studio.py"
FIXTURES = Path(__file__).parent / "fixtures"


def _markers(name: str) -> list[str]:
    return [line for line in (FIXTURES / name).read_text().splitlines() if line.strip()]


def _run(*arguments: str) -> str:
    completed = subprocess.run(
        [sys.executable, str(ENTRY_POINT), *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return completed.stdout


class LegacyCliTests(unittest.TestCase):
    def test_legacy_self_test_markers(self):
        output = _run("--self-test")
        missing = [marker for marker in _markers("self-test-markers.txt") if marker not in output]
        self.assertFalse(missing)

    def test_focused_command_audit_markers(self):
        output = _run("--audit-command", "wave right hand")
        missing = [
            marker for marker in _markers("command-audit-markers.txt") if marker not in output
        ]
        self.assertFalse(missing)


if __name__ == "__main__":
    unittest.main()
