from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from legacy_support import load_legacy, load_viewer


class LegacyCharacterizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy = load_legacy()
        cls.viewer = load_viewer()

    def test_motion_creation_and_editing_are_isolated(self):
        legacy = self.legacy
        frames = legacy.motion_from_description("wave right hand")
        edited = legacy.clone_keyframes(frames)

        self.assertGreaterEqual(len(frames), 3)
        self.assertEqual(edited, frames)
        self.assertIsNot(edited, frames)
        self.assertIsNot(edited[0], frames[0])

        edited[0].name = "Edited"
        edited[0].joint_offsets_rad["right_elbow_joint"] = -0.25
        self.assertNotEqual(frames[0].name, "Edited")
        self.assertNotEqual(
            frames[0].joint_offsets_rad["right_elbow_joint"],
            -0.25,
        )

    def test_playback_trajectory_preserves_timing_and_endpoints(self):
        legacy = self.legacy
        frames = [
            legacy.Keyframe("Start", 300, legacy.complete_offsets({})),
            legacy.Keyframe(
                "End",
                600,
                legacy.complete_offsets({"right_shoulder_pitch_joint": -0.3}),
            ),
        ]

        dense = legacy.dense_trajectory_from_keyframes(frames, frame_rate=30)
        legacy.validate_dense_trajectory(dense)
        ok, reason, accounting = legacy.validate_trajectory_accounting(frames)

        self.assertTrue(ok, reason)
        self.assertEqual(accounting["generated_frames"], len(frames))
        self.assertEqual(accounting["applied_frames"], len(dense))
        self.assertEqual(
            dense[0]["joint_targets"],
            legacy._frame_array_from_offsets(frames[0].joint_offsets_rad),
        )
        self.assertEqual(
            dense[-1]["joint_targets"],
            legacy._frame_array_from_offsets(frames[-1].joint_offsets_rad),
        )

    def test_animation_file_schema_round_trip(self):
        legacy = self.legacy
        frames = legacy.motion_from_description("thinking hand on chin")
        payload = legacy.build_motion_payload(
            frames,
            name="Characterization",
            loop=False,
            description="baseline",
            created_at="2026-07-24T00:00:00+07:00",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "motion.json"
            path.write_text(json.dumps(payload))
            loaded, metadata = legacy.load_animation_payload(path)

        self.assertEqual(metadata["schema"], "eric_motion_studio_animation_v1")
        self.assertEqual(metadata["version"], 1)
        self.assertEqual(
            metadata["total_duration_ms"],
            sum(frame.duration_ms for frame in loaded),
        )
        self.assertEqual(
            [legacy.keyframe_to_json(frame) for frame in loaded],
            [legacy.keyframe_to_json(frame) for frame in frames],
        )

    def test_animation_file_rejects_unknown_joints(self):
        legacy = self.legacy
        payload = legacy.animation_payload(
            [legacy.Keyframe("Invalid", 500, {"unknown_joint": 1.0})]
        )
        payload["keyframes"][0]["joint_targets"]["unknown_joint"] = 1.0
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "unknown joints"):
                legacy.load_animation_file(path)

    def test_gesture_save_load_contract(self):
        legacy = self.legacy
        frames = legacy.motion_from_description("wave right hand")
        payload = legacy.build_gesture_payload(
            keyframes=frames,
            gesture_id="wave_right",
            display_name="Wave Right",
            source_prompt="wave right hand",
            motion_type="one_shot",
            loopable=False,
            interruptible=True,
            return_to_neutral=True,
            tags=("greeting",),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gesture.json"
            path.write_text(json.dumps(payload))
            loaded = legacy.load_gesture_payload(path)

        self.assertEqual(loaded["schema_version"], 1)
        self.assertEqual(loaded["gesture_id"], "wave_right")
        self.assertEqual(loaded["frame_count"], len(loaded["frames"]))
        self.assertEqual(
            loaded["joint_names"],
            list(legacy.FULL_BODY_JOINTS),
        )

    def test_viewer_state_contract(self):
        viewer = self.viewer
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "live-state.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "eric_motion_studio_live_pose_v1",
                        "sequence": 42,
                        "joint_offsets_rad": {"right_elbow_joint": -0.25},
                    }
                )
            )

            offsets, sequence = viewer.read_state(path)
            missing = viewer.read_state(root / "missing.json")

        self.assertEqual(sequence, 42)
        self.assertEqual(offsets["right_elbow_joint"], -0.25)
        self.assertEqual(set(offsets), set(viewer.FULL_BODY_JOINTS))
        self.assertEqual(missing, ({}, None))

    def test_brainos_export_contract(self):
        legacy = self.legacy
        frames = legacy.motion_from_description("wave right hand")
        payload = legacy.animation_payload(frames, name="Wave")
        payload.update(
            {
                "schema": "brainos_motion_package_v1",
                "source": "ERIC Motion Studio",
                "description": "wave right hand",
                "export_note": (
                    "Local simulation-only package. Not deployed to physical ERIC."
                ),
            }
        )

        self.assertEqual(payload["schema"], "brainos_motion_package_v1")
        self.assertEqual(payload["source"], "ERIC Motion Studio")
        self.assertTrue(payload["simulation_only"])
        self.assertTrue(payload["keyframes"])


if __name__ == "__main__":
    unittest.main()
