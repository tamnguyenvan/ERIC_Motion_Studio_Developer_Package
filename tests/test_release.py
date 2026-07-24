from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_release_audit_passes(self):
        completed = subprocess.run(
            [sys.executable, "tools/release_audit.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertIn("RELEASE_AUDIT_OK", completed.stdout)

    def test_release_documentation_covers_required_topics(self):
        for name in (
            "architecture.md",
            "gesture-authoring.md",
            "file-formats.md",
            "testing.md",
            "release.md",
        ):
            self.assertTrue((ROOT / "docs" / name).is_file(), name)

        release = (ROOT / "docs" / "release.md").read_text(encoding="utf-8")
        self.assertIn("Rollback", release)
        self.assertIn("0.1.0", release)

    def test_pyproject_declares_only_supported_entry_points(self):
        metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertEqual(metadata.count("eric-motion-studio ="), 1)
        self.assertEqual(metadata.count("eric-motion-studio-viewer ="), 1)


if __name__ == "__main__":
    unittest.main()
