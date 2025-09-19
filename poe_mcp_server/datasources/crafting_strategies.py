"""General crafting strategy guidance."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence

from .utils import load_json


@dataclass(frozen=True)
class CraftingStrategy:
    name: str
    summary: str
    best_for: Sequence[str]
    requirements: Sequence[str]
    steps: Sequence[str]
    keywords: Sequence[str]


class _StrategyIndex:
    def __init__(self) -> None:
        payload = load_json("crafting_methods.json")
        self._strategies = tuple(
            CraftingStrategy(
                name=entry.get("name", ""),
                summary=entry.get("summary", ""),
                best_for=tuple(entry.get("best_for", [])),
                requirements=tuple(entry.get("requirements", [])),
                steps=tuple(entry.get("steps", [])),
                keywords=tuple(entry.get("keywords", [])),
            )
            for entry in payload.get("strategies", [])
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

    def search(self, query: str) -> Sequence[CraftingStrategy]:
        needle = self._normalise(query)
        matches = []
        for strategy in self._strategies:
            candidates = [
                strategy.name,
                strategy.summary,
                *strategy.best_for,
                *strategy.requirements,
                *strategy.steps,
                *strategy.keywords,
            ]
            if self._matches(candidates, needle):
                matches.append(strategy)
        return tuple(matches)

    @property
    def strategies(self) -> Sequence[CraftingStrategy]:
        return self._strategies


_INDEX: _StrategyIndex | None = None


def _get_index() -> _StrategyIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = _StrategyIndex()
    return _INDEX


def load() -> Sequence[CraftingStrategy]:
    return _get_index().strategies


def find(query: str) -> Sequence[CraftingStrategy]:
    return _get_index().search(query)
