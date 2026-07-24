from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from eric_motion_studio.config import Settings
from eric_motion_studio.domain import JointValues, Keyframe, Motion, TrajectoryFrame
from eric_motion_studio.runtime import (
    MalformedStateError,
    MujocoAdapter,
    SafetyViolation,
    SimulationMode,
    StaleStateError,
    ViewerPlaybackOutput,
    ViewerProcessError,
    ViewerProcessManager,
    ViewerProcessStatus,
    ViewerStateStore,
)
from eric_motion_studio.runtime.viewer_process import ViewerLaunchSettings
from eric_motion_studio.ui.controllers import PlaybackController


class FakeProcess:
    def __init__(self, pid: int = 8123) -> None:
        self.pid = pid
        self.exit_code: int | None = None
        self.terminated = False
        self.killed = False
        self.timeout_on_terminate = False

    def poll(self) -> int | None:
        return self.exit_code

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self.exit_code = -9

    def wait(self, timeout: float | None = None) -> int:
        if self.timeout_on_terminate and not self.killed:
            raise subprocess.TimeoutExpired("viewer", timeout)
        self.exit_code = 0 if self.exit_code is None else self.exit_code
        return self.exit_code


class ViewerStateTests(unittest.TestCase):
    def test_atomic_round_trip_and_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run" / "pose.json"
            store = ViewerStateStore(path)
            joints = JointValues.from_mapping({"waist_yaw_joint": 0.125})

            first = store.write(joints)
            second = store.write(joints)
            loaded = store.read(max_age_seconds=5.0)

            self.assertEqual(first.sequence, 1)
            self.assertEqual(second.sequence, 2)
            self.assertEqual(loaded.sequence, 2)
            self.assertAlmostEqual(loaded.joints.get("waist_yaw_joint"), 0.125)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_malformed_and_stale_state_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pose.json"
            path.write_text("{broken", encoding="utf-8")
            store = ViewerStateStore(path)
            with self.assertRaises(MalformedStateError):
                store.read()

            store.write(JointValues.neutral())
            os.utime(path, (10.0, 10.0))
            stale_store = ViewerStateStore(path, clock=lambda: 20.0)
            with self.assertRaises(StaleStateError):
                stale_store.read(max_age_seconds=5.0)

    def test_wrong_schema_and_incomplete_joints_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pose.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "wrong",
                        "sequence": 1,
                        "updated_at": "now",
                        "joint_offsets_rad": {},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(MalformedStateError):
                ViewerStateStore(path).read()


