from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eric_motion_studio.domain import JointValues
from eric_motion_studio.infrastructure import PoseLibrary, PoseOrigin

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = ROOT / "src" / "eric_motion_studio" / "resources"


class PoseLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.library = PoseLibrary(
            self.root / "poses",
            RESOURCE_ROOT / "pose_definitions" / "builtins.json",
            RESOURCE_ROOT / "gesture_stages" / "builtin_stages.json",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_builtin_catalog_and_semantic_style_search(self):
        entries = self.library.entries()

        self.assertEqual(len(entries), 22)
        self.assertTrue(all(entry.origin is PoseOrigin.BUILTIN for entry in entries))
        for query in ("thinking", "thoughtful", "hand on chin", "thnking"):
            with self.subTest(query=query):
                self.assertEqual(
                    self.library.search(query)[0].entry_id,
                    "builtin:thinking_chin",
                )
        self.assertEqual(
            self.library.search("akimbo")[0].entry_id,
            "builtin:hands_on_hips",
        )
        self.assertEqual(
            self.library.search("left hand raised")[0].entry_id,
            "builtin:raise_left_hand",
        )

    def test_mirrored_builtin_poses_use_the_opposite_arm(self):
        right, _path = self.library.load("builtin:raise_right_hand")
        left, _path = self.library.load("builtin:raise_left_hand")

        self.assertNotEqual(right.joints.get("right_shoulder_pitch_joint"), 0.0)
        self.assertEqual(right.joints.get("left_shoulder_pitch_joint"), 0.0)
        self.assertNotEqual(left.joints.get("left_shoulder_pitch_joint"), 0.0)
        self.assertEqual(left.joints.get("right_shoulder_pitch_joint"), 0.0)

    def test_custom_pose_create_update_rename_duplicate_and_delete(self):
        joints = JointValues.from_mapping({"right_shoulder_pitch_joint": -0.3})
        pose, path = self.library.create(joints, "Presentation Ready")
        entry_id = f"user:{path.name}"

        self.assertTrue(path.is_file())
        self.assertEqual(dict(pose.metadata)["pose_name"], "Presentation Ready")
        self.assertEqual(self.library.search("presentation ready")[0].entry_id, entry_id)

        updated_joints = JointValues.from_mapping({"right_shoulder_pitch_joint": -0.5})
        updated, _path = self.library.update(entry_id, updated_joints)
        self.assertEqual(updated.joints, updated_joints)

        renamed, _path = self.library.rename(entry_id, "Speaker Ready")
        self.assertEqual(dict(renamed.metadata)["pose_name"], "Speaker Ready")
        self.assertEqual(dict(renamed.metadata)["pose_id"], "presentation_ready")
        self.assertEqual(self.library.search("speaker ready")[0].entry_id, entry_id)

        duplicate, duplicate_path = self.library.duplicate(entry_id)
        self.assertEqual(dict(duplicate.metadata)["pose_name"], "Speaker Ready Copy")
        self.assertNotEqual(path, duplicate_path)

        duplicate_entry = f"user:{duplicate_path.name}"
        self.assertEqual(self.library.delete(duplicate_entry), duplicate_path)
        self.assertFalse(duplicate_path.exists())


if __name__ == "__main__":
    unittest.main()
