"""Deterministic intent grammar and typed semantic command model."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from eric_motion_studio.gestures.normalization import normalize_text, tokenize
from eric_motion_studio.gestures.slots import (
    Direction,
    GestureSlots,
    Side,
    SlotName,
)

LEXICON_SCHEMA_VERSION = 1
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class LexiconValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GrammarRule:
    canonical_id: str
    actions: frozenset[str]
    effectors: frozenset[str]
    effector_optional: bool = False


@dataclass(frozen=True, slots=True)
class LanguageMatch:
    canonical_id: str
    score: int
    slots: GestureSlots


@dataclass(frozen=True, slots=True)
class SemanticCommand:
    canonical_id: str
    slots: GestureSlots
    clauses: tuple[SemanticCommand, ...] = ()


class GestureLexicon:
    def __init__(
        self,
        actions: Mapping[str, tuple[str, ...]],
        effectors: Mapping[str, tuple[str, ...]],
        rules: tuple[GrammarRule, ...],
    ) -> None:
        self.actions = dict(actions)
        self.effectors = dict(effectors)
        self.rules = rules

    def validate_canonical_ids(self, canonical_ids: frozenset[str]) -> None:
        unknown = {
            rule.canonical_id for rule in self.rules if rule.canonical_id not in canonical_ids
        }
        if unknown:
            raise LexiconValidationError(
                f"lexicon rules reference unknown gestures: {', '.join(sorted(unknown))}"
            )

    @classmethod
    def from_path(cls, path: Path) -> GestureLexicon:
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            raise LexiconValidationError(f"{path} contains invalid JSON: {error}") from error
        return cls.from_payload(payload)

    @classmethod
    def from_payload(cls, raw_payload: object) -> GestureLexicon:
        if not isinstance(raw_payload, Mapping):
            raise LexiconValidationError("gesture lexicon must be an object")
        if raw_payload.get("schema_version") != LEXICON_SCHEMA_VERSION:
            raise LexiconValidationError(f"lexicon schema_version must be {LEXICON_SCHEMA_VERSION}")
        actions = _term_groups(raw_payload.get("actions"), "actions")
        effectors = _term_groups(raw_payload.get("effectors"), "effectors")
        raw_rules = raw_payload.get("rules")
        if not isinstance(raw_rules, list) or not raw_rules:
            raise LexiconValidationError("rules must be a non-empty array")
        rules = tuple(_rule_from_payload(rule, actions, effectors) for rule in raw_rules)
        return cls(actions, effectors, rules)

    def match(self, command: str, slots: GestureSlots) -> tuple[LanguageMatch, ...]:
        command_tokens = tokenize(command)
        action_matches = _matching_groups(command_tokens, self.actions)
        effector_matches = _matching_groups(command_tokens, self.effectors)
        matches: dict[str, LanguageMatch] = {}
        for rule in self.rules:
            matched_actions = rule.actions.intersection(action_matches)
            matched_effectors = rule.effectors.intersection(effector_matches)
            if not matched_actions:
                continue
            if rule.effectors and not matched_effectors and not rule.effector_optional:
                continue
            resolved_slots = _enrich_slots(rule.canonical_id, command_tokens, slots)
            score = 5_000 + max(
                len(tokenize(alias))
                for action in matched_actions
                for alias in self.actions[action]
                if _contains_tokens(command_tokens, tokenize(alias))
            )
            if matched_effectors:
                score += 10 + max(
                    len(tokenize(alias))
                    for effector in matched_effectors
                    for alias in self.effectors[effector]
                    if _contains_tokens(command_tokens, tokenize(alias))
                )
            match = LanguageMatch(rule.canonical_id, score, resolved_slots)
            previous = matches.get(rule.canonical_id)
            if previous is None or match.score > previous.score:
                matches[rule.canonical_id] = match
        return tuple(matches.values())


def _term_groups(raw_groups: object, field: str) -> dict[str, tuple[str, ...]]:
    if not isinstance(raw_groups, Mapping) or not raw_groups:
        raise LexiconValidationError(f"{field} must be a non-empty object")
    groups: dict[str, tuple[str, ...]] = {}
    normalized_terms: dict[str, str] = {}
    for identifier, raw_terms in raw_groups.items():
        if not isinstance(identifier, str) or not _IDENTIFIER.fullmatch(identifier):
            raise LexiconValidationError(f"{field} contains an invalid identifier")
        if (
            not isinstance(raw_terms, list)
            or not raw_terms
            or any(not isinstance(term, str) or not normalize_text(term) for term in raw_terms)
        ):
            raise LexiconValidationError(f"{field}.{identifier} must contain phrases")
        terms = tuple(normalize_text(term) for term in raw_terms)
        if len(set(terms)) != len(terms):
            raise LexiconValidationError(f"{field}.{identifier} contains duplicate phrases")
        for term in terms:
            previous = normalized_terms.get(term)
            if previous is not None and previous != identifier:
                raise LexiconValidationError(
                    f"{field} phrase {term!r} belongs to both {previous!r} and {identifier!r}"
                )
            normalized_terms[term] = identifier
        groups[identifier] = terms
    return groups


def _rule_from_payload(
    raw_rule: object,
    actions: Mapping[str, tuple[str, ...]],
    effectors: Mapping[str, tuple[str, ...]],
) -> GrammarRule:
    if not isinstance(raw_rule, Mapping):
        raise LexiconValidationError("rules must contain objects")
    canonical_id = raw_rule.get("canonical_id")
    raw_actions = raw_rule.get("actions")
    raw_effectors = raw_rule.get("effectors", [])
    effector_optional = raw_rule.get("effector_optional", False)
    if not isinstance(canonical_id, str) or not _IDENTIFIER.fullmatch(canonical_id):
        raise LexiconValidationError("rule canonical_id is invalid")
    if (
        not isinstance(raw_actions, list)
        or not raw_actions
        or any(not isinstance(action, str) or action not in actions for action in raw_actions)
    ):
        raise LexiconValidationError(f"rule {canonical_id!r} contains invalid actions")
    if not isinstance(raw_effectors, list) or any(
        not isinstance(effector, str) or effector not in effectors for effector in raw_effectors
    ):
        raise LexiconValidationError(f"rule {canonical_id!r} contains invalid effectors")
    if not isinstance(effector_optional, bool):
        raise LexiconValidationError(f"rule {canonical_id!r} effector_optional must be boolean")
    return GrammarRule(
        canonical_id=canonical_id,
        actions=frozenset(raw_actions),
        effectors=frozenset(raw_effectors),
        effector_optional=effector_optional,
    )


def _matching_groups(
    command_tokens: tuple[str, ...],
    groups: Mapping[str, tuple[str, ...]],
) -> frozenset[str]:
    return frozenset(
        identifier
        for identifier, aliases in groups.items()
        if any(_contains_tokens(command_tokens, tokenize(alias)) for alias in aliases)
    )


def _contains_tokens(command: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    if not phrase or len(phrase) > len(command):
        return False
    width = len(phrase)
    return any(
        command[index : index + width] == phrase for index in range(len(command) - width + 1)
    )


def _enrich_slots(
    canonical_id: str,
    command_tokens: tuple[str, ...],
    slots: GestureSlots,
) -> GestureSlots:
    if canonical_id != "point" or slots.side is not None:
        return slots
    has_left = "left" in command_tokens
    has_right = "right" in command_tokens
    if has_left == has_right:
        return slots
    side = Side.LEFT if has_left else Side.RIGHT
    direction = Direction.LEFT if has_left else Direction.RIGHT
    return replace(
        slots,
        side=side,
        direction=direction,
        provided=slots.provided | {SlotName.SIDE, SlotName.DIRECTION},
    )
