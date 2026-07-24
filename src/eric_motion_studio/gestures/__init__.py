"""Data-driven gesture language API."""

from eric_motion_studio.gestures.compiler import CompilationResult, GestureCompiler
from eric_motion_studio.gestures.definitions import (
    DefinitionValidationError,
    GestureConstraints,
    GestureDefinition,
    GestureRegistry,
)
from eric_motion_studio.gestures.generators import (
    GenerationRequest,
    GeneratorRegistry,
    GestureGenerator,
)
from eric_motion_studio.gestures.normalization import (
    best_phrase_match,
    contains_phrase,
    normalize_text,
    tokenize,
)
from eric_motion_studio.gestures.resolver import (
    GestureResolver,
    ResolutionResult,
    ResolutionStatus,
)
from eric_motion_studio.gestures.slots import (
    Direction,
    GestureSlots,
    Intensity,
    Side,
    SlotName,
    Speed,
    extract_slots,
)
from eric_motion_studio.gestures.validators import (
    ValidationIssue,
    ValidationReport,
)

__all__ = [
    "CompilationResult",
    "DefinitionValidationError",
    "Direction",
    "GenerationRequest",
    "GeneratorRegistry",
    "GestureCompiler",
    "GestureConstraints",
    "GestureDefinition",
    "GestureGenerator",
    "GestureRegistry",
    "GestureResolver",
    "GestureSlots",
    "Intensity",
    "ResolutionResult",
    "ResolutionStatus",
    "Side",
    "SlotName",
    "Speed",
    "ValidationIssue",
    "ValidationReport",
    "best_phrase_match",
    "contains_phrase",
    "extract_slots",
    "normalize_text",
    "tokenize",
]
