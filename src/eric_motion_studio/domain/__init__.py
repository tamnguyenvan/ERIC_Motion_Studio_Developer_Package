"""Pure ERIC Motion Studio domain API."""

from eric_motion_studio.domain.model import (
    FULL_BODY_JOINTS,
    UNITREE_G1,
    JointLimit,
    ModelProfile,
)
from eric_motion_studio.domain.operations import (
    append_keyframe,
    clamp,
    clamp_joint_values,
    clone_keyframe,
    clone_motion,
    dense_trajectory,
    interpolate_joint_values,
    keyframes_from_trajectory,
    remove_keyframe,
    replace_keyframe,
    retime_motion,
    smooth_step,
)
from eric_motion_studio.domain.values import (
    Gesture,
    JointValues,
    Keyframe,
    Motion,
    PlaybackPlan,
    PlaybackState,
    Pose,
    TrajectoryFrame,
)

__all__ = [
    "FULL_BODY_JOINTS",
    "UNITREE_G1",
    "Gesture",
    "JointLimit",
    "JointValues",
    "Keyframe",
    "ModelProfile",
    "Motion",
    "PlaybackPlan",
    "PlaybackState",
    "Pose",
    "TrajectoryFrame",
    "append_keyframe",
    "clamp",
    "clamp_joint_values",
    "clone_keyframe",
    "clone_motion",
    "dense_trajectory",
    "interpolate_joint_values",
    "keyframes_from_trajectory",
    "remove_keyframe",
    "replace_keyframe",
    "retime_motion",
    "smooth_step",
]
