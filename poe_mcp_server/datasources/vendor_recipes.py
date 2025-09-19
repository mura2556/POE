"""Load vendor and combination recipe data."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class VendorRecipePart:
    part_id: int | None
    item_name: str
    item_page: str | None
    item_id: str | None
    amount: int | None
    notes: str | None


@dataclass(frozen=True)
class VendorRecipe:
    page: str
    recipe_id: int
    result_amount: int | None
    description: str | None
    automatic: bool
    parts: Sequence[VendorRecipePart]


class _VendorIndex:
    def __init__(self) -> None:
        payload = load_json("vendor_recipes.json")
        self._recipes: List[VendorRecipe] = []
        for entry in payload:
            page = entry.get("page", "")
            recipe_id = entry.get("recipe_id")
            parts_payload = entry.get("parts", [])
            parts = [
                VendorRecipePart(
                    part_id=part.get("part_id"),
                    item_name=part.get("item_name", ""),
                    item_page=part.get("item_page"),
                    item_id=part.get("item_id"),
                    amount=part.get("amount"),
                    notes=part.get("notes"),
                )
                for part in parts_payload
                if part.get("item_name") or part.get("item_page") or part.get("item_id")
            ]
            if not page or not parts or recipe_id is None:
                continue
            recipe = VendorRecipe(
                page=page,
                recipe_id=int(recipe_id),
                result_amount=entry.get("result_amount"),
                description=entry.get("description"),
                automatic=bool(entry.get("automatic", False)),
                parts=tuple(parts),
            )
            self._recipes.append(recipe)
        self._recipes.sort(key=lambda recipe: (recipe.page.lower(), recipe.recipe_id))

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def search(self, query: str) -> List[VendorRecipe]:
        words = self._normalise(query).split()
        if not words:
            return []
        matches: List[VendorRecipe] = []
        for recipe in self._recipes:
            tokens: List[str] = []
            tokens.append(self._normalise(recipe.page))
            if recipe.description:
                tokens.append(self._normalise(recipe.description))
            for part in recipe.parts:
                if part.item_name:
                    tokens.append(self._normalise(part.item_name))
                if part.item_page:
                    tokens.append(self._normalise(part.item_page))
                if part.notes:
                    tokens.append(self._normalise(part.notes))
            if not tokens:
                continue
            if all(any(word in token for token in tokens if token) for word in words):
                matches.append(recipe)
        return matches

    @property
    def recipes(self) -> Sequence[VendorRecipe]:
        return tuple(self._recipes)


_index: _VendorIndex | None = None


def _get_index() -> _VendorIndex:
    global _index
    if _index is None:
        _index = _VendorIndex()
    return _index


def load() -> Sequence[VendorRecipe]:
    return _get_index().recipes


def find(query: str) -> Sequence[VendorRecipe]:
    return tuple(_get_index().search(query))
