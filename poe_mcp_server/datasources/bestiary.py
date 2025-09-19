"""Beastcraft recipe metadata loader."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class BeastRequirement:
    component_id: str
    amount: int
    display: str
    monster: str | None
    family: str | None
    genus: str | None
    beast_group: str | None
    rarity: str | None


@dataclass(frozen=True)
class BeastcraftRecipe:
    identifier: str
    header: str
    subheader: str | None
    notes: str | None
    game_mode: str
    display: str
    keywords: Sequence[str]
    requirements: Sequence[BeastRequirement]


class _BestiaryIndex:
    def __init__(self) -> None:
        payload = load_json("bestiary_recipes.json")
        self._recipes = [
            BeastcraftRecipe(
                identifier=entry["identifier"],
                header=entry.get("header", ""),
                subheader=entry.get("subheader"),
                notes=entry.get("notes"),
                game_mode=entry.get("game_mode", "standard"),
                display=entry.get("display", entry.get("header", "")),
                keywords=tuple(entry.get("keywords", [])),
                requirements=tuple(
                    BeastRequirement(
                        component_id=requirement.get("component_id", ""),
                        amount=max(1, int(requirement.get("amount", 0) or 0)),
                        display=requirement.get("display", ""),
                        monster=requirement.get("monster"),
                        family=requirement.get("family"),
                        genus=requirement.get("genus"),
                        beast_group=requirement.get("beast_group"),
                        rarity=requirement.get("rarity"),
                    )
                    for requirement in entry.get("requirements", [])
                ),
            )
            for entry in payload
            if entry.get("identifier")
        ]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def search(self, query: str) -> List[BeastcraftRecipe]:
        needle = self._normalise(query)
        matches: List[BeastcraftRecipe] = []
        for recipe in self._recipes:
            haystack: List[str] = [
                recipe.display,
                recipe.header,
                recipe.game_mode,
                *recipe.keywords,
            ]
            if recipe.subheader:
                haystack.append(recipe.subheader)
            if recipe.notes:
                haystack.append(recipe.notes)
            for requirement in recipe.requirements:
                haystack.extend(
                    [
                        requirement.display,
                        requirement.component_id,
                        requirement.monster or "",
                        requirement.family or "",
                        requirement.genus or "",
                        requirement.beast_group or "",
                        requirement.rarity or "",
                    ]
                )
            if any(needle in self._normalise(candidate) for candidate in haystack if candidate):
                matches.append(recipe)
        matches.sort(key=lambda recipe: (0 if recipe.game_mode == "standard" else 1, recipe.display))
        return matches

    @property
    def recipes(self) -> Sequence[BeastcraftRecipe]:
        return tuple(self._recipes)


_index: _BestiaryIndex | None = None


def _get_index() -> _BestiaryIndex:
    global _index
    if _index is None:
        _index = _BestiaryIndex()
    return _index


def load() -> Sequence[BeastcraftRecipe]:
    return _get_index().recipes


def find(query: str) -> Sequence[BeastcraftRecipe]:
    return tuple(_get_index().search(query))
