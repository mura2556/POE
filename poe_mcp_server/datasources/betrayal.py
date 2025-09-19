"""Betrayal safehouse bench utilities."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence

from .utils import load_json


@dataclass(frozen=True)
class BetrayalBench:
    member: str
    division: str
    rank: int
    ability: str
    summary: str
    requirements: Sequence[str]
    keywords: Sequence[str]


class _BetrayalIndex:
    def __init__(self) -> None:
        payload = load_json("crafting_methods.json")
        self._benches = tuple(
            BetrayalBench(
                member=entry.get("member", ""),
                division=entry.get("division", ""),
                rank=int(entry.get("rank", 0)),
                ability=entry.get("ability", ""),
                summary=entry.get("summary", ""),
                requirements=tuple(entry.get("requirements", [])),
                keywords=tuple(entry.get("keywords", [])),
            )
            for entry in payload.get("betrayal_benches", [])
        )

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def _matches(self, candidates: Iterable[str], needle: str) -> bool:
        for candidate in candidates:
            if needle in self._normalise(candidate):
                return True
        return False

    def search(self, query: str) -> Sequence[BetrayalBench]:
        needle = self._normalise(query)
        matches = []
        for bench in self._benches:
            candidates = [
                bench.member,
                bench.division,
                bench.ability,
                bench.summary,
                *bench.requirements,
                *bench.keywords,
                str(bench.rank),
            ]
            if self._matches(candidates, needle):
                matches.append(bench)
        return tuple(matches)

    @property
    def benches(self) -> Sequence[BetrayalBench]:
        return self._benches


_INDEX: _BetrayalIndex | None = None


def _get_index() -> _BetrayalIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = _BetrayalIndex()
    return _INDEX


def load() -> Sequence[BetrayalBench]:
    return _get_index().benches


def find(query: str) -> Sequence[BetrayalBench]:
    return _get_index().search(query)
