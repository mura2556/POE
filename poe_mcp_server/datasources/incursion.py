from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class IncursionCraft:
    room: str
    room_id: str
    tier: int
    effect: str
    item_classes: Sequence[str]
    notes: Sequence[str]
    aliases: Sequence[str]


class _IncursionIndex:
    def __init__(self) -> None:
        payload = load_json("incursion_crafts.json")
        self._entries = [IncursionCraft(**entry) for entry in payload]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def search(self, query: str) -> List[IncursionCraft]:
        needle = self._normalise(query)
        if not needle:
            return []
        matches: List[IncursionCraft] = []
        for craft in self._entries:
            candidates: Iterable[str] = [
                craft.room,
                craft.room_id,
                craft.effect,
                *craft.item_classes,
                *craft.notes,
                *craft.aliases,
            ]
            for candidate in candidates:
                haystack = self._normalise(candidate)
                if haystack and (needle in haystack or haystack in needle):
                    matches.append(craft)
                    break
        return matches

    @property
    def entries(self) -> Sequence[IncursionCraft]:
        return tuple(self._entries)


_index: _IncursionIndex | None = None


def _get_index() -> _IncursionIndex:
    global _index
    if _index is None:
        _index = _IncursionIndex()
    return _index


def load() -> Sequence[IncursionCraft]:
    return _get_index().entries


def find(query: str) -> Sequence[IncursionCraft]:
    return tuple(_get_index().search(query))
