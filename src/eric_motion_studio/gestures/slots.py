"""Typed gesture slot extraction."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum

from eric_motion_studio.gestures.normalization import normalize_text


class SlotName(StrEnum):
    SIDE = "side"
    DIRECTION = "direction"
    SPEED = "speed"
    INTENSITY = "intensity"
    HOLD = "hold"
    SEQUENCE = "sequence"
    NEUTRAL_RETURN = "neutral_return"


class Side(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"


class Direction(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"
    FORWARD = "forward"
    OUTWARD = "outward"
    INWARD = "inward"


class Speed(StrEnum):
    SLOW = "slow"
    NORMAL = "normal"
    FAST = "fast"


class Intensity(StrEnum):
    SUBTLE = "subtle"
    NORMAL = "normal"
    STRONG = "strong"


class SlotExtractionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GestureSlots:
    side: Side | None = None
    direction: Direction | None = None
    speed: Speed = Speed.NORMAL
    intensity: Intensity = Intensity.NORMAL
    hold_seconds: float = 0.0
    sequence: tuple[str, ...] = ()
    neutral_return: bool = True
    provided: frozenset[SlotName] = frozenset()

    def with_defaults(self, defaults: Mapping[str, object]) -> GestureSlots:
        values: dict[str, object] = {}
        if SlotName.SIDE not in self.provided and defaults.get("side") is not None:
            values["side"] = Side(str(defaults["side"]))
        if SlotName.DIRECTION not in self.provided and defaults.get("direction") is not None:
            values["direction"] = Direction(str(defaults["direction"]))
        if SlotName.SPEED not in self.provided and defaults.get("speed") is not None:
            values["speed"] = Speed(str(defaults["speed"]))
        if SlotName.INTENSITY not in self.provided and defaults.get("intensity") is not None:
            values["intensity"] = Intensity(str(defaults["intensity"]))
        if SlotName.HOLD not in self.provided and defaults.get("hold") is not None:
            values["hold_seconds"] = float(defaults["hold"])
        if (
            SlotName.NEUTRAL_RETURN not in self.provided
            and defaults.get("neutral_return") is not None
        ):
            values["neutral_return"] = bool(defaults["neutral_return"])
        return replace(self, **values)


_HOLD_PATTERN = re.compile(
    r"\b(?:hold|pause)(?:\s+(?:for))?\s+(\d+(?:\.\d+)?)\s*(seconds?|secs?|s)\b"
)
_SEQUENCE_SPLIT = re.compile(r"\s*(?:(?<!\d)[.;](?!\d)|\bthen\b|\bwhile\b)\s*")
_NEUTRAL_RESET_COMMAND = re.compile(
    r"(?:(?:please|kindly)\s+)?"
    r"(?:(?:can|could|would)\s+you\s+)?"
    r"(?:return to neutral|neutral)"
    r"(?:\s+please)?"
)


def _extract_sequence(command: str) -> tuple[str, ...]:
    parts = tuple(
        normalized
        for part in _SEQUENCE_SPLIT.split(command)
        if (normalized := normalize_text(part))
    )
    return parts if len(parts) > 1 else ()


def extract_slots(command: str) -> GestureSlots:
    text = normalize_text(command)
    provided: set[SlotName] = set()

    slow = any(word in text.split() for word in ("slow", "slowly", "gentle"))
    fast = any(word in text.split() for word in ("fast", "quick", "quickly", "rapid"))
    if slow and fast:
        raise SlotExtractionError("Command contains conflicting speed modifiers")
    speed = Speed.SLOW if slow else Speed.FAST if fast else Speed.NORMAL
    if slow or fast:
        provided.add(SlotName.SPEED)

    subtle = any(word in text.split() for word in ("subtle", "small", "slight"))
    strong = any(word in text.split() for word in ("strong", "strongly", "firmly", "wide"))
    if subtle and strong:
        raise SlotExtractionError("Command contains conflicting intensity modifiers")
    intensity = Intensity.SUBTLE if subtle else Intensity.STRONG if strong else Intensity.NORMAL
    if subtle or strong:
        provided.add(SlotName.INTENSITY)

    side: Side | None = None
    if re.search(r"\bleft (?:hand|arm)\b.*\b(?:on|to) (?:the )?chest\b", text):
        side = Side.LEFT
    elif re.search(
        r"\bright (?:hand|arm)\b.*\b(?:on|to) "
        r"(?:the )?(?:centre of the )?chest\b",
        text,
    ):
        side = Side.RIGHT
    elif re.search(r"\bboth (?:hands|arms)\b", text):
        side = Side.BOTH
    else:
        has_left = bool(re.search(r"\bleft (?:hand|arm)\b", text))
        has_right = bool(re.search(r"\bright (?:hand|arm)\b", text))
        if has_left and has_right:
            side = Side.BOTH
        elif has_left:
            side = Side.LEFT
        elif has_right:
            side = Side.RIGHT
    if side is not None:
        provided.add(SlotName.SIDE)

    direction: Direction | None = None
    if (
        "left to right" in text
        or "toward the right" in text
        or re.search(r"\bfrom\b.*\bleft\b.*\bto\b.*\bright\b", text)
    ):
        direction = Direction.RIGHT
    elif (
        "right to left" in text
        or "toward the left" in text
        or re.search(r"\bfrom\b.*\bright\b.*\bto\b.*\bleft\b", text)
    ):
        direction = Direction.LEFT
    else:
        direction_terms = {
            Direction.UP: ("up", "upward"),
            Direction.DOWN: ("down", "downward"),
            Direction.FORWARD: ("forward", "ahead"),
            Direction.OUTWARD: ("outward", "outwards"),
            Direction.INWARD: ("inward", "inwards"),
        }
        words = set(text.split())
        matches = [
            candidate for candidate, terms in direction_terms.items() if words.intersection(terms)
        ]
        if len(matches) > 1:
            raise SlotExtractionError("Command contains conflicting directions")
        if matches:
            direction = matches[0]
    if direction is not None:
        provided.add(SlotName.DIRECTION)

    hold_seconds = 0.0
    if hold_match := _HOLD_PATTERN.search(command.casefold()):
        hold_seconds = float(hold_match.group(1))
        if not 0.0 <= hold_seconds <= 10.0:
            raise SlotExtractionError("Hold duration must be between 0 and 10 seconds")
        provided.add(SlotName.HOLD)
    elif "pause" in text.split():
        hold_seconds = 0.5
        provided.add(SlotName.HOLD)

    sequence = _extract_sequence(command)
    if sequence:
        provided.add(SlotName.SEQUENCE)

    neutral_return = True
    if re.search(r"\b(?:do not|dont|without) return(?:ing)? to neutral\b", text):
        neutral_return = False
        provided.add(SlotName.NEUTRAL_RETURN)
    elif "return to neutral" in text and _NEUTRAL_RESET_COMMAND.fullmatch(text) is None:
        provided.add(SlotName.NEUTRAL_RETURN)

    return GestureSlots(
        side=side,
        direction=direction,
        speed=speed,
        intensity=intensity,
        hold_seconds=hold_seconds,
        sequence=sequence,
        neutral_return=neutral_return,
        provided=frozenset(provided),
    )
