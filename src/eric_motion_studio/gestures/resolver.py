"""Definition-driven deterministic gesture resolution."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

from eric_motion_studio.config import RESOURCE_ROOT
from eric_motion_studio.gestures.definitions import (
    GestureDefinition,
    GestureRegistry,
)
from eric_motion_studio.gestures.language import (
    GestureLexicon,
    SemanticCommand,
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
    semantic: SemanticCommand | None = None
    candidates: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status is ResolutionStatus.SUCCESS


@dataclass(frozen=True, slots=True)
class _Candidate:
    canonical_id: str
    score: int
    exact: bool
    slots: GestureSlots


class GestureResolver:
    def __init__(
        self,
        registry: GestureRegistry,
        lexicon: GestureLexicon | None = None,
    ) -> None:
        self.registry = registry
        self.lexicon = lexicon or GestureLexicon.from_path(
            RESOURCE_ROOT / "gesture_lexicon" / "builtins.json"
        )

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

        candidates = self._candidates(command, slots)
        exact = tuple(candidate for candidate in candidates if candidate.exact)
        semantic_clauses = self._semantic_clauses(slots.sequence)
        if exact:
            candidates = exact
        elif len(semantic_clauses) >= 2:
            try:
                definition = self.registry.get("structured_full_body")
            except KeyError:
                definition = None
            if definition is not None:
                return self._complete(
                    normalized,
                    definition,
                    slots,
                    SemanticCommand(
                        canonical_id=definition.canonical_id,
                        slots=slots,
                        clauses=semantic_clauses,
                    ),
                )
        else:
            grammar_ids = tuple(
                sorted(
                    {
                        match.canonical_id
                        for match in self.lexicon.match(command, slots)
                        if self._has_definition(match.canonical_id)
                    }
                )
            )
            if len(grammar_ids) > 1:
                return ResolutionResult(
                    status=ResolutionStatus.AMBIGUOUS,
                    normalized_command=normalized,
                    slots=slots,
                    candidates=grammar_ids,
                    message="Command contains multiple gestures without a sequence separator",
                )

        if not candidates:
            suggestions = self._suggestions(command)
            message = "No deterministic grammar or gesture phrase matched the command"
            if suggestions:
                labels = ", ".join(
                    self.registry.get(identifier).aliases[0] for identifier in suggestions
                )
                message = f"{message}. Did you mean: {labels}?"
            return ResolutionResult(
                status=ResolutionStatus.UNSUPPORTED,
                normalized_command=normalized,
                slots=slots,
                suggestions=suggestions,
                message=message,
            )

        best_score = max(candidate.score for candidate in candidates)
        best = tuple(candidate for candidate in candidates if candidate.score == best_score)
        canonical_ids = tuple(sorted({candidate.canonical_id for candidate in best}))
        if len(canonical_ids) > 1:
            return ResolutionResult(
                status=ResolutionStatus.AMBIGUOUS,
                normalized_command=normalized,
                slots=slots,
                candidates=canonical_ids,
                message="Multiple gesture definitions matched equally",
            )

        selected = next(
            candidate for candidate in best if candidate.canonical_id == canonical_ids[0]
        )
        definition = self.registry.get(selected.canonical_id)
        semantic = SemanticCommand(
            canonical_id=definition.canonical_id,
            slots=selected.slots,
            clauses=semantic_clauses,
        )
        return self._complete(normalized, definition, selected.slots, semantic)

    def _has_definition(self, canonical_id: str) -> bool:
        try:
            self.registry.get(canonical_id)
        except KeyError:
            return False
        return True

    def _candidates(
        self,
        command: str,
        slots: GestureSlots,
    ) -> tuple[_Candidate, ...]:
        candidates: dict[tuple[str, bool], _Candidate] = {}
        for definition in self.registry.definitions:
            match = best_phrase_match(
                command,
                (*definition.aliases, *definition.triggers),
            )
            if match is None:
                continue
            score = match.score if match.exact else 6_000 + match.score
            candidate = _Candidate(
                canonical_id=definition.canonical_id,
                score=score,
                exact=match.exact,
                slots=slots,
            )
            candidates[(candidate.canonical_id, candidate.exact)] = candidate
        for match in self.lexicon.match(command, slots):
            try:
                self.registry.get(match.canonical_id)
            except KeyError:
                continue
            candidate = _Candidate(
                canonical_id=match.canonical_id,
                score=match.score,
                exact=False,
                slots=match.slots,
            )
            key = (candidate.canonical_id, False)
            previous = candidates.get(key)
            if previous is None or candidate.score > previous.score:
                candidates[key] = candidate
            elif candidate.slots.provided > previous.slots.provided:
                candidates[key] = _Candidate(
                    canonical_id=previous.canonical_id,
                    score=previous.score,
                    exact=previous.exact,
                    slots=candidate.slots,
                )
        return tuple(candidates.values())

    def _suggestions(self, command: str, *, limit: int = 3) -> tuple[str, ...]:
        normalized = normalize_text(command)
        if not normalized:
            return ()
        command_tokens = frozenset(normalized.split())
        scored: list[tuple[float, str]] = []
        for definition in self.registry.definitions:
            best = 0.0
            for phrase in (*definition.aliases, *definition.triggers):
                normalized_phrase = normalize_text(phrase)
                phrase_tokens = frozenset(normalized_phrase.split())
                character_score = SequenceMatcher(
                    None,
                    normalized,
                    normalized_phrase,
                ).ratio()
                token_score = (
                    len(command_tokens.intersection(phrase_tokens))
                    / len(command_tokens.union(phrase_tokens))
                    if command_tokens and phrase_tokens
                    else 0.0
                )
                best = max(best, character_score, token_score)
            if best >= 0.6:
                scored.append((best, definition.canonical_id))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(identifier for _score, identifier in scored[:limit])

    def _semantic_clauses(
        self,
        sequence: tuple[str, ...],
    ) -> tuple[SemanticCommand, ...]:
        clauses: list[SemanticCommand] = []
        for clause in sequence:
            try:
                slots = extract_slots(clause)
            except SlotExtractionError:
                continue
            candidates = self._candidates(clause, slots)
            if not candidates:
                continue
            best_score = max(candidate.score for candidate in candidates)
            best = tuple(candidate for candidate in candidates if candidate.score == best_score)
            canonical_ids = {candidate.canonical_id for candidate in best}
            if len(canonical_ids) != 1:
                continue
            candidate = best[0]
            clauses.append(
                SemanticCommand(
                    canonical_id=candidate.canonical_id,
                    slots=candidate.slots,
                )
            )
        return tuple(clauses)

    def _complete(
        self,
        normalized: str,
        definition: GestureDefinition,
        slots: GestureSlots,
        semantic: SemanticCommand,
    ) -> ResolutionResult:
        unsupported_slots = slots.provided - definition.supported_slots
        if unsupported_slots:
            names = ", ".join(sorted(slot.value for slot in unsupported_slots))
            return ResolutionResult(
                status=ResolutionStatus.INVALID_SLOT,
                normalized_command=normalized,
                definition=definition,
                slots=slots,
                semantic=semantic,
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
                semantic=semantic,
                candidates=(definition.canonical_id,),
                message=f"Gesture defaults are invalid: {error}",
            )
        resolved_semantic = SemanticCommand(
            canonical_id=semantic.canonical_id,
            slots=resolved_slots,
            clauses=semantic.clauses,
        )
        if definition.constraints.requires_neutral_return and not resolved_slots.neutral_return:
            return ResolutionResult(
                status=ResolutionStatus.INVALID_SLOT,
                normalized_command=normalized,
                definition=definition,
                slots=resolved_slots,
                semantic=resolved_semantic,
                candidates=(definition.canonical_id,),
                message=f"Gesture {definition.canonical_id!r} must return to neutral",
            )
        return ResolutionResult(
            status=ResolutionStatus.SUCCESS,
            normalized_command=normalized,
            definition=definition,
            slots=resolved_slots,
            semantic=resolved_semantic,
            candidates=(definition.canonical_id,),
        )
