from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from eric_motion_studio.config import RESOURCE_ROOT
from eric_motion_studio.domain import JointValues, Keyframe, Motion
from eric_motion_studio.gestures import (
    DefinitionValidationError,
    Direction,
    GestureCompiler,
    GestureLexicon,
    GestureRegistry,
    GestureResolver,
    Intensity,
    LexiconValidationError,
    ResolutionStatus,
    Side,
    SlotName,
    Speed,
    extract_slots,
)
from eric_motion_studio.gestures.generators import default_generator_registry
from eric_motion_studio.gestures.stages import StageLibrary, StageValidationError
from eric_motion_studio.gestures.validators import validate_compiled_motion

ROOT = Path(__file__).resolve().parents[1]
DEFINITIONS_PATH = RESOURCE_ROOT / "gesture_definitions" / "builtins.json"
STAGES_PATH = RESOURCE_ROOT / "gesture_stages" / "builtin_stages.json"
LEXICON_PATH = RESOURCE_ROOT / "gesture_lexicon" / "builtins.json"

LEGACY_COMMANDS = {
    "talking_idle": (
        "talking motion",
        "natural talking motion",
        "conversational idle",
        "talking idle",
        "presentation talking motion",
        "happy talking motion",
    ),
    "wave": (
        "wave",
        "wave with your right hand",
        "wave with your left hand",
    ),
    "raise_arm": (
        "raise left arm",
        "raise right arm",
        "lift left hand",
        "lift right hand",
    ),
    "lower_arm": ("lower left arm", "lower right arm"),
    "both_arm_motion": ("open both arms as if introducing a speaker, pause, then relax",),
    "hand_to_chest": (
        (
            "place the right hand firmly on the centre of the chest "
            "while the left arm hangs by the side"
        ),
        ("place the left hand on the chest while extending the right arm outward"),
    ),
    "welcome_presentation": (
        "welcome the audience with both hands",
        (
            "raise both hands to chest height with open palms. sweep both arms "
            "in a wide horizontal arc from the far left side of the body to the "
            "far right while rotating the torso to follow the movement. pause. "
            "return to neutral"
        ),
    ),
    "scratch_head": (
        "scratch head",
        "thinking scratch",
        "rub side of head",
        "hand to temple",
    ),
    "thinking_hand_on_chin": (
        "hand on chin",
        "thinking pose",
        "thoughtful pose",
        "rub chin",
        "thinking with hand on chin",
        "looking thoughtful",
    ),
    "neutral_reset": ("return to neutral", "neutral"),
}

REQUESTED_COMMANDS = {
    "raise_arm": (
        "raise left hand",
        "raise right hand",
        "lift left hand",
        "lift right hand",
        "raise both hands",
    ),
    "lower_arm": ("lower left hand", "lower right hand", "lower both hands"),
    "wave": ("wave left hand", "wave right hand"),
    "point": ("point left", "point right"),
    "stop_gesture": ("stop gesture",),
    "thumbs_up": ("thumbs up",),
    "thumbs_down": ("thumbs down",),
    "clap": ("clap",),
    "arms_open": ("arms open", "arms out"),
    "cross_arms": ("cross arms",),
    "hands_on_hips": ("hands on hips",),
    "shrug": ("shrug",),
    "thinking_hand_on_chin": (
        "hand on chin",
        "think",
        "thinking",
        "thinking pose",
        "ponder",
    ),
    "scratch_head": ("scratch head",),
    "celebrate": ("celebrate", "cheer"),
    "welcome_presentation": ("welcome",),
    "wave_goodbye": ("wave goodbye",),
    "present_object": ("present object",),
    "idle_pose": ("idle", "idle pose", "rest", "standby"),
}


class GestureDefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(DEFINITIONS_PATH.read_text())
        cls.registry = GestureRegistry.from_payload(cls.payload)

    def test_every_legacy_alias_resolves_and_compiles(self):
        compiler = GestureCompiler.default()
        definition_aliases = {
            definition.canonical_id: set(definition.aliases)
            for definition in compiler.registry.definitions
        }

        for canonical_id, aliases in LEGACY_COMMANDS.items():
            for alias in aliases:
                with self.subTest(canonical_id=canonical_id, alias=alias):
                    self.assertIn(alias, definition_aliases[canonical_id])
                    result = compiler.compile(alias)
                    self.assertTrue(result.succeeded, result)
                    self.assertEqual(
                        result.resolution.definition.canonical_id,
                        canonical_id,
                    )
                    self.assertTrue(result.validation.passed)

        unsupported = compiler.compile("do a cartwheel")
        self.assertEqual(
            unsupported.resolution.status,
            ResolutionStatus.UNSUPPORTED,
        )

    def test_all_definition_commands_are_deterministic(self):
        compiler = GestureCompiler.default()
        for definition in compiler.registry.definitions:
            for command in (*definition.aliases, *definition.triggers):
                with self.subTest(definition=definition.canonical_id, command=command):
                    first = compiler.compile(command)
                    second = compiler.compile(command)
                    self.assertTrue(first.succeeded, first)
                    self.assertEqual(first, second)

    def test_short_trigger_and_specific_phrase_precedence(self):
        compiler = GestureCompiler.default()

        idle = compiler.compile("idle")
        talking = compiler.compile("talking idle")

        self.assertTrue(idle.succeeded, idle)
        self.assertEqual(idle.resolution.definition.canonical_id, "idle_pose")
        self.assertTrue(talking.succeeded, talking)
        self.assertEqual(talking.resolution.definition.canonical_id, "talking_idle")

    def test_morphological_and_concept_vocabulary(self):
        compiler = GestureCompiler.default()
        commands = {
            "waving left hand": "wave",
            "pointing right": "point",
            "clapping": "clap",
            "shrugging": "shrug",
            "pondering": "thinking_hand_on_chin",
            "celebrating": "celebrate",
            "standby": "idle_pose",
            "farewell": "wave_goodbye",
            "greeting": "welcome_presentation",
            "halt": "stop_gesture",
        }

        for command, canonical_id in commands.items():
            with self.subTest(command=command):
                result = compiler.compile(command)
                self.assertTrue(result.succeeded, result)
                self.assertEqual(result.resolution.definition.canonical_id, canonical_id)

    def test_fuzzy_matching_suggests_but_does_not_execute(self):
        result = GestureCompiler.default().compile("idel")

        self.assertFalse(result.succeeded)
        self.assertEqual(result.resolution.status, ResolutionStatus.UNSUPPORTED)
        self.assertEqual(result.resolution.suggestions[0], "idle_pose")
        self.assertIn("Did you mean: idle pose?", result.resolution.message)

    def test_requested_gesture_catalog_compiles_and_validates(self):
        compiler = GestureCompiler.default()

        for canonical_id, commands in REQUESTED_COMMANDS.items():
            for command in commands:
                with self.subTest(canonical_id=canonical_id, command=command):
                    result = compiler.compile(command)
                    self.assertTrue(result.succeeded, result)
                    self.assertEqual(
                        result.resolution.definition.canonical_id,
                        canonical_id,
                    )
                    self.assertTrue(result.validation.passed)

    def test_compositional_synonym_cross_product(self):
        compiler = GestureCompiler.default()

        for verb in ("raise", "lift", "elevate"):
            for side in (Side.LEFT, Side.RIGHT):
                for effector in ("hand", "arm"):
                    command = f"please {verb} your {side.value} {effector} slowly"
                    with self.subTest(command=command):
                        result = compiler.compile(command)
                        self.assertTrue(result.succeeded, result)
                        self.assertEqual(
                            result.resolution.definition.canonical_id,
                            "raise_arm",
                        )
                        self.assertEqual(result.resolution.slots.side, side)
                        self.assertEqual(result.resolution.slots.speed, Speed.SLOW)

    def test_both_side_is_composed_without_full_phrase_aliases(self):
        compiler = GestureCompiler.default()

        for command, canonical_id in (
            ("elevate both arms", "raise_arm"),
            ("bring down both hands", "lower_arm"),
            ("quickly wave with both hands", "wave"),
        ):
            with self.subTest(command=command):
                result = compiler.compile(command)
                self.assertTrue(result.succeeded, result)
                self.assertEqual(result.resolution.definition.canonical_id, canonical_id)
                self.assertEqual(result.resolution.slots.side, Side.BOTH)

    def test_conflicting_actions_are_not_guessed(self):
        result = GestureCompiler.default().compile("raise and lower the left hand")

        self.assertEqual(result.resolution.status, ResolutionStatus.AMBIGUOUS)
        self.assertEqual(result.resolution.candidates, ("lower_arm", "raise_arm"))

    def test_polite_fillers_do_not_require_duplicate_idiom_aliases(self):
        compiler = GestureCompiler.default()

        for command, canonical_id in (
            ("could you put your hands on your hips please", "hands_on_hips"),
            ("please give me a thumbs up", "thumbs_up"),
            ("could you think please", "thinking_hand_on_chin"),
            ("would you wave goodbye please", "wave_goodbye"),
        ):
            with self.subTest(command=command):
                result = compiler.compile(command)
                self.assertTrue(result.succeeded, result)
                self.assertEqual(result.resolution.definition.canonical_id, canonical_id)

    def test_lexicon_synonym_can_be_added_without_parser_code(self):
        lexicon_payload = json.loads(LEXICON_PATH.read_text())
        lexicon_payload["actions"]["raise"].append("hoist")
        lexicon = GestureLexicon.from_payload(lexicon_payload)
        compiler = GestureCompiler(
            self.registry,
            StageLibrary.from_path(STAGES_PATH),
            default_generator_registry(),
            lexicon,
        )

        result = compiler.compile("hoist the left hand")

        self.assertTrue(result.succeeded, result)
        self.assertEqual(result.resolution.definition.canonical_id, "raise_arm")
        self.assertEqual(result.resolution.slots.side, Side.LEFT)

    def test_lexicon_rejects_collisions_and_unknown_rule_terms(self):
        collision = json.loads(LEXICON_PATH.read_text())
        collision["actions"]["lower"].append("raise")
        with self.assertRaises(LexiconValidationError):
            GestureLexicon.from_payload(collision)

        invalid_rule = json.loads(LEXICON_PATH.read_text())
        invalid_rule["rules"][0]["actions"] = ["missing"]
        with self.assertRaises(LexiconValidationError):
            GestureLexicon.from_payload(invalid_rule)

        unknown_gesture = json.loads(LEXICON_PATH.read_text())
        unknown_gesture["rules"][0]["canonical_id"] = "missing"
        lexicon = GestureLexicon.from_payload(unknown_gesture)
        with self.assertRaises(LexiconValidationError):
            GestureCompiler(
                self.registry,
                StageLibrary.from_path(STAGES_PATH),
                default_generator_registry(),
                lexicon,
            )

    def test_validator_pipeline_reports_each_safety_category(self):
        compiler = GestureCompiler.default()
        resolved = compiler.resolver.resolve("wave with your right hand")
        definition = resolved.definition
        slots = resolved.slots
        self.assertIsNotNone(definition)
        self.assertIsNotNone(slots)

        unsafe = JointValues.from_mapping(
            {
                "left_hip_pitch_joint": 0.5,
                "left_shoulder_pitch_joint": -2.0,
                "left_shoulder_roll_joint": -0.3,
                "right_shoulder_roll_joint": 0.3,
            }
        )
        motion = Motion(
            name="Unsafe",
            keyframes=(
                Keyframe("Neutral", 100, JointValues.neutral()),
                Keyframe("Unsafe", 10000, unsafe),
            ),
            created_at="1970-01-01T00:00:00+00:00",
            updated_at="1970-01-01T00:00:00+00:00",
        )
        report = validate_compiled_motion(motion, definition, slots)
        codes = {issue.code for issue in report.issues}

        self.assertTrue(
            {
                "joint_limit",
                "trajectory_duration",
                "balance",
                "collision",
                "semantic_side",
                "neutral_return",
            }.issubset(codes)
        )

        amplitude_definition = replace(
            definition,
            constraints=replace(
                definition.constraints,
                min_amplitude_rad=3.0,
            ),
        )
        amplitude_report = validate_compiled_motion(
            motion,
            amplitude_definition,
            slots,
        )
        self.assertIn(
            "insufficient_amplitude",
            {issue.code for issue in amplitude_report.issues},
        )

    def test_synonym_can_be_added_using_definition_data_only(self):
        payload = copy.deepcopy(self.payload)
        wave = next(
            definition
            for definition in payload["definitions"]
            if definition["canonical_id"] == "wave"
        )
        wave["aliases"].append("offer a friendly greeting")
        registry = GestureRegistry.from_payload(payload)
        compiler = GestureCompiler(
            registry,
            StageLibrary.from_path(STAGES_PATH),
            default_generator_registry(),
        )

        result = compiler.compile("offer a friendly greeting")

        self.assertTrue(result.succeeded, result)
        self.assertEqual(result.resolution.definition.canonical_id, "wave")

    def test_short_trigger_can_be_added_using_definition_data_only(self):
        payload = copy.deepcopy(self.payload)
        idle = next(
            definition
            for definition in payload["definitions"]
            if definition["canonical_id"] == "idle_pose"
        )
        idle["triggers"].append("wait")
        registry = GestureRegistry.from_payload(payload)
        compiler = GestureCompiler(
            registry,
            StageLibrary.from_path(STAGES_PATH),
            default_generator_registry(),
        )

        result = compiler.compile("wait")

        self.assertTrue(result.succeeded, result)
        self.assertEqual(result.resolution.definition.canonical_id, "idle_pose")

    def test_malformed_definition_is_rejected(self):
        payload = copy.deepcopy(self.payload)
        del payload["definitions"][0]["generator_id"]
        with self.assertRaises(DefinitionValidationError):
            GestureRegistry.from_payload(payload)

        invalid_default = copy.deepcopy(self.payload)
        invalid_default["definitions"][0]["defaults"]["side"] = "diagonal"
        with self.assertRaises(DefinitionValidationError):
            GestureRegistry.from_payload(invalid_default)

        duplicate_trigger = copy.deepcopy(self.payload)
        idle = next(
            definition
            for definition in duplicate_trigger["definitions"]
            if definition["canonical_id"] == "idle_pose"
        )
        idle["triggers"].append("idle")
        with self.assertRaises(DefinitionValidationError):
            GestureRegistry.from_payload(duplicate_trigger)

    def test_reusable_stage_data_is_validated(self):
        payload = json.loads(STAGES_PATH.read_text())
        payload["sequences"]["talking_idle"][0]["pose"] = "missing"
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory) / "invalid-stages.json"
            temporary.write_text(json.dumps(payload))
            with self.assertRaises(StageValidationError):
                StageLibrary.from_path(temporary)


class ResolverAndSlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(DEFINITIONS_PATH.read_text())
        cls.registry = GestureRegistry.from_payload(cls.payload)
        cls.resolver = GestureResolver(cls.registry)

    def test_typed_slot_extraction(self):
        slots = extract_slots(
            "Slowly wave the left hand outward, hold for 2.5 seconds, then return to neutral"
        )

        self.assertEqual(slots.side, Side.LEFT)
        self.assertEqual(slots.direction, Direction.OUTWARD)
        self.assertEqual(slots.speed, Speed.SLOW)
        self.assertEqual(slots.intensity, Intensity.NORMAL)
        self.assertEqual(slots.hold_seconds, 2.5)
        self.assertEqual(len(slots.sequence), 2)
        self.assertTrue(slots.neutral_return)
        self.assertEqual(
            slots.provided,
            {
                SlotName.SIDE,
                SlotName.DIRECTION,
                SlotName.SPEED,
                SlotName.HOLD,
                SlotName.SEQUENCE,
                SlotName.NEUTRAL_RETURN,
            },
        )

    def test_ambiguity_unknown_and_invalid_slot_results(self):
        ambiguous_payload = copy.deepcopy(self.payload)
        duplicate = copy.deepcopy(
            next(
                definition
                for definition in ambiguous_payload["definitions"]
                if definition["canonical_id"] == "wave"
            )
        )
        duplicate["canonical_id"] = "salute"
        duplicate["aliases"] = ["wave"]
        ambiguous_payload["definitions"].append(duplicate)
        ambiguous = GestureResolver(GestureRegistry.from_payload(ambiguous_payload)).resolve("wave")

        self.assertEqual(ambiguous.status, ResolutionStatus.AMBIGUOUS)
        self.assertEqual(ambiguous.candidates, ("salute", "wave"))
        self.assertEqual(
            self.resolver.resolve("do a cartwheel").status,
            ResolutionStatus.UNSUPPORTED,
        )
        self.assertEqual(
            self.resolver.resolve("wave forward").status,
            ResolutionStatus.INVALID_SLOT,
        )
        self.assertEqual(
            self.resolver.resolve("wave slowly and quickly").status,
            ResolutionStatus.INVALID_SLOT,
        )
        self.assertEqual(
            self.resolver.resolve("wave without returning to neutral").status,
            ResolutionStatus.INVALID_SLOT,
        )

    def test_compound_command_uses_structured_generator(self):
        compiler = GestureCompiler.default()
        result = compiler.compile(
            "raise the left arm then extend the right arm outward then return to neutral"
        )

        self.assertTrue(result.succeeded, result)
        self.assertEqual(
            result.resolution.definition.canonical_id,
            "structured_full_body",
        )
        self.assertEqual(
            tuple(clause.canonical_id for clause in result.resolution.semantic.clauses),
            ("raise_arm", "extend_arm", "neutral_reset"),
        )
        self.assertGreaterEqual(len(result.motion.keyframes), 4)
        metrics = result.validation.metrics_mapping
        self.assertGreater(metrics["left_arm_amplitude_rad"], 0.1)
        self.assertGreater(metrics["right_arm_amplitude_rad"], 0.1)
        self.assertEqual(metrics["final_amplitude_rad"], 0.0)

    def test_recognized_compound_clauses_do_not_require_alias_match(self):
        result = GestureCompiler.default().compile(
            "raise the left arm then extend the right arm outward"
        )

        self.assertTrue(result.succeeded, result)
        self.assertEqual(
            result.resolution.definition.canonical_id,
            "structured_full_body",
        )

    def test_parallel_hand_to_chest_action_is_typed_before_generation(self):
        result = GestureCompiler.default().compile(
            "place the left hand on the chest while extending the right arm outward"
        )

        self.assertTrue(result.succeeded, result)
        self.assertEqual(result.resolution.definition.canonical_id, "hand_to_chest")
        self.assertEqual(
            tuple(clause.canonical_id for clause in result.resolution.semantic.clauses),
            ("hand_to_chest", "extend_arm"),
        )
        active = result.motion.keyframes[1].joints
        self.assertNotEqual(active.get("left_shoulder_pitch_joint"), 0.0)
        self.assertNotEqual(active.get("right_shoulder_pitch_joint"), 0.0)

    def test_presentation_honors_sweep_direction(self):
        compiler = GestureCompiler.default()
        leftward = compiler.compile("welcome the audience with both hands from right to left")
        rightward = compiler.compile("welcome the audience with both hands from left to right")

        self.assertTrue(leftward.succeeded, leftward)
        self.assertTrue(rightward.succeeded, rightward)
        self.assertGreater(
            leftward.motion.keyframes[1].joints.get("waist_yaw_joint"),
            0.0,
        )
        self.assertLess(
            rightward.motion.keyframes[1].joints.get("waist_yaw_joint"),
            0.0,
        )

    def test_two_handed_wave_oscillates_both_arms(self):
        result = GestureCompiler.default().compile("wave with both hands")

        self.assertTrue(result.succeeded, result)
        raised = result.motion.keyframes[1].joints
        oscillated = result.motion.keyframes[2].joints
        left_delta = oscillated.get("left_shoulder_yaw_joint") - raised.get(
            "left_shoulder_yaw_joint"
        )
        right_delta = oscillated.get("right_shoulder_yaw_joint") - raised.get(
            "right_shoulder_yaw_joint"
        )
        self.assertNotEqual(left_delta, 0.0)
        self.assertAlmostEqual(left_delta, -right_delta)

    def test_polite_neutral_reset_alias_is_not_a_modifier(self):
        result = GestureCompiler.default().compile("please return to neutral")

        self.assertTrue(result.succeeded, result)
        self.assertEqual(
            result.resolution.definition.canonical_id,
            "neutral_reset",
        )
        self.assertEqual(result.resolution.slots.provided, frozenset())


class GesturePureImportTests(unittest.TestCase):
    def test_gesture_language_imports_without_qt_or_mujoco(self):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        script = (
            "import sys; "
            "from eric_motion_studio.gestures import GestureCompiler; "
            "result = GestureCompiler.default().compile('wave'); "
            "assert result.succeeded; "
            "assert 'PySide6' not in sys.modules; "
            "assert 'mujoco' not in sys.modules; "
            "print('PURE_GESTURE_IMPORT_OK')"
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
        self.assertEqual(completed.stdout.strip(), "PURE_GESTURE_IMPORT_OK")


if __name__ == "__main__":
    unittest.main()
