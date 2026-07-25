from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from eric_motion_studio.gestures import GestureCompiler
from eric_motion_studio.infrastructure import (
    AnimationRepository,
    MotionLibrary,
    MotionOrigin,
    migrate_legacy_user_files,
)


class MotionLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.library = MotionLibrary(
            self.root / "motions",
            GestureCompiler.default(),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_duplicate_adds_an_editable_custom_motion_immediately(self):
        builtins = self.library.entries()
        self.assertEqual(len(builtins), 25)
        self.assertTrue(all(entry.origin is MotionOrigin.BUILTIN for entry in builtins))
        idle_entry = next(entry for entry in builtins if entry.canonical_id == "idle_pose")

        builtin, builtin_path = self.library.load(idle_entry.entry_id)
        custom, custom_path = self.library.duplicate(idle_entry.entry_id)

        self.assertIsNone(builtin_path)
        self.assertEqual(dict(builtin.metadata)["library_origin"], "builtin")
        self.assertTrue(custom_path.is_file())
        self.assertEqual(custom.name, f"{builtin.name} Copy")
        self.assertEqual(dict(custom.metadata)["library_origin"], "user")
        self.assertNotIn("library_status", dict(custom.metadata))
        entries = self.library.entries()
        custom_entry = next(entry for entry in entries if entry.path == custom_path)
        self.assertEqual(custom_entry.origin, MotionOrigin.USER)
        self.assertTrue(custom_entry.editable)

    def test_duplicate_names_are_unique_and_custom_motion_can_be_deleted(self):
        idle = next(entry for entry in self.library.entries() if entry.canonical_id == "idle_pose")
        first, first_path = self.library.duplicate(idle.entry_id)
        first_entry = next(entry for entry in self.library.entries() if entry.path == first_path)
        second, second_path = self.library.duplicate(first_entry.entry_id)

        self.assertEqual(second.name, f"{first.name.removesuffix(' Copy')} Copy 2")
        self.assertNotEqual(first_path, second_path)
        self.assertFalse(hasattr(self.library, "approve"))

        second_entry = next(entry for entry in self.library.entries() if entry.path == second_path)
        deleted = self.library.delete(second_entry.entry_id)
        self.assertEqual(deleted, second_path)
        self.assertFalse(deleted.exists())

    def test_create_adds_motion_and_discards_legacy_approval_metadata(self):
        idle = next(entry for entry in self.library.entries() if entry.canonical_id == "idle_pose")
        motion, _path = self.library.load(idle.entry_id)
        legacy = replace(
            motion,
            metadata=(*motion.metadata, ("library_status", "approved")),
        )

        stored, path = self.library.create(legacy)
        loaded, loaded_path = self.library.load(f"user:{path.name}")

        self.assertEqual(loaded_path, path)
        self.assertEqual(loaded.name, stored.name)
        self.assertEqual(len(loaded.keyframes), len(stored.keyframes))
        self.assertNotIn("library_status", dict(loaded.metadata))

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
