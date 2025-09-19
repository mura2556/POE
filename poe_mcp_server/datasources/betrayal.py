"""Immortal Syndicate crafting bench metadata loader."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class BetrayalBench:
    member: str
    division: str
    rank: int
    description: str
    limitations: Sequence[str]


class _BetrayalIndex:
    def __init__(self) -> None:
        payload = load_json("betrayal_benches.json")
        self._benches = [
            BetrayalBench(
                member=entry.get("member", ""),
                division=entry.get("division", ""),
                rank=int(entry.get("rank", 0)),
                description=entry.get("description", ""),
                limitations=tuple(entry.get("limitations", [])),
            )
            for entry in payload
        ]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def search(self, query: str) -> List[BetrayalBench]:
        needle = self._normalise(query)
        if not needle:
            return []
        matches: List[BetrayalBench] = []
        for bench in self._benches:
            haystack: Iterable[str] = [
                bench.member,
                bench.division,
                f"{bench.member} {bench.division}",
                f"rank {bench.rank}",
                bench.description,
                *bench.limitations,
            ]
            if any(needle in self._normalise(candidate) for candidate in haystack if candidate):
                matches.append(bench)
        return matches

    @property
    def benches(self) -> Sequence[BetrayalBench]:
        return tuple(self._benches)


_index: _BetrayalIndex | None = None


def _get_index() -> _BetrayalIndex:
    global _index
    if _index is None:
        _index = _BetrayalIndex()
    return _index


def load() -> Sequence[BetrayalBench]:
    return _get_index().benches


def find(query: str) -> Sequence[BetrayalBench]:
    return tuple(_get_index().search(query))

