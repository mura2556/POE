"""Beastcraft recipe metadata loader."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class BestiaryRequirement:
    component_id: str
    name: str
    amount: int
    group: str | None
    family: str | None
    genus: str | None
    rarity: str | None
    min_level: int | None
    mod_id: str | None


@dataclass(frozen=True)
class BestiaryRecipe:
    identifier: str
    category: str
    outcome: str
    notes: str | None
    game_mode: str
    beasts: Sequence[BestiaryRequirement]


class _BestiaryIndex:
    def __init__(self) -> None:
        payload = load_json("bestiary_recipes.json")
        self._recipes = [
            BestiaryRecipe(
                identifier=entry["identifier"],
                category=entry.get("category", ""),
                outcome=entry.get("outcome", ""),
                notes=entry.get("notes"),
                game_mode=entry.get("game_mode", "default"),
                beasts=tuple(
                    BestiaryRequirement(
                        component_id=beast["component_id"],
                        name=beast.get("name", beast["component_id"]),
                        amount=int(beast.get("amount", 1)),
                        group=beast.get("group"),
                        family=beast.get("family"),
                        genus=beast.get("genus"),
                        rarity=beast.get("rarity"),
                        min_level=beast.get("min_level"),
                        mod_id=beast.get("mod_id"),
                    )
                    for beast in entry.get("beasts", [])
                ),
            )
            for entry in payload
        ]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def search(self, query: str) -> List[BestiaryRecipe]:
        needle = self._normalise(query)
        if not needle:
            return []
        matches: List[BestiaryRecipe] = []
        for recipe in self._recipes:
            haystack: List[str] = [
                recipe.identifier,
                recipe.category,
                recipe.outcome,
                recipe.game_mode,
            ]
            if recipe.notes:
                haystack.append(recipe.notes)
            for beast in recipe.beasts:
                haystack.extend(
                    value
                    for value in (
                        beast.name,
                        beast.component_id,
                        beast.group,
                        beast.family,
                        beast.genus,
                        beast.rarity,
                    )
                    if value
                )
            if any(needle in self._normalise(candidate) for candidate in haystack if candidate):
                matches.append(recipe)
        return matches

    @property
    def recipes(self) -> Sequence[BestiaryRecipe]:
        return tuple(self._recipes)


_index: _BestiaryIndex | None = None


def _get_index() -> _BestiaryIndex:
    global _index
    if _index is None:
        _index = _BestiaryIndex()
    return _index


def load() -> Sequence[BestiaryRecipe]:
    return _get_index().recipes


def find(query: str) -> Sequence[BestiaryRecipe]:
    return tuple(_get_index().search(query))
