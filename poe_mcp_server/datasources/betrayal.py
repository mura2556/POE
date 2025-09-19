"""Load curated Immortal Syndicate bench crafts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class BetrayalBench:
    owner: str
    division: str
    rank: int
    description: str
    limitations: Sequence[str]


class _BenchIndex:
    def __init__(self) -> None:
        payload = load_json("betrayal_benches.json")
        self._benches = [
            BetrayalBench(
                owner=entry["owner"],
                division=entry["division"],
                rank=int(entry["rank"]),
                description=entry["description"],
                limitations=tuple(entry.get("limitations", [])),
            )
            for entry in payload
        ]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def _haystack(self, bench: BetrayalBench) -> Iterable[str]:
        yield bench.owner
        yield bench.division
        yield bench.description
        for item in bench.limitations:
            yield item
        yield f"rank {bench.rank}"
        yield f"rank{bench.rank}"
        yield "immortal syndicate betrayal bench"

    def search(self, query: str) -> List[BetrayalBench]:
        tokens = self._normalise(query).split()
        if not tokens:
            return []
        matches: List[BetrayalBench] = []
        for bench in self._benches:
            haystack_tokens: set[str] = set()
            for candidate in self._haystack(bench):
                haystack_tokens.update(self._normalise(candidate).split())
            if all(token in haystack_tokens for token in tokens):
                matches.append(bench)
        if matches:
            return matches
        generic_triggers = {"betrayal", "syndicate", "safehouse", "jun"}
        if any(token in generic_triggers for token in tokens):
            top = [bench for bench in self._benches if bench.rank == 3]
            if not top:
                top = self._benches
            return top[:12]
        return []

    @property
    def benches(self) -> Sequence[BetrayalBench]:
        return tuple(self._benches)


_index: _BenchIndex | None = None


def _get_index() -> _BenchIndex:
    global _index
    if _index is None:
        _index = _BenchIndex()
    return _index


def load() -> Sequence[BetrayalBench]:
    return _get_index().benches


def find(query: str) -> Sequence[BetrayalBench]:
    return tuple(_get_index().search(query))
