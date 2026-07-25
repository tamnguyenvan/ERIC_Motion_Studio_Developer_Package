"""Pure file-format infrastructure available before runtime adapters."""

from eric_motion_studio.infrastructure.formats import (
    ANIMATION_SCHEMA,
    ANIMATION_VERSION,
    BRAINOS_SCHEMA,
    GESTURE_SCHEMA_VERSION,
    POSE_SCHEMA,
    AnimationRepository,
    AnimationSerializer,
    BrainOSExportRepository,
    BrainOSSerializer,
    GestureRepository,
    GestureSerializer,
    PoseRepository,
    PoseSerializer,
    SchemaValidationError,
)
from eric_motion_studio.infrastructure.migration import (
    MigratedUserFile,
    migrate_legacy_user_files,
)
from eric_motion_studio.infrastructure.motion_library import (
    MotionLibrary,
    MotionLibraryEntry,
    MotionOrigin,
)
from eric_motion_studio.infrastructure.pose_library import (
    PoseLibrary,
    PoseLibraryEntry,
    PoseLibraryError,
    PoseOrigin,
)

__all__ = [
    "ANIMATION_SCHEMA",
    "ANIMATION_VERSION",
    "BRAINOS_SCHEMA",
    "GESTURE_SCHEMA_VERSION",
    "POSE_SCHEMA",
    "AnimationRepository",
    "AnimationSerializer",
    "BrainOSExportRepository",
    "BrainOSSerializer",
    "GestureRepository",
    "MotionLibrary",
    "MotionLibraryEntry",
    "MotionOrigin",
    "MigratedUserFile",
    "GestureSerializer",
    "PoseRepository",
    "PoseSerializer",
    "PoseLibrary",
    "PoseLibraryEntry",
    "PoseLibraryError",
    "PoseOrigin",
    "SchemaValidationError",
    "migrate_legacy_user_files",
]
