"""Focused ERIC Motion Studio widgets."""

from eric_motion_studio.ui.widgets.gesture_library import GestureLibraryWidget
from eric_motion_studio.ui.widgets.joint_editor import JointEditorWidget
from eric_motion_studio.ui.widgets.keyframe_editor import KeyframeEditorWidget
from eric_motion_studio.ui.widgets.motion_metadata import MotionMetadataWidget
from eric_motion_studio.ui.widgets.playback_controls import PlaybackControlsWidget
from eric_motion_studio.ui.widgets.status_panel import StatusPanel

__all__ = [
    "GestureLibraryWidget",
    "JointEditorWidget",
    "KeyframeEditorWidget",
    "MotionMetadataWidget",
    "PlaybackControlsWidget",
    "StatusPanel",
]
