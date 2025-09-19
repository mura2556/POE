"""Load curated crafting bench recipes."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class BenchCost:
    currency: str
    amount: int


@dataclass(frozen=True)
class BenchRecipe:
    identifier: str
    display: str
    description: str
    bench_tier: int
    master: str
    item_classes: Sequence[str]
    action: str
    keywords: Sequence[str]
    costs: Sequence[BenchCost]


class _BenchIndex:
    def __init__(self) -> None:
        payload = load_json("bench_recipes.json")
        self._recipes = [
            BenchRecipe(
                identifier=entry["identifier"],
                display=entry["display"],
                description=entry["description"],
                bench_tier=entry["bench_tier"],
                master=entry["master"],
                item_classes=tuple(entry.get("item_classes", [])),
                action=entry["action"],
                keywords=tuple(entry.get("keywords", [])),
                costs=tuple(BenchCost(**cost) for cost in entry.get("costs", [])),
            )
            for entry in payload
        ]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def search(self, query: str) -> List[BenchRecipe]:
        needle = self._normalise(query)
        matches: List[BenchRecipe] = []
        for recipe in self._recipes:
            haystack: Iterable[str] = [recipe.display, recipe.description, *recipe.keywords]
            if any(needle in self._normalise(candidate) for candidate in haystack):
                matches.append(recipe)
        return matches

    @property
    def recipes(self) -> Sequence[BenchRecipe]:
        return tuple(self._recipes)


_index: _BenchIndex | None = None


def _get_index() -> _BenchIndex:
    global _index
    if _index is None:
        _index = _BenchIndex()
    return _index


def load() -> Sequence[BenchRecipe]:
    return _get_index().recipes


def find(query: str) -> Sequence[BenchRecipe]:
    return tuple(_get_index().search(query))
