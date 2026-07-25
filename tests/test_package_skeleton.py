from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"


def _package_environment() -> dict[str, str]:
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{SOURCE_ROOT}{os.pathsep}{existing}" if existing else str(SOURCE_ROOT)
    )
    return environment


class PackageSkeletonTests(unittest.TestCase):
    def test_package_import_has_no_qt_or_mujoco_side_effects(self):
        script = (
            "import sys, eric_motion_studio; "
            "assert 'PySide6' not in sys.modules; "
            "assert 'mujoco' not in sys.modules; "
            "print(eric_motion_studio.__version__)"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=_package_environment(),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(completed.stdout.strip(), "0.1.0")

    def test_settings_precedence_and_mutable_path_isolation(self):
        from eric_motion_studio.config import RESOURCE_ROOT, Settings

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = {
                "HOME": str(root / "home"),
                "XDG_DATA_HOME": str(root / "environment-data"),
                "XDG_STATE_HOME": str(root / "environment-state"),
                "ERIC_MOTION_STUDIO_MODEL_PATH": str(root / "environment-model.xml"),
                "ERIC_MOTION_STUDIO_DATA_DIR": str(root / "environment-app-data"),
                "ERIC_MOTION_STUDIO_LOG_PATH": str(root / "environment.log"),
            }
            overrides = SimpleNamespace(
                model_path=root / "cli-model.xml",
                data_dir=root / "cli-data",
                export_dir=None,
                log_path=None,
                runtime_state_path=root / "cli-runtime.json",
            )

            settings = Settings.load(overrides, environment)

            self.assertEqual(settings.model_path, root / "cli-model.xml")
            self.assertEqual(settings.data_dir, root / "cli-data")
            self.assertEqual(settings.export_dir, root / "cli-data" / "exports")
            self.assertEqual(settings.log_path, root / "environment.log")
            self.assertEqual(settings.runtime_state_path, root / "cli-runtime.json")
            self.assertEqual(settings.resource_root, RESOURCE_ROOT)
            for mutable_path in (
                settings.data_dir,
                settings.motions_dir,
                settings.poses_dir,
                settings.compiled_dir,
                settings.export_dir,
                settings.log_path,
                settings.runtime_state_path,
            ):
                self.assertFalse(mutable_path.is_relative_to(RESOURCE_ROOT))

            settings.prepare_mutable_directories()
            self.assertTrue(settings.data_dir.is_dir())
            self.assertTrue(settings.motions_dir.is_dir())
            self.assertTrue(settings.poses_dir.is_dir())
            self.assertTrue(settings.compiled_dir.is_dir())
            self.assertTrue(settings.export_dir.is_dir())
            self.assertTrue(settings.log_path.parent.is_dir())
            self.assertTrue(settings.runtime_state_path.parent.is_dir())

    def test_packaged_default_resources_exist(self):
        from eric_motion_studio.config import Settings

        settings = Settings.load(environment={"HOME": "/tmp/eric-test-home"})

        self.assertTrue(settings.model_path.is_file())
        for relative in (
            "gesture_definitions/builtins.json",
            "gesture_lexicon/builtins.json",
            "gesture_stages/builtin_stages.json",
        ):
            self.assertTrue((settings.resource_root / relative).is_file(), relative)
        self.assertEqual(
            list((settings.resource_root / "animations").glob("*.json")),
            [],
        )
        self.assertEqual(
            list((settings.resource_root / "gestures").glob("*.json")),
            [],
        )

    def test_structured_logging_is_json_and_bounded(self):
        from eric_motion_studio.logging import (
            DEFAULT_BACKUP_COUNT,
            DEFAULT_MAX_LOG_BYTES,
            configure_logging,
        )

        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "motion-studio.jsonl"
            logger = configure_logging(log_path, console=False)
            logger.info("test_event", extra={"context": {"phase": 1}})
            for handler in logger.handlers:
                handler.flush()

            payload = json.loads(log_path.read_text().splitlines()[-1])
            handler = logger.handlers[0]

            self.assertEqual(payload["message"], "test_event")
            self.assertEqual(payload["context"], {"phase": 1})
            self.assertEqual(handler.maxBytes, DEFAULT_MAX_LOG_BYTES)
            self.assertEqual(handler.backupCount, DEFAULT_BACKUP_COUNT)

    def test_module_help_and_headless_startup(self):
        help_result = subprocess.run(
            [sys.executable, "-m", "eric_motion_studio", "--help"],
            cwd=ROOT,
            env=_package_environment(),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertIn("--headless", help_result.stdout)
        self.assertIn("--runtime-state-path", help_result.stdout)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            startup_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "eric_motion_studio",
                    "--headless",
                    "--no-console-log",
                    "--data-dir",
                    str(root / "data"),
                    "--log-path",
                    str(root / "logs" / "events.jsonl"),
                    "--runtime-state-path",
                    str(root / "run" / "live.json"),
                ],
                cwd=ROOT,
                env=_package_environment(),
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(startup_result.stdout, "")
            events = [
                json.loads(line)
                for line in (root / "logs" / "events.jsonl").read_text().splitlines()
            ]
            self.assertEqual(
                [event["message"] for event in events],
                ["startup", "headless_startup_ok"],
            )


if __name__ == "__main__":
    unittest.main()
