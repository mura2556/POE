"""Curated access to atlas boss metadata."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class BossEncounter:
    """High level encounter such as Sirus or The Maven."""

    name: str
    aliases: Sequence[str]
    encounter: str
    unlock: Sequence[str]
    notes: Sequence[str]


@dataclass(frozen=True)
class MapBoss:
    """Standard atlas map boss information."""

    map: str
    tier: int
    bosses: Sequence[str]
    unlock: Sequence[str]


class _BossIndex:
    def __init__(self) -> None:
        payload = load_json("bosses.json")
        self._atlas_bosses = [BossEncounter(**entry) for entry in payload.get("atlas_bosses", [])]
        self._map_bosses = [MapBoss(**entry) for entry in payload.get("map_bosses", [])]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def _contains(self, haystack: Iterable[str], needle: str) -> bool:
        needle_norm = self._normalise(needle)
        for candidate in haystack:
            if needle_norm in self._normalise(candidate):
                return True
        return False

    def find_atlas_bosses(self, query: str) -> List[BossEncounter]:
        return [boss for boss in self._atlas_bosses if self._contains([boss.name, *boss.aliases], query)]

    def find_map_bosses(self, query: str) -> List[MapBoss]:
        matches: List[MapBoss] = []
        for boss in self._map_bosses:
            haystack = [boss.map, *boss.bosses]
            if self._contains(haystack, query):
                matches.append(boss)
        return matches

    @property
    def atlas_bosses(self) -> Sequence[BossEncounter]:
        return tuple(self._atlas_bosses)

    @property
    def map_bosses(self) -> Sequence[MapBoss]:
        return tuple(self._map_bosses)


_index: _BossIndex | None = None


def _get_index() -> _BossIndex:
    global _index
    if _index is None:
        _index = _BossIndex()
    return _index


def load_atlas_bosses() -> Sequence[BossEncounter]:
    """Return all high level boss encounters."""
    return _get_index().atlas_bosses


def load_map_bosses() -> Sequence[MapBoss]:
    """Return all atlas map bosses."""
    return _get_index().map_bosses


def search(query: str) -> dict[str, Sequence[BossEncounter | MapBoss]]:
    """Search both encounter lists for :data:`query`."""

    index = _get_index()
    return {
        "atlas_bosses": index.find_atlas_bosses(query),
        "map_bosses": index.find_map_bosses(query),
    }
