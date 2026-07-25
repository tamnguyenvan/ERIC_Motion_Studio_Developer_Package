"""Gesture language composition root."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from eric_motion_studio.config import RESOURCE_ROOT
from eric_motion_studio.domain import Motion
from eric_motion_studio.gestures.definitions import GestureRegistry
from eric_motion_studio.gestures.generators import (
    GenerationRequest,
    GeneratorRegistry,
    default_generator_registry,
)
from eric_motion_studio.gestures.language import GestureLexicon
from eric_motion_studio.gestures.resolver import (
    GestureResolver,
    ResolutionResult,
)
from eric_motion_studio.gestures.stages import StageLibrary
from eric_motion_studio.gestures.validators import (
    ValidationReport,
    validate_compiled_motion,
)


@dataclass(frozen=True, slots=True)
class CompilationResult:
    resolution: ResolutionResult
    motion: Motion | None = None
    validation: ValidationReport | None = None
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return (
            self.resolution.succeeded
            and self.motion is not None
            and self.validation is not None
            and self.validation.passed
            and not self.error
        )


class GestureCompiler:
    def __init__(
        self,
        registry: GestureRegistry,
        stages: StageLibrary,
        generators: GeneratorRegistry,
        lexicon: GestureLexicon | None = None,
    ) -> None:
        self.registry = registry
        active_lexicon = lexicon or GestureLexicon.from_path(
            RESOURCE_ROOT / "gesture_lexicon" / "builtins.json"
        )
        active_lexicon.validate_canonical_ids(
            frozenset(definition.canonical_id for definition in registry.definitions)
        )
        self.resolver = GestureResolver(registry, active_lexicon)
        self.stages = stages
        self.generators = generators

    @classmethod
    def default(cls, resource_root: Path = RESOURCE_ROOT) -> GestureCompiler:
        registry = GestureRegistry.from_directory(resource_root / "gesture_definitions")
        lexicon = GestureLexicon.from_path(resource_root / "gesture_lexicon" / "builtins.json")
        stages = StageLibrary.from_path(resource_root / "gesture_stages" / "builtin_stages.json")
        return cls(registry, stages, default_generator_registry(), lexicon)

    def compile(self, command: str) -> CompilationResult:
        logger = logging.getLogger("eric_motion_studio")
        logger.info("motion_prompt_received", extra={"context": {"prompt": command}})
        resolution = self.resolver.resolve(command)
        if not resolution.succeeded:
            logger.warning(
                "motion_parse_failed",
                extra={
                    "context": {
                        "prompt": command,
                        "normalized": resolution.normalized_command,
                        "status": resolution.status.value,
                        "candidates": resolution.candidates,
                        "suggestions": resolution.suggestions,
                        "reason": resolution.message,
                    }
                },
            )
            return CompilationResult(resolution=resolution)
        assert resolution.definition is not None
        assert resolution.slots is not None
        assert resolution.semantic is not None
        try:
            generator = self.generators.get(resolution.definition.generator_id)
            logger.info(
                "motion_template_selected",
                extra={
                    "context": {
                        "canonical_id": resolution.definition.canonical_id,
                        "generator": resolution.definition.generator_id,
                        "slots": repr(resolution.slots),
                    }
                },
            )
            motion = generator.generate(
                GenerationRequest(
                    command=command,
                    definition=resolution.definition,
                    slots=resolution.slots,
                    semantic=resolution.semantic,
                    stages=self.stages,
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            logger.error(
                "motion_generation_failed",
                extra={
                    "context": {
                        "canonical_id": resolution.definition.canonical_id,
                        "reason": str(error),
                    }
                },
            )
            return CompilationResult(
                resolution=resolution,
                error=str(error),
            )
        validation = validate_compiled_motion(
            motion,
            resolution.definition,
            resolution.slots,
        )
        if not validation.passed:
            logger.error(
                "motion_rejected",
                extra={
                    "context": {
                        "canonical_id": resolution.definition.canonical_id,
                        "issues": [issue.code for issue in validation.issues],
                    }
                },
            )
        else:
            logger.info(
                "motion_generation_ok",
                extra={
                    "context": {
                        "canonical_id": resolution.definition.canonical_id,
                        "frames": len(motion.keyframes),
                        "duration_ms": motion.total_duration_ms,
                        "nonzero_joints": sum(
                            any(abs(value) > 1e-6 for value in frame.joints.values)
                            for frame in motion.keyframes
                        ),
                    }
                },
            )
        return CompilationResult(
            resolution=resolution,
            motion=motion,
            validation=validation,
        )
