"""Essence metadata loader."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class Essence:
    identifier: str
    name: str
    tier: str
    level: int
    type: dict[str, object] | str
    mods: Sequence[str]
    item_level_restriction: int | None
    spawn_level_min: int | None
    spawn_level_max: int | None


class _EssenceIndex:
    def __init__(self) -> None:
        payload = load_json("essences.json")
        self._entries = [Essence(**entry) for entry in payload]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def search(self, query: str) -> List[Essence]:
        needle = self._normalise(query)
        matches: List[Essence] = []
        for essence in self._entries:
            candidates: List[str] = [essence.name, *essence.mods]
            if isinstance(essence.type, str):
                candidates.append(essence.type)
            elif isinstance(essence.type, dict):
                candidates.extend(str(value) for value in essence.type.values())
            if any(needle in self._normalise(candidate) for candidate in candidates):
                matches.append(essence)
        return matches

    @property
    def entries(self) -> Sequence[Essence]:
        return tuple(self._entries)


_index: _EssenceIndex | None = None


def _get_index() -> _EssenceIndex:
    global _index
    if _index is None:
        _index = _EssenceIndex()
    return _index


def load() -> Sequence[Essence]:
    return _get_index().entries


def find(query: str) -> Sequence[Essence]:
    return tuple(_get_index().search(query))
