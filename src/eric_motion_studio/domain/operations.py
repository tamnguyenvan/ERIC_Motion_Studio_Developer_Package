"""Pure motion editing, interpolation, and trajectory operations."""

from __future__ import annotations

from dataclasses import replace

from eric_motion_studio.domain.values import (
    DEFAULT_FRAME_RATE,
    MAX_KEYFRAME_DURATION_MS,
    MIN_KEYFRAME_DURATION_MS,
    MIN_TRAJECTORY_FRAME_DURATION_MS,
    JointValues,
    Keyframe,
    Motion,
    PlaybackPlan,
    TrajectoryFrame,
)


def clamp(value: float, lower: float, upper: float) -> float:
    if lower > upper:
        raise ValueError("Clamp lower bound must not exceed upper bound")
    return max(lower, min(upper, value))


def smooth_step(value: float) -> float:
    normalized = clamp(value, 0.0, 1.0)
    return normalized * normalized * (3.0 - 2.0 * normalized)


def clone_keyframe(frame: Keyframe) -> Keyframe:
    return Keyframe(
        name=frame.name,
        duration_ms=frame.duration_ms,
        joints=JointValues(tuple(frame.joints.values), frame.joints.profile),
    )


def clone_motion(motion: Motion) -> Motion:
    return replace(
        motion,
        keyframes=tuple(clone_keyframe(frame) for frame in motion.keyframes),
    )


def interpolate_joint_values(
    start: JointValues,
    target: JointValues,
    alpha: float,
) -> JointValues:
    if start.profile != target.profile:
        raise ValueError("Cannot interpolate joint values from different model profiles")
    eased = smooth_step(alpha)
    return JointValues(
        tuple(
            source + (destination - source) * eased
            for source, destination in zip(
                start.values,
                target.values,
                strict=True,
            )
        ),
        start.profile,
    )


def clamp_joint_values(values: JointValues) -> JointValues:
    profile = values.profile
    return JointValues(
        tuple(
            profile.limits[name].clamp(value)
            for name, value in zip(
                profile.joint_names,
                values.values,
                strict=True,
            )
        ),
        profile,
    )


def retime_motion(motion: Motion, factor: float) -> Motion:
    if factor <= 0.0:
        raise ValueError("Retime factor must be positive")
    frames = tuple(
        replace(
            frame,
            duration_ms=int(
                clamp(
                    round(frame.duration_ms * factor),
                    MIN_KEYFRAME_DURATION_MS,
                    MAX_KEYFRAME_DURATION_MS,
                )
            ),
        )
        for frame in motion.keyframes
    )
    return replace(motion, keyframes=frames)


def dense_trajectory(
    keyframes: tuple[Keyframe, ...],
    frame_rate: int = DEFAULT_FRAME_RATE,
) -> PlaybackPlan:
    if not keyframes:
        raise ValueError("Cannot build a trajectory without keyframes")
    if frame_rate <= 0:
        raise ValueError("Frame rate must be positive")

    interval = 1.0 / frame_rate
    timestamp = 0.0
    current = keyframes[0].joints
    trajectory = [TrajectoryFrame(timestamp, current)]
    for target_frame in keyframes[1:]:
        start = current
        steps = max(1, round((target_frame.duration_ms / 1000.0) * frame_rate))
        for step in range(1, steps + 1):
            current = interpolate_joint_values(start, target_frame.joints, step / steps)
            timestamp += interval
            trajectory.append(TrajectoryFrame(round(timestamp, 6), current))

    return PlaybackPlan(tuple(trajectory), frame_rate)


def keyframes_from_trajectory(
    plan: PlaybackPlan,
    *,
    name_prefix: str = "Trajectory frame",
) -> tuple[Keyframe, ...]:
    duration_ms = max(
        MIN_TRAJECTORY_FRAME_DURATION_MS,
        round(1000.0 / plan.frame_rate),
    )
    return tuple(
        Keyframe(
            name=f"{name_prefix} {index}",
            duration_ms=duration_ms,
            joints=frame.joints,
        )
        for index, frame in enumerate(plan.frames, start=1)
    )


def append_keyframe(motion: Motion, frame: Keyframe) -> Motion:
    return replace(motion, keyframes=(*motion.keyframes, clone_keyframe(frame)))


def replace_keyframe(motion: Motion, index: int, frame: Keyframe) -> Motion:
    if not 0 <= index < len(motion.keyframes):
        raise IndexError("Keyframe index out of range")
    frames = list(motion.keyframes)
    frames[index] = clone_keyframe(frame)
    return replace(motion, keyframes=tuple(frames))


def remove_keyframe(motion: Motion, index: int) -> Motion:
    if len(motion.keyframes) == 1:
        raise ValueError("Motion must retain at least one keyframe")
    if not 0 <= index < len(motion.keyframes):
        raise IndexError("Keyframe index out of range")
    return replace(
        motion,
        keyframes=tuple(
            frame for frame_index, frame in enumerate(motion.keyframes) if frame_index != index
        ),
    )
