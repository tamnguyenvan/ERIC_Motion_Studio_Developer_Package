"""Validated data-driven gesture definitions."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from eric_motion_studio.gestures.normalization import normalize_text
from eric_motion_studio.gestures.slots import (
    Direction,
    Intensity,
    Side,
    SlotName,
    Speed,
)

DEFINITION_SCHEMA_VERSION = 1
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


class DefinitionValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GestureConstraints:
    min_amplitude_rad: float
    max_duration_seconds: float
    requires_neutral_return: bool
    balance_required: bool
    collision_check: bool

    @classmethod
    def from_payload(cls, raw_payload: object) -> GestureConstraints:
        if not isinstance(raw_payload, Mapping):
            raise DefinitionValidationError("constraints must be an object")
        required = {
            "min_amplitude_rad",
            "max_duration_seconds",
            "requires_neutral_return",
            "balance_required",
            "collision_check",
        }
        missing = required - set(raw_payload)
        if missing:
            raise DefinitionValidationError(
                f"constraints missing fields: {', '.join(sorted(missing))}"
            )
        try:
            minimum = float(raw_payload["min_amplitude_rad"])
            maximum_duration = float(raw_payload["max_duration_seconds"])
        except (TypeError, ValueError) as error:
            raise DefinitionValidationError("constraint numeric fields must be numbers") from error
        if (
            not math.isfinite(minimum)
            or minimum < 0.0
            or not math.isfinite(maximum_duration)
            or maximum_duration <= 0.0
        ):
            raise DefinitionValidationError("constraint numeric fields are invalid")
        boolean_values = {
            name: raw_payload[name]
            for name in (
                "requires_neutral_return",
                "balance_required",
                "collision_check",
            )
        }
        if any(not isinstance(value, bool) for value in boolean_values.values()):
            raise DefinitionValidationError("constraint boolean fields must be booleans")
        return cls(
            min_amplitude_rad=minimum,
            max_duration_seconds=maximum_duration,
            requires_neutral_return=boolean_values["requires_neutral_return"],
            balance_required=boolean_values["balance_required"],
            collision_check=boolean_values["collision_check"],
        )


@dataclass(frozen=True, slots=True)
class GestureDefinition:
    canonical_id: str
    aliases: tuple[str, ...]
    supported_slots: frozenset[SlotName]
    generator_id: str
    defaults: tuple[tuple[str, object], ...]
    tags: tuple[str, ...]
    constraints: GestureConstraints

    @classmethod
    def from_payload(cls, raw_payload: object) -> GestureDefinition:
        if not isinstance(raw_payload, Mapping):
            raise DefinitionValidationError("gesture definition must be an object")
        canonical_id = raw_payload.get("canonical_id")
        generator_id = raw_payload.get("generator_id")
        if not isinstance(canonical_id, str) or not _IDENTIFIER.fullmatch(canonical_id):
            raise DefinitionValidationError("canonical_id is invalid")
        if not isinstance(generator_id, str) or not _IDENTIFIER.fullmatch(generator_id):
            raise DefinitionValidationError("generator_id is invalid")

        raw_aliases = raw_payload.get("aliases")
        if (
            not isinstance(raw_aliases, list)
            or not raw_aliases
            or any(not isinstance(alias, str) or not alias.strip() for alias in raw_aliases)
        ):
            raise DefinitionValidationError("aliases must be non-empty strings")
        normalized_aliases = [normalize_text(alias) for alias in raw_aliases]
        if len(set(normalized_aliases)) != len(normalized_aliases):
            raise DefinitionValidationError(
                f"definition {canonical_id!r} contains duplicate aliases"
            )

        raw_slots = raw_payload.get("supported_slots")
        if not isinstance(raw_slots, list):
            raise DefinitionValidationError("supported_slots must be an array")
        try:
            slots = frozenset(SlotName(slot) for slot in raw_slots)
        except (TypeError, ValueError) as error:
            raise DefinitionValidationError("supported_slots contains an invalid slot") from error
        if len(slots) != len(raw_slots):
            raise DefinitionValidationError("supported_slots contains duplicates")

        raw_defaults = raw_payload.get("defaults")
        if not isinstance(raw_defaults, Mapping):
            raise DefinitionValidationError("defaults must be an object")
        unknown_defaults = set(raw_defaults) - {slot.value for slot in slots}
        if unknown_defaults:
            raise DefinitionValidationError(
                f"defaults use unsupported slots: {', '.join(sorted(unknown_defaults))}"
            )
        _validate_defaults(raw_defaults)

        raw_tags = raw_payload.get("tags")
        if not isinstance(raw_tags, list) or any(
            not isinstance(tag, str) or not tag.strip() for tag in raw_tags
        ):
            raise DefinitionValidationError("tags must contain non-empty strings")

        return cls(
            canonical_id=canonical_id,
            aliases=tuple(raw_aliases),
            supported_slots=slots,
            generator_id=generator_id,
            defaults=tuple(raw_defaults.items()),
            tags=tuple(raw_tags),
            constraints=GestureConstraints.from_payload(raw_payload.get("constraints")),
        )

    @property
    def defaults_mapping(self) -> dict[str, object]:
        return dict(self.defaults)


def _validate_defaults(defaults: Mapping[str, object]) -> None:
    enum_fields = {
        "side": Side,
        "direction": Direction,
        "speed": Speed,
        "intensity": Intensity,
    }
    for name, enum_type in enum_fields.items():
        if name in defaults:
            try:
                enum_type(str(defaults[name]))
            except ValueError as error:
                raise DefinitionValidationError(f"default {name!r} is invalid") from error
    if "hold" in defaults:
        try:
            hold = float(defaults["hold"])
        except (TypeError, ValueError) as error:
            raise DefinitionValidationError("default hold is invalid") from error
        if not 0.0 <= hold <= 10.0:
            raise DefinitionValidationError("default hold is outside 0..10 seconds")
    if "neutral_return" in defaults and not isinstance(
        defaults["neutral_return"],
        bool,
    ):
        raise DefinitionValidationError("default neutral_return must be boolean")


class GestureRegistry:
    def __init__(self, definitions: tuple[GestureDefinition, ...]) -> None:
        if not definitions:
            raise DefinitionValidationError("gesture registry must not be empty")
        identifiers = [definition.canonical_id for definition in definitions]
        if len(set(identifiers)) != len(identifiers):
            raise DefinitionValidationError("canonical gesture IDs must be unique")
        self._definitions = definitions
        self._by_id = {definition.canonical_id: definition for definition in definitions}

    @classmethod
    def from_payload(cls, raw_payload: object) -> GestureRegistry:
        if not isinstance(raw_payload, Mapping):
            raise DefinitionValidationError("definition registry must be an object")
        if raw_payload.get("schema_version") != DEFINITION_SCHEMA_VERSION:
            raise DefinitionValidationError(
                f"definition schema_version must be {DEFINITION_SCHEMA_VERSION}"
            )
        raw_definitions = raw_payload.get("definitions")
        if not isinstance(raw_definitions, list) or not raw_definitions:
            raise DefinitionValidationError("definitions must be a non-empty array")
        return cls(
            tuple(GestureDefinition.from_payload(definition) for definition in raw_definitions)
        )

    @classmethod
    def from_directory(cls, directory: Path) -> GestureRegistry:
        definitions: list[GestureDefinition] = []
        paths = sorted(directory.glob("*.json"))
        if not paths:
            raise DefinitionValidationError(f"No gesture definitions found in {directory}")
        for path in paths:
            try:
                payload = json.loads(path.read_text())
            except json.JSONDecodeError as error:
                raise DefinitionValidationError(f"{path} contains invalid JSON: {error}") from error
            registry = cls.from_payload(payload)
            definitions.extend(registry.definitions)
        return cls(tuple(definitions))

    @property
    def definitions(self) -> tuple[GestureDefinition, ...]:
        return self._definitions

    def get(self, canonical_id: str) -> GestureDefinition:
        try:
            return self._by_id[canonical_id]
        except KeyError as error:
            raise KeyError(f"Unknown canonical gesture: {canonical_id}") from error
