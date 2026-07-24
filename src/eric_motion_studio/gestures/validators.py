"""Post-compilation gesture validation pipeline."""

from __future__ import annotations

import math
from dataclasses import dataclass

from eric_motion_studio.domain import Motion, UNITREE_G1, dense_trajectory
from eric_motion_studio.gestures.definitions import GestureDefinition
from eric_motion_studio.gestures.slots import GestureSlots, Side


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]
    metrics: tuple[tuple[str, float], ...]

    @property
    def passed(self) -> bool:
        return not self.issues

    @property
    def metrics_mapping(self) -> dict[str, float]:
        return dict(self.metrics)


def validate_compiled_motion(
    motion: Motion,
    definition: GestureDefinition,
    slots: GestureSlots,
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    metrics: dict[str, float] = {}

    _validate_joint_limits(motion, issues)
    _validate_amplitude(motion, definition, issues, metrics)
    _validate_trajectory(motion, definition, issues, metrics)
    if definition.constraints.balance_required:
        _validate_balance(motion, issues, metrics)
    if definition.constraints.collision_check:
        _validate_collision(motion, issues)
    _validate_semantics(motion, definition, slots, issues, metrics)

    return ValidationReport(
        issues=tuple(issues),
        metrics=tuple(sorted(metrics.items())),
    )


def _validate_joint_limits(
    motion: Motion,
    issues: list[ValidationIssue],
) -> None:
    for frame_index, frame in enumerate(motion.keyframes):
        for name, value in frame.joints.to_mapping().items():
            limit = UNITREE_G1.limits[name]
            if not limit.lower <= value <= limit.upper:
                issues.append(
                    ValidationIssue(
                        "joint_limit",
                        f"Frame {frame_index} exceeds {name} limits",
                    )
                )


def _validate_amplitude(
    motion: Motion,
    definition: GestureDefinition,
    issues: list[ValidationIssue],
    metrics: dict[str, float],
) -> None:
    amplitude = max(
        abs(value)
        for frame in motion.keyframes
        for value in frame.joints.values
    )
    metrics["max_amplitude_rad"] = amplitude
    if amplitude + 1e-9 < definition.constraints.min_amplitude_rad:
        issues.append(
            ValidationIssue(
                "insufficient_amplitude",
                f"Amplitude {amplitude:.3f} is below the gesture minimum",
            )
        )


def _validate_trajectory(
    motion: Motion,
    definition: GestureDefinition,
    issues: list[ValidationIssue],
    metrics: dict[str, float],
) -> None:
    try:
        plan = dense_trajectory(motion.keyframes)
    except (TypeError, ValueError) as error:
        issues.append(ValidationIssue("trajectory", str(error)))
        return
    duration = plan.duration_seconds
    metrics["trajectory_duration_seconds"] = duration
    metrics["trajectory_frame_count"] = float(len(plan.frames))
    if not all(
        math.isfinite(value)
        for frame in plan.frames
        for value in frame.joints.values
    ):
        issues.append(
            ValidationIssue("trajectory", "Trajectory contains non-finite values")
        )
    if duration > definition.constraints.max_duration_seconds:
        issues.append(
            ValidationIssue(
                "trajectory_duration",
                f"Trajectory duration {duration:.3f}s exceeds the maximum",
            )
        )


def _validate_balance(
    motion: Motion,
    issues: list[ValidationIssue],
    metrics: dict[str, float],
) -> None:
    leg_names = UNITREE_G1.groups["legs"]
    max_leg_offset = max(
        abs(frame.joints.get(name))
        for frame in motion.keyframes
        for name in leg_names
    )
    max_waist_roll = max(
        abs(frame.joints.get("waist_roll_joint"))
        for frame in motion.keyframes
    )
    metrics["max_leg_offset_rad"] = max_leg_offset
    metrics["max_waist_roll_rad"] = max_waist_roll
    if max_leg_offset > 0.28 or max_waist_roll > 0.10:
        issues.append(
            ValidationIssue(
                "balance",
                "Generated lower-body or waist-roll offsets are unstable",
            )
        )


def _validate_collision(
    motion: Motion,
    issues: list[ValidationIssue],
) -> None:
    for frame in motion.keyframes:
        left_roll = frame.joints.get("left_shoulder_roll_joint")
        right_roll = frame.joints.get("right_shoulder_roll_joint")
        if left_roll < -0.12 and right_roll > 0.12:
            issues.append(
                ValidationIssue(
                    "collision",
                    "Both arms cross inward through the torso",
                )
            )
            return


def _group_amplitude(motion: Motion, group: str) -> float:
    return max(
        abs(frame.joints.get(name))
        for frame in motion.keyframes
        for name in UNITREE_G1.groups[group]
    )


def _validate_semantics(
    motion: Motion,
    definition: GestureDefinition,
    slots: GestureSlots,
    issues: list[ValidationIssue],
    metrics: dict[str, float],
) -> None:
    left_amplitude = _group_amplitude(motion, "left_arm")
    right_amplitude = _group_amplitude(motion, "right_arm")
    metrics["left_arm_amplitude_rad"] = left_amplitude
    metrics["right_arm_amplitude_rad"] = right_amplitude
    if slots.side is Side.LEFT and left_amplitude + 1e-9 < right_amplitude:
        issues.append(
            ValidationIssue(
                "semantic_side",
                "Right-arm motion exceeds the requested left-arm motion",
            )
        )
    if slots.side is Side.RIGHT and right_amplitude + 1e-9 < left_amplitude:
        issues.append(
            ValidationIssue(
                "semantic_side",
                "Left-arm motion exceeds the requested right-arm motion",
            )
        )
    if slots.side is Side.BOTH and min(left_amplitude, right_amplitude) < 0.05:
        issues.append(
            ValidationIssue(
                "semantic_side",
                "Both-arm gesture does not visibly move both arms",
            )
        )

    if definition.constraints.requires_neutral_return:
        final_amplitude = max(abs(value) for value in motion.keyframes[-1].joints.values)
        metrics["final_amplitude_rad"] = final_amplitude
        if final_amplitude > 1e-9:
            issues.append(
                ValidationIssue(
                    "neutral_return",
                    "Gesture does not return exactly to neutral",
                )
            )
