"""Bestiary crafting data sourced from the curated dataset."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence

from .utils import load_json


@dataclass(frozen=True)
class BeastRequirement:
    id: str
    name: str
    rarity: str | None
    family: str | None
    genus: str | None
    group: str | None
    quantity: int


@dataclass(frozen=True)
class Beastcraft:
    id: str
    header: str
    result: str
    notes: Sequence[str]
    game_mode: str
    beasts: Sequence[BeastRequirement]
    keywords: Sequence[str]


class _BeastcraftIndex:
    def __init__(self) -> None:
        payload = load_json("crafting_methods.json")
        self._crafts = tuple(
            Beastcraft(
                id=entry["id"],
                header=entry.get("header", ""),
                result=entry.get("result", ""),
                notes=tuple(entry.get("notes", [])),
                game_mode=entry.get("game_mode", "Any"),
                beasts=tuple(
                    BeastRequirement(
                        id=beast.get("id", ""),
                        name=beast.get("name", ""),
                        rarity=beast.get("rarity"),
                        family=beast.get("family"),
                        genus=beast.get("genus"),
                        group=beast.get("group"),
                        quantity=int(beast.get("quantity", 1)),
                    )
                    for beast in entry.get("beasts", [])
                ),
                keywords=tuple(entry.get("keywords", [])),
            )
            for entry in payload.get("beastcrafts", [])
        )

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def _matches(self, haystack: Iterable[str], needle: str) -> bool:
        for candidate in haystack:
            if needle in self._normalise(candidate):
                return True
        return False

    def search(self, query: str) -> Sequence[Beastcraft]:
        needle = self._normalise(query)
        matches = []
        for craft in self._crafts:
            beast_names = [beast.name for beast in craft.beasts if beast.name]
            candidates = [
                craft.header,
                craft.result,
                craft.game_mode,
                *craft.notes,
                *craft.keywords,
                *beast_names,
            ]
            if self._matches(candidates, needle):
                matches.append(craft)
        return tuple(matches)

    @property
    def crafts(self) -> Sequence[Beastcraft]:
        return self._crafts


_INDEX: _BeastcraftIndex | None = None


def _get_index() -> _BeastcraftIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = _BeastcraftIndex()
    return _INDEX


def load() -> Sequence[Beastcraft]:
    return _get_index().crafts


def find(query: str) -> Sequence[Beastcraft]:
    return _get_index().search(query)
