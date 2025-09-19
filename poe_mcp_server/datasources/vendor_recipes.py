"""Vendor recipe lookup for common crafting utilities."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence

from .utils import load_json


@dataclass(frozen=True)
class VendorRecipe:
    name: str
    reward: str
    inputs: Sequence[str]
    notes: Sequence[str]
    keywords: Sequence[str]


class _VendorIndex:
    def __init__(self) -> None:
        payload = load_json("crafting_methods.json")
        self._recipes = tuple(
            VendorRecipe(
                name=entry.get("name", ""),
                reward=entry.get("reward", ""),
                inputs=tuple(entry.get("inputs", [])),
                notes=tuple(entry.get("notes", [])),
                keywords=tuple(entry.get("keywords", [])),
            )
            for entry in payload.get("vendor_recipes", [])
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

    def search(self, query: str) -> Sequence[VendorRecipe]:
        needle = self._normalise(query)
        matches = []
        for recipe in self._recipes:
            candidates = [recipe.name, recipe.reward, *recipe.inputs, *recipe.notes, *recipe.keywords]
            if self._matches(candidates, needle):
                matches.append(recipe)
        return tuple(matches)

    @property
    def recipes(self) -> Sequence[VendorRecipe]:
        return self._recipes


_INDEX: _VendorIndex | None = None


def _get_index() -> _VendorIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = _VendorIndex()
    return _INDEX


def load() -> Sequence[VendorRecipe]:
    return _get_index().recipes


def find(query: str) -> Sequence[VendorRecipe]:
    return _get_index().search(query)
