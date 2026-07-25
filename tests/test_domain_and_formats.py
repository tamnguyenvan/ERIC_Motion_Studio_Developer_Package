from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from eric_motion_studio.domain import (
    UNITREE_G1,
    Gesture,
    JointValues,
    Keyframe,
    Motion,
    PlaybackState,
    Pose,
    TrajectoryFrame,
    append_keyframe,
    clamp_joint_values,
    clone_motion,
    dense_trajectory,
    interpolate_joint_values,
    keyframes_from_trajectory,
    remove_keyframe,
    replace_keyframe,
    retime_motion,
)
from eric_motion_studio.infrastructure import (
    AnimationRepository,
    BrainOSExportRepository,
    GestureRepository,
    PoseRepository,
    SchemaValidationError,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "eric_motion_studio"
RESOURCE_ROOT = PACKAGE_ROOT / "resources"
LEGACY_ROOT = ROOT / "codebase" / "ERIC-Gesture-Lab"


class DomainOperationTests(unittest.TestCase):
    def setUp(self):
        self.neutral = JointValues.neutral()
        self.target = JointValues.from_mapping(
            {
                "left_shoulder_pitch_joint": -2.0,
                "right_elbow_joint": -0.4,
            }
        )
        self.motion = Motion(
            name="Domain test",
            keyframes=(
                Keyframe("Neutral", 100, self.neutral),
                Keyframe("Target", 600, self.target),
            ),
            description="pure domain test",
            created_at="2026-07-24T00:00:00+00:00",
            updated_at="2026-07-24T00:00:00+00:00",
        )

    def test_model_profile_centralizes_joint_metadata(self):
        self.assertEqual(len(UNITREE_G1.joint_names), 29)
        self.assertEqual(set(UNITREE_G1.limits), set(UNITREE_G1.joint_names))
        self.assertEqual(
            UNITREE_G1.groups["full_body"],
            UNITREE_G1.joint_names,
        )
        self.assertEqual(len(UNITREE_G1.groups["editor"]), 17)
        self.assertEqual(
            UNITREE_G1.limits["right_elbow_joint"].clamp(-4.0),
            -0.75,
        )

    def test_interpolation_clamping_cloning_and_retiming(self):
        midpoint = interpolate_joint_values(self.neutral, self.target, 0.5)
        self.assertEqual(midpoint.get("right_elbow_joint"), -0.2)

        clamped = clamp_joint_values(self.target)
        self.assertEqual(clamped.get("left_shoulder_pitch_joint"), -0.95)
        self.assertEqual(clamped.get("right_elbow_joint"), -0.4)

        cloned = clone_motion(self.motion)
        self.assertEqual(cloned, self.motion)
        self.assertIsNot(cloned, self.motion)
        self.assertIsNot(cloned.keyframes[0], self.motion.keyframes[0])

        retimed = retime_motion(self.motion, 2.0)
        self.assertEqual(
            [frame.duration_ms for frame in retimed.keyframes],
            [200, 1200],
        )
        self.assertEqual(self.motion.total_duration_ms, 700)

    def test_editing_and_playback_operations(self):
        added = append_keyframe(
            self.motion,
            Keyframe("Settle", 300, self.neutral),
        )
        self.assertEqual(len(added.keyframes), 3)

        replacement = Keyframe("Replacement", 400, self.neutral)
        edited = replace_keyframe(added, 1, replacement)
        self.assertEqual(edited.keyframes[1], replacement)
        removed = remove_keyframe(edited, 1)
        self.assertEqual(len(removed.keyframes), 2)

        plan = dense_trajectory(self.motion.keyframes, frame_rate=30)
        self.assertEqual(len(plan.frames), 19)
        self.assertEqual(plan.frames[0].joints, self.neutral)
        self.assertEqual(plan.frames[-1].joints, self.target)
        self.assertAlmostEqual(plan.duration_seconds, 0.6)

        state = PlaybackState(
            playing=True,
            frame_index=4,
            elapsed_seconds=0.2,
            speed=1.5,
        )
        self.assertTrue(state.playing)
        with self.assertRaises(ValueError):
            replace(state, speed=4.0)

    def test_trajectory_conversion_preserves_frame_timing(self):
        plan = dense_trajectory(self.motion.keyframes, frame_rate=30)
        keyframes = keyframes_from_trajectory(plan)
        reconstructed = dense_trajectory(keyframes, frame_rate=30)

        self.assertEqual({frame.duration_ms for frame in keyframes}, {33})
        self.assertAlmostEqual(
            reconstructed.duration_seconds,
            plan.duration_seconds,
        )


class RepositoryGoldenTests(unittest.TestCase):
    def test_all_packaged_animations_round_trip(self):
        repository = AnimationRepository()
        paths = sorted((RESOURCE_ROOT / "animations").glob("*.json"))
        self.assertEqual(len(paths), 3)

        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            for source in paths:
                motion = repository.load(source)
                output = output_root / source.name
                repository.save(output, motion)
                self.assertEqual(repository.load(output), motion)

                payload = json.loads(output.read_text())
                self.assertEqual(
                    payload["schema"],
                    "eric_motion_studio_animation_v1",
                )
                self.assertEqual(payload["version"], 1)

    def test_legacy_custom_editor_motion_round_trip(self):
        repository = AnimationRepository()
        source = LEGACY_ROOT / "animations" / "custom" / "untitled-eric-motion.json"
        motion = repository.load(source)

        self.assertEqual(len(motion.keyframes[0].joints.values), 29)
        self.assertEqual(
            motion.keyframes[0].joints.get("left_hip_pitch_joint"),
            0.0,
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / source.name
            repository.save(output, motion)
            self.assertEqual(repository.load(output), motion)

    def test_all_packaged_gestures_round_trip(self):
        repository = GestureRepository()
        paths = sorted((RESOURCE_ROOT / "gestures").glob("*.json"))
        self.assertEqual(len(paths), 3)

        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory)
            for source in paths:
                gesture = repository.load(source)
                output = output_root / source.name
                repository.save(output, gesture)
                self.assertEqual(repository.load(output), gesture)

    def test_pose_and_brainos_repositories_round_trip(self):
        pose_repository = PoseRepository()
        export_repository = BrainOSExportRepository()
        pose = Pose(
            joints=JointValues.from_mapping({"waist_yaw_joint": 0.1}),
            model_ref="Unitree G1",
            created_at="2026-07-24T00:00:00+00:00",
        )
        motion = Motion(
            name="Export",
            keyframes=(Keyframe("Pose", 900, pose.joints),),
            description="local export",
            created_at="2026-07-24T00:00:00+00:00",
            updated_at="2026-07-24T00:00:00+00:00",
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pose_path = root / "pose.json"
            export_path = root / "export.brainos-motion.json"
            pose_repository.save(pose_path, pose)
            export_repository.save(export_path, motion)

            self.assertEqual(pose_repository.load(pose_path), pose)
            self.assertEqual(export_repository.load(export_path), motion)
            export_payload = json.loads(export_path.read_text())
            self.assertEqual(
                export_payload["schema"],
                "brainos_motion_package_v1",
            )
            self.assertTrue(export_payload["simulation_only"])

    def test_repository_boundaries_reject_invalid_schemas(self):
        invalid_animation = {
            "schema": "unknown",
            "version": 1,
            "keyframes": [],
        }
        invalid_gesture = {
            "schema_version": 1,
            "joint_names": [],
            "frames": [],
        }

        with self.assertRaises(SchemaValidationError):
            AnimationRepository().serializer.from_payload(invalid_animation)
        with self.assertRaises(SchemaValidationError):
            GestureRepository().serializer.from_payload(invalid_gesture)

    def test_animation_rejects_non_integer_keyframe_durations(self):
        serializer = AnimationRepository().serializer
        source = RESOURCE_ROOT / "animations" / "conversational_talking.json"
        valid_payload = json.loads(source.read_text())

        for duration in (None, "900", 900.0, True):
            with self.subTest(duration=duration):
                payload = json.loads(json.dumps(valid_payload))
                if duration is None:
                    payload["keyframes"][0].pop("duration_ms")
                else:
                    payload["keyframes"][0]["duration_ms"] = duration
                with self.assertRaises(SchemaValidationError):
                    serializer.from_payload(payload)

    def test_gesture_serialization_rejects_mismatched_frame_profile(self):
        reordered_profile = replace(
            UNITREE_G1,
            joint_names=tuple(reversed(UNITREE_G1.joint_names)),
        )
        gesture = Gesture(
            gesture_id="profile-mismatch",
            display_name="Profile mismatch",
            source_prompt="test",
            frames=(
                TrajectoryFrame(
                    0.0,
                    JointValues.neutral(reordered_profile),
                ),
            ),
        )

        with self.assertRaises(SchemaValidationError):
            GestureRepository().serializer.to_payload(gesture)

    def test_brainos_enforces_version_and_simulation_only(self):
        serializer = BrainOSExportRepository().serializer
        motion = Motion(
            name="Export",
            keyframes=(Keyframe("Pose", 900, JointValues.neutral()),),
        )
        valid_payload = serializer.to_payload(motion)

        for field, value in (("version", None), ("simulation_only", False)):
            with self.subTest(field=field):
                payload = dict(valid_payload)
                if value is None:
                    payload.pop(field)
                else:
                    payload[field] = value
                with self.assertRaises(SchemaValidationError):
                    serializer.from_payload(payload)

        with self.assertRaises(SchemaValidationError):
            serializer.to_payload(replace(motion, simulation_only=False))

    def test_json_schema_documents_are_versioned_and_valid_json(self):
        schema_paths = sorted((RESOURCE_ROOT / "schemas").glob("*.schema.json"))
        self.assertEqual(len(schema_paths), 6)
        identifiers = {json.loads(path.read_text())["$id"] for path in schema_paths}
        self.assertEqual(len(identifiers), len(schema_paths))
        self.assertTrue(all("v1" in identifier for identifier in identifiers))


class PureImportTests(unittest.TestCase):
    def test_domain_and_formats_import_without_qt_or_mujoco(self):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        script = (
            "import sys; "
            "import eric_motion_studio.domain; "
            "import eric_motion_studio.infrastructure.formats; "
            "assert 'PySide6' not in sys.modules; "
            "assert 'mujoco' not in sys.modules; "
            "print('PURE_IMPORT_OK')"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.stdout.strip(), "PURE_IMPORT_OK")


if __name__ == "__main__":
    unittest.main()