class ViewerProcessTests(unittest.TestCase):
    def setUp(self):
        self.settings = ViewerLaunchSettings(
            model_path=Path("/package/model.xml"),
            state_path=Path("/runtime/pose.json"),
            python_executable=Path("/active/venv/bin/python"),
        )

    def test_command_uses_injected_active_interpreter_and_package_module(self):
        self.assertEqual(
            self.settings.command(),
            (
                "/active/venv/bin/python",
                "-m",
                "eric_motion_studio.viewer",
                "--model-path",
                "/package/model.xml",
                "--state-file",
                "/runtime/pose.json",
                "--simulation-mode",
                "AUTHORING_KINEMATIC",
            ),
        )

    def test_start_stop_and_forced_shutdown(self):
        launched: list[tuple[str, ...]] = []
        process = FakeProcess()
        process.timeout_on_terminate = True

        def launch(command):
            launched.append(tuple(command))
            return process

        manager = ViewerProcessManager(self.settings, launcher=launch)
        self.assertEqual(manager.start(), process.pid)
        self.assertEqual(manager.status, ViewerProcessStatus.RUNNING)
        self.assertEqual(launched, [self.settings.command()])

        manager.stop()
        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)
        self.assertEqual(manager.status, ViewerProcessStatus.STOPPED)

    def test_crash_is_reported_and_not_silently_restarted(self):
        process = FakeProcess()
        manager = ViewerProcessManager(
            self.settings,
            launcher=lambda _command: process,
        )
        manager.start()
        process.exit_code = 7

        self.assertEqual(manager.status, ViewerProcessStatus.CRASHED)
        with self.assertRaisesRegex(ViewerProcessError, "code 7"):
            manager.start()

    def test_playback_writes_before_start_and_detects_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            state_store = ViewerStateStore(Path(directory) / "pose.json")
            process = FakeProcess()
            manager = ViewerProcessManager(
                self.settings,
                launcher=lambda _command: process,
            )
            output = ViewerPlaybackOutput(state_store, manager)
            frame = TrajectoryFrame(0.0, JointValues.neutral())

            output.apply_frame(frame)
            self.assertTrue(state_store.path.is_file())
            self.assertEqual(manager.status, ViewerProcessStatus.RUNNING)

            process.exit_code = 3
            with self.assertRaisesRegex(ViewerProcessError, "code 3"):
                output.apply_frame(frame)

    def test_playback_controller_reports_viewer_failure(self):
        class FailingOutput:
            def apply_frame(self, _frame):
                raise ViewerProcessError("viewer crashed with code 4")

            def reset(self):
                raise ViewerProcessError("viewer crashed with code 4")

            def close(self):
                pass

        controller = PlaybackController(FailingOutput())
        statuses: list[str] = []
        controller.subscribe_status(statuses.append)
        controller.set_motion(
            Motion(
                name="Failure",
                keyframes=(Keyframe("Neutral", 100, JointValues.neutral()),),
            )
        )

        controller.play()

        self.assertFalse(controller.state.playing)
        self.assertEqual(
            statuses,
            ["Viewer unavailable: viewer crashed with code 4"],
        )


class MujocoAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model_path = Settings.load(environment={"HOME": "/tmp/eric-runtime-tests"}).model_path

    def test_model_load_bindings_neutral_and_pose_application(self):
        adapter = MujocoAdapter(self.model_path)
        offsets = {
            joint_name: (-0.02 if index % 2 else 0.02)
            for index, joint_name in enumerate(adapter.profile.joint_names)
        }
        pose = JointValues.from_mapping(offsets)
        applied = adapter.apply_pose(pose, sequence=17)

        self.assertEqual(len(adapter.bindings), 29)
        self.assertTrue(
            all(binding.actuator_index is not None for binding in adapter.bindings.values())
        )
        self.assertEqual(applied.sequence, 17)
        self.assertEqual(applied.root_position, (0.0, 0.0, 0.79))
        for joint_name, expected in offsets.items():
            self.assertAlmostEqual(
                dict(applied.joint_offsets)[joint_name],
                expected,
                places=7,
            )

    def test_pose_outside_safe_profile_is_rejected(self):
        adapter = MujocoAdapter(self.model_path)
        unsafe = JointValues.from_mapping({"waist_yaw_joint": 0.5})

        with self.assertRaises(SafetyViolation):
            adapter.apply_pose(unsafe)

    def test_simulation_mode_parsing_is_strict(self):
        self.assertIs(
            SimulationMode.parse("authoring_kinematic"),
            SimulationMode.AUTHORING_KINEMATIC,
        )
        with self.assertRaises(ValueError):
            SimulationMode.parse("unknown")


class ViewerEntryPointTests(unittest.TestCase):
    def test_packaged_viewer_self_test(self):
        environment = os.environ.copy()
        source_root = Path(__file__).resolve().parents[1] / "src"
        environment["PYTHONPATH"] = str(source_root)
        model_path = Settings.load(environment={"HOME": "/tmp/eric-viewer-entry-test"}).model_path

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "eric_motion_studio.viewer",
                "--model-path",
                str(model_path),
                "--self-test",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
            env=environment,
        )

        self.assertIn("VIEWER_MAPPING_TEST_OK", completed.stdout)
        self.assertIn("AUTHORING_STABILITY_30S_TEST_OK", completed.stdout)
        self.assertIn("VIEWER_SELF_TEST_OK", completed.stdout)


if __name__ == "__main__":
    unittest.main()
