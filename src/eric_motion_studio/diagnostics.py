"""Cutover diagnostics for the active package."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TextIO

from eric_motion_studio.config import Settings
from eric_motion_studio.domain import Gesture, dense_trajectory
from eric_motion_studio.gestures import GestureCompiler
from eric_motion_studio.infrastructure import (
    AnimationRepository,
    BrainOSExportRepository,
    GestureRepository,
    PoseLibrary,
)
from eric_motion_studio.runtime import MujocoAdapter, ViewerStateStore
from eric_motion_studio.ui.controllers import PlaybackController
from eric_motion_studio.ui.services import NullPlaybackOutput


def _write(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")


def _motions_equivalent(left, right, *, tolerance: float = 1e-6) -> bool:
    if (
        left.name != right.name
        or left.loop != right.loop
        or left.description != right.description
        or left.simulation_only != right.simulation_only
        or left.model_ref != right.model_ref
        or left.created_at != right.created_at
        or left.updated_at != right.updated_at
        or left.metadata != right.metadata
        or len(left.keyframes) != len(right.keyframes)
    ):
        return False
    return all(
        left_frame.name == right_frame.name
        and left_frame.duration_ms == right_frame.duration_ms
        and all(
            abs(left_value - right_value) <= tolerance
            for left_value, right_value in zip(
                left_frame.joints.values,
                right_frame.joints.values,
                strict=True,
            )
        )
        for left_frame, right_frame in zip(
            left.keyframes,
            right.keyframes,
            strict=True,
        )
    )


def audit_command(
    prompt: str,
    *,
    compiler: GestureCompiler | None = None,
    stream: TextIO,
) -> bool:
    active_compiler = compiler or GestureCompiler.default()
    result = active_compiler.compile(prompt)
    definition = result.resolution.definition
    action = definition.canonical_id if definition is not None else "none"
    status = "PASS" if result.succeeded else "FAIL"
    _write(
        stream,
        f"COMMAND_AUDIT_PHRASE_RESULT prompt={prompt} action={action} status={status}",
    )
    if not result.succeeded:
        detail = result.error or result.resolution.message or "validation failed"
        _write(stream, f"COMMAND_AUDIT_ERROR prompt={prompt} detail={detail}")
    return result.succeeded


def audit_all_commands(*, stream: TextIO) -> bool:
    compiler = GestureCompiler.default()
    prompts = tuple(
        command
        for definition in compiler.registry.definitions
        for command in (*definition.aliases, *definition.triggers)
    )
    results = tuple(audit_command(prompt, compiler=compiler, stream=stream) for prompt in prompts)
    passed = all(results)
    status = "PASS" if passed else "FAIL"
    _write(
        stream,
        f"ALL_COMMANDS_AUDITED total={len(prompts)} status={status}",
    )
    return passed


def audit_all_gestures_in_mujoco(
    settings: Settings,
    *,
    stream: TextIO,
) -> bool:
    """Compile every gesture and apply its dense trajectory to the MuJoCo model."""
    compiler = GestureCompiler.default(settings.resource_root)
    adapter = MujocoAdapter(settings.model_path)
    all_passed = True
    applied_frames = 0
    for definition in compiler.registry.definitions:
        prompt = definition.aliases[0]
        result = compiler.compile(prompt)
        if not result.succeeded or result.motion is None:
            _write(
                stream,
                f"MUJOCO_GESTURE_AUDIT_RESULT action={definition.canonical_id} "
                "frames=0 status=FAIL reason=compilation",
            )
            all_passed = False
            continue
        trajectory = dense_trajectory(result.motion.keyframes)
        try:
            for sequence, frame in enumerate(trajectory.frames, start=1):
                adapter.apply_pose(frame.joints, sequence=sequence)
        except Exception as error:
            _write(
                stream,
                f"MUJOCO_GESTURE_AUDIT_RESULT action={definition.canonical_id} "
                f"frames={len(trajectory.frames)} status=FAIL reason={error}",
            )
            all_passed = False
            continue
        applied_frames += len(trajectory.frames)
        _write(
            stream,
            f"MUJOCO_GESTURE_AUDIT_RESULT action={definition.canonical_id} "
            f"frames={len(trajectory.frames)} status=PASS",
        )
    status = "PASS" if all_passed else "FAIL"
    _write(
        stream,
        "MUJOCO_ALL_GESTURES_AUDITED "
        f"gestures={len(compiler.registry.definitions)} "
        f"frames={applied_frames} status={status}",
    )
    return all_passed


def run_self_test(settings: Settings, *, stream: TextIO) -> bool:
    resource_root = settings.resource_root
    required_paths = (
        settings.model_path,
        resource_root / "models" / "g1" / "g1_29dof.xml",
        resource_root / "gesture_definitions" / "builtins.json",
        resource_root / "gesture_lexicon" / "builtins.json",
        resource_root / "gesture_stages" / "builtin_stages.json",
        resource_root / "pose_definitions" / "builtins.json",
        resource_root / "schemas" / "animation-v1.schema.json",
        resource_root / "schemas" / "brainos-motion-v1.schema.json",
        resource_root / "schemas" / "gesture-v1.schema.json",
        resource_root / "schemas" / "gesture-lexicon-v1.schema.json",
        resource_root / "schemas" / "pose-library-v1.schema.json",
    )
    missing = [path for path in required_paths if not path.is_file()]
    if missing:
        _write(
            stream,
            "RESOURCE_LAYOUT_TEST_FAILED "
            f"missing={','.join(str(path) for path in missing) or 'none'}",
        )
        return False
    _write(
        stream,
        "RESOURCE_LAYOUT_TEST_OK canonical_sources=definitions,lexicon,stages,poses",
    )

    pose_library = PoseLibrary(
        settings.poses_dir,
        resource_root / "pose_definitions" / "builtins.json",
        resource_root / "gesture_stages" / "builtin_stages.json",
    )
    pose_matches = pose_library.search("thoughtful hand on chin")
    if not pose_matches or pose_matches[0].entry_id != "builtin:thinking_chin":
        _write(stream, "POSE_LIBRARY_REGRESSION_FAILED")
        return False
    _write(
        stream,
        f"POSE_LIBRARY_REGRESSION_OK builtins={len(pose_library.entries())}",
    )

    compiler = GestureCompiler.default(resource_root)
    compilation = compiler.compile("wave with your right hand")
    if not compilation.succeeded or compilation.motion is None:
        _write(stream, "AUTHORING_REGRESSION_FAILED")
        return False
    motion = compilation.motion
    _write(stream, "AUTHORING_REGRESSION_OK action=wave")

    output = NullPlaybackOutput()
    playback = PlaybackController(output)
    playback.set_motion(motion)
    if not playback.play():
        _write(stream, "PLAYBACK_REGRESSION_FAILED")
        return False
    playback.advance(motion.total_duration_ms / 1000.0)
    if not playback.stop() or output.last_frame is not None:
        _write(stream, "PLAYBACK_REGRESSION_FAILED")
        return False
    _write(stream, "PLAYBACK_REGRESSION_OK")

    animations = AnimationRepository()
    gestures = GestureRepository()
    trajectory = dense_trajectory(motion.keyframes)
    artifact = Gesture(
        gesture_id="self_test_wave",
        display_name=motion.name,
        source_prompt="wave with your right hand",
        frames=trajectory.frames,
        frame_rate=trajectory.frame_rate,
    )

    with tempfile.TemporaryDirectory(prefix="eric-motion-studio-cutover-") as directory:
        root = Path(directory)
        animation_path = root / "saved-animation.json"
        gesture_path = root / "saved-gesture.json"
        export_path = root / "export.brainos-motion.json"
        state_path = root / "live-pose.json"

        animations.save(animation_path, motion)
        if not _motions_equivalent(animations.load(animation_path), motion):
            _write(stream, "FILE_COMPATIBILITY_REGRESSION_FAILED animation")
            return False
        gestures.save(gesture_path, artifact)
        if gestures.load(gesture_path) != artifact:
            _write(stream, "FILE_COMPATIBILITY_REGRESSION_FAILED gesture")
            return False
        _write(
            stream,
            "FILE_COMPATIBILITY_REGRESSION_OK motions=1 compiled_gestures=1",
        )

        exports = BrainOSExportRepository()
        exports.save(export_path, motion)
        if not _motions_equivalent(exports.load(export_path), motion):
            _write(stream, "EXPORT_REGRESSION_FAILED")
            return False
        _write(stream, "EXPORT_REGRESSION_OK")

        frame = dense_trajectory(motion.keyframes).frames[1]
        state_store = ViewerStateStore(state_path)
        written = state_store.write(frame.joints)
        read = state_store.read(max_age_seconds=5.0)
        adapter = MujocoAdapter(settings.model_path)
        applied = adapter.apply_pose(read.joints, sequence=read.sequence)
        synchronized = (
            written.sequence == read.sequence
            and written.updated_at == read.updated_at
            and all(
                abs(left - right) <= 1e-6
                for left, right in zip(
                    written.joints.values,
                    read.joints.values,
                    strict=True,
                )
            )
            and applied.sequence == written.sequence
        )
        if not synchronized:
            _write(stream, "VIEWER_SYNCHRONIZATION_REGRESSION_FAILED")
            return False
        _write(
            stream,
            f"VIEWER_SYNCHRONIZATION_REGRESSION_OK sequence={written.sequence}",
        )

    if not audit_all_commands(stream=stream):
        return False
    _write(stream, "SELF_TEST_OK")
    return True
