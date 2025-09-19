"""Currency metadata loader."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class CurrencyOption:
    name: str
    tags: Sequence[str]
    action: str
    constraints: Sequence[str]


class _CurrencyIndex:
    def __init__(self) -> None:
        payload = load_json("currency.json")
        self._options = [
            CurrencyOption(
                name=entry.get("name", ""),
                tags=tuple(entry.get("tags", [])),
                action=entry.get("action", ""),
                constraints=tuple(entry.get("constraints", [])),
            )
            for entry in payload
        ]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def search(self, query: str) -> List[CurrencyOption]:
        needle_tokens = [token for token in self._normalise(query).split() if token]
        if not needle_tokens:
            return []
        matches: List[CurrencyOption] = []
        for option in self._options:
            haystack: Iterable[str] = [option.name, option.action, *option.tags, *option.constraints]
            for candidate in haystack:
                candidate_tokens = self._normalise(candidate).split()
                if not candidate_tokens:
                    continue
                if all(any(token in candidate_token for candidate_token in candidate_tokens) for token in needle_tokens):
                    matches.append(option)
                    break
        return matches

    @property
    def entries(self) -> Sequence[CurrencyOption]:
        return tuple(self._options)


_index: _CurrencyIndex | None = None


def _get_index() -> _CurrencyIndex:
    global _index
    if _index is None:
        _index = _CurrencyIndex()
    return _index


def load() -> Sequence[CurrencyOption]:
    return _get_index().entries


def find(query: str) -> Sequence[CurrencyOption]:
    return tuple(_get_index().search(query))
