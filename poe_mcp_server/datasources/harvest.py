"""Harvest craft metadata loader."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class HarvestCraft:
    identifier: str
    description: Sequence[str]
    groups: Sequence[str]
    tags: Sequence[str]
    item_classes: Sequence[str]


class _HarvestIndex:
    def __init__(self) -> None:
        payload = load_json("harvest_crafts.json")
        self._entries = [HarvestCraft(**entry) for entry in payload]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def search(self, query: str) -> List[HarvestCraft]:
        needle = self._normalise(query)
        matches: List[HarvestCraft] = []
        for craft in self._entries:
            haystack: Iterable[str] = [*craft.description, *craft.groups, *craft.tags]
            if any(needle in self._normalise(candidate) for candidate in haystack):
                matches.append(craft)
        return matches

    @property
    def entries(self) -> Sequence[HarvestCraft]:
        return tuple(self._entries)


_index: _HarvestIndex | None = None


def _get_index() -> _HarvestIndex:
    global _index
    if _index is None:
        _index = _HarvestIndex()
    return _index


def load() -> Sequence[HarvestCraft]:
    return _get_index().entries


def find(query: str) -> Sequence[HarvestCraft]:
    return tuple(_get_index().search(query))
