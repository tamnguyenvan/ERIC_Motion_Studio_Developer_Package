"""Isolated command normalization and phrase matching."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_NON_WORD = re.compile(r"[^a-z0-9]+")
_SPACE = re.compile(r"\s+")
_IGNORABLE_TOKENS = frozenset(
    {
        "a",
        "an",
        "can",
        "could",
        "kindly",
        "me",
        "my",
        "please",
        "the",
        "would",
        "you",
        "your",
    }
)


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.casefold().replace("&", " and ")
    return _SPACE.sub(" ", _NON_WORD.sub(" ", lowered)).strip()


def tokenize(value: str) -> tuple[str, ...]:
    normalized = normalize_text(value)
    return tuple(normalized.split()) if normalized else ()


def contains_phrase(command: str, phrase: str) -> bool:
    command_tokens = tokenize(command)
    phrase_tokens = tokenize(phrase)
    if not phrase_tokens or len(phrase_tokens) > len(command_tokens):
        return False
    width = len(phrase_tokens)
    return any(
        command_tokens[index : index + width] == phrase_tokens
        for index in range(len(command_tokens) - width + 1)
    )


def _content_tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in tokenize(value) if token not in _IGNORABLE_TOKENS)


@dataclass(frozen=True, slots=True)
class PhraseMatch:
    alias: str
    score: int
    exact: bool


def best_phrase_match(command: str, aliases: tuple[str, ...]) -> PhraseMatch | None:
    normalized_command = normalize_text(command)
    command_tokens = tokenize(command)
    matches: list[PhraseMatch] = []
    for alias in aliases:
        normalized_alias = normalize_text(alias)
        if normalized_alias == normalized_command:
            matches.append(
                PhraseMatch(alias=alias, score=10_000 + len(tokenize(alias)), exact=True)
            )
        elif contains_phrase(command, alias):
            phrase_tokens = tokenize(alias)
            width = len(phrase_tokens)
            position = next(
                index
                for index in range(len(command_tokens) - width + 1)
                if command_tokens[index : index + width] == phrase_tokens
            )
            matches.append(
                PhraseMatch(
                    alias=alias,
                    score=len(phrase_tokens) * 100 - position,
                    exact=False,
                )
            )
        else:
            content_command = _content_tokens(command)
            content_alias = _content_tokens(alias)
            if not content_alias or len(content_alias) > len(content_command):
                continue
            width = len(content_alias)
            positions = [
                index
                for index in range(len(content_command) - width + 1)
                if content_command[index : index + width] == content_alias
            ]
            if positions:
                matches.append(
                    PhraseMatch(
                        alias=alias,
                        score=width * 100 - positions[0],
                        exact=False,
                    )
                )
    return max(matches, key=lambda match: match.score, default=None)
