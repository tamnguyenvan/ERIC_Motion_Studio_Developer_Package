"""Definition-driven gesture resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from eric_motion_studio.gestures.definitions import (
    GestureDefinition,
    GestureRegistry,
)
from eric_motion_studio.gestures.normalization import (
    best_phrase_match,
    normalize_text,
)
from eric_motion_studio.gestures.slots import (
    GestureSlots,
    SlotExtractionError,
    extract_slots,
)


class ResolutionStatus(StrEnum):
    SUCCESS = "success"
    AMBIGUOUS = "ambiguity"
    UNSUPPORTED = "unsupported_gesture"
    INVALID_SLOT = "invalid_slot"


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    status: ResolutionStatus
    normalized_command: str
    definition: GestureDefinition | None = None
    slots: GestureSlots | None = None
    candidates: tuple[str, ...] = ()
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status is ResolutionStatus.SUCCESS


class GestureResolver:
    def __init__(self, registry: GestureRegistry) -> None:
        self.registry = registry

    def resolve(self, command: str) -> ResolutionResult:
        normalized = normalize_text(command)
        if not normalized:
            return ResolutionResult(
                status=ResolutionStatus.UNSUPPORTED,
                normalized_command=normalized,
                message="Command is empty",
            )
        try:
            slots = extract_slots(command)
        except SlotExtractionError as error:
            return ResolutionResult(
                status=ResolutionStatus.INVALID_SLOT,
                normalized_command=normalized,
                message=str(error),
            )

        matches = []
        for definition in self.registry.definitions:
            match = best_phrase_match(command, definition.aliases)
            if match is not None:
                matches.append((definition, match))

        exact_matches = [
            (definition, match)
            for definition, match in matches
            if match.exact
        ]
        if exact_matches:
            matches = exact_matches
        elif _has_multiple_movement_clauses(slots.sequence):
            try:
                structured = self.registry.get("structured_full_body")
            except KeyError:
                structured = None
            if structured is not None:
                structured_match = best_phrase_match(
                    "structured full body motion",
                    structured.aliases,
                )
                matches = [(structured, structured_match)]

        if not matches:
            return ResolutionResult(
                status=ResolutionStatus.UNSUPPORTED,
                normalized_command=normalized,
                slots=slots,
                message="No gesture definition matched the command",
            )

        best_score = max(match.score for _, match in matches if match is not None)
        candidates = tuple(
            definition
            for definition, match in matches
            if match is not None and match.score == best_score
        )
        if len(candidates) > 1:
            return ResolutionResult(
                status=ResolutionStatus.AMBIGUOUS,
                normalized_command=normalized,
                slots=slots,
                candidates=tuple(
                    sorted(definition.canonical_id for definition in candidates)
                ),
                message="Multiple gesture definitions matched equally",
            )

        definition = candidates[0]
        unsupported_slots = slots.provided - definition.supported_slots
        if unsupported_slots:
            names = ", ".join(sorted(slot.value for slot in unsupported_slots))
            return ResolutionResult(
                status=ResolutionStatus.INVALID_SLOT,
                normalized_command=normalized,
                definition=definition,
                slots=slots,
                candidates=(definition.canonical_id,),
                message=f"Gesture {definition.canonical_id!r} does not support: {names}",
            )
        try:
            resolved_slots = slots.with_defaults(definition.defaults_mapping)
        except (TypeError, ValueError) as error:
            return ResolutionResult(
                status=ResolutionStatus.INVALID_SLOT,
                normalized_command=normalized,
                definition=definition,
                slots=slots,
                candidates=(definition.canonical_id,),
                message=f"Gesture defaults are invalid: {error}",
            )
        if (
            definition.constraints.requires_neutral_return
            and not resolved_slots.neutral_return
        ):
            return ResolutionResult(
                status=ResolutionStatus.INVALID_SLOT,
                normalized_command=normalized,
                definition=definition,
                slots=resolved_slots,
                candidates=(definition.canonical_id,),
                message=f"Gesture {definition.canonical_id!r} must return to neutral",
            )
        return ResolutionResult(
            status=ResolutionStatus.SUCCESS,
            normalized_command=normalized,
            definition=definition,
            slots=resolved_slots,
            candidates=(definition.canonical_id,),
        )


def _has_multiple_movement_clauses(sequence: tuple[str, ...]) -> bool:
    movement_terms = {
        "raise",
        "lift",
        "lower",
        "extend",
        "open",
        "wave",
        "sweep",
        "rotate",
        "turn",
        "scratch",
        "rub",
        "place",
        "bend",
    }
    return (
        sum(
            bool(set(clause.split()).intersection(movement_terms))
            for clause in sequence
        )
        >= 2
    )
