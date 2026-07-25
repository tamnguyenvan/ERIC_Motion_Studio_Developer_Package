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
    "SchemaValidationError",
    "migrate_legacy_user_files",
]
