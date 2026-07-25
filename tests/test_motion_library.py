from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eric_motion_studio.gestures import GestureCompiler
from eric_motion_studio.infrastructure import (
    AnimationRepository,
    GestureRepository,
    MotionLibrary,
    MotionOrigin,
    MotionStatus,
    migrate_legacy_user_files,
)


class MotionLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.library = MotionLibrary(
            self.root / "motions",
            self.root / "compiled",
            GestureCompiler.default(),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_builtin_and_user_motions_share_one_library(self):
        builtins = self.library.entries()
        self.assertEqual(len(builtins), 25)
        self.assertTrue(all(entry.origin is MotionOrigin.BUILTIN for entry in builtins))
        idle_entry = next(entry for entry in builtins if entry.canonical_id == "idle_pose")

        motion, path = self.library.load(idle_entry.entry_id)

        self.assertIsNone(path)
        self.assertEqual(dict(motion.metadata)["library_status"], "draft")
        stored_path = self.library.save(motion)
        entries = self.library.entries()
        custom = next(entry for entry in entries if entry.path == stored_path)
        self.assertEqual(custom.origin, MotionOrigin.USER)
        self.assertEqual(custom.status, MotionStatus.DRAFT)

    def test_approval_persists_source_and_compiled_artifact(self):
        idle = next(entry for entry in self.library.entries() if entry.canonical_id == "idle_pose")
        motion, _path = self.library.load(idle.entry_id)

        approved = self.library.approve(motion)

        self.assertTrue(approved.motion_path.is_file())
        self.assertTrue(approved.artifact_path.is_file())
        artifact = GestureRepository().load(approved.artifact_path)
        self.assertEqual(artifact.display_name, approved.motion.name)
        self.assertEqual(dict(approved.motion.metadata)["library_status"], "approved")
        custom = next(
            entry for entry in self.library.entries() if entry.path == approved.motion_path
        )
        self.assertEqual(custom.status, MotionStatus.APPROVED)

        deleted = self.library.delete(custom.entry_id)
        self.assertEqual(deleted, approved.motion_path)
        self.assertFalse(deleted.exists())

    def test_legacy_flat_motion_is_copied_non_destructively(self):
        idle = next(entry for entry in self.library.entries() if entry.canonical_id == "idle_pose")
        motion, _path = self.library.load(idle.entry_id)
        legacy_path = self.root / "legacy-motion.json"
        AnimationRepository().save(legacy_path, motion)

        migrated = migrate_legacy_user_files(
            self.root,
            self.root / "motions",
            self.root / "poses",
            self.root / "compiled",
        )

        self.assertEqual(len(migrated), 1)
        self.assertTrue(legacy_path.is_file())
        self.assertTrue((self.root / "motions" / legacy_path.name).is_file())
