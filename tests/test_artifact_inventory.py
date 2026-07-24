from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "build_artifact_inventory.py"


def _load_inventory_module():
    spec = importlib.util.spec_from_file_location("build_artifact_inventory", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ArtifactInventoryTests(unittest.TestCase):
    def test_staged_file_is_owned_by_user_working_tree(self):
        inventory = _load_inventory_module()

        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            (repository / "docs").mkdir()
            staged_file = repository / "staged.txt"
            staged_file.write_text("pending\n")
            subprocess.run(
                ["git", "init", "--quiet"],
                cwd=repository,
                check=True,
                timeout=10,
            )
            subprocess.run(
                ["git", "add", staged_file.name],
                cwd=repository,
                check=True,
                timeout=10,
            )

            inventory.ROOT = repository
            inventory.OUTPUT = repository / "docs" / "artifact-inventory.tsv"
            inventory.main()

            rows = {
                columns[0]: columns
                for line in inventory.OUTPUT.read_text().splitlines()[1:]
                if (columns := line.split("\t"))
            }
            self.assertEqual(rows[staged_file.name][2], "user working tree")


if __name__ == "__main__":
    unittest.main()
