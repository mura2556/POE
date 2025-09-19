"""Load curated fossil and resonator information."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Sequence

from .utils import load_json


@dataclass(frozen=True)
class Fossil:
    identifier: str
    name: str
    effects: Sequence[str]
    constraints: Sequence[str]
    keywords: Sequence[str]


@dataclass(frozen=True)
class Resonator:
    identifier: str
    name: str
    sockets: int
    description: str
    directions: str
    keywords: Sequence[str]


@dataclass(frozen=True)
class FossilMatches:
    fossils: Sequence[Fossil]
    resonators: Sequence[Resonator]


class _FossilIndex:
    def __init__(self) -> None:
        payload = load_json("crafting_methods.json")
        self._fossils = tuple(
            Fossil(
                identifier=entry["identifier"],
                name=entry["name"],
                effects=tuple(entry.get("effects", [])),
                constraints=tuple(entry.get("constraints", [])),
                keywords=tuple(entry.get("keywords", [])),
            )
            for entry in payload.get("fossils", [])
        )
        self._resonators = tuple(
            Resonator(
                identifier=entry["identifier"],
                name=entry["name"],
                sockets=int(entry.get("sockets", 1)),
                description=entry.get("description", ""),
                directions=entry.get("directions", ""),
                keywords=tuple(entry.get("keywords", [])),
            )
            for entry in payload.get("resonators", [])
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

    def search(self, query: str) -> FossilMatches:
        needle = self._normalise(query)
        fossils = [
            fossil
            for fossil in self._fossils
            if self._matches([fossil.name, *fossil.effects, *fossil.constraints, *fossil.keywords], needle)
        ]
        resonators = [
            resonator
            for resonator in self._resonators
            if self._matches(
                [
                    resonator.name,
                    resonator.description,
                    resonator.directions,
                    *(str(resonator.sockets),),
                    *resonator.keywords,
                ],
                needle,
            )
        ]
        return FossilMatches(tuple(fossils), tuple(resonators))

    @property
    def fossils(self) -> Sequence[Fossil]:
        return self._fossils

    @property
    def resonators(self) -> Sequence[Resonator]:
        return self._resonators


_INDEX: _FossilIndex | None = None


def _get_index() -> _FossilIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = _FossilIndex()
    return _INDEX


def load() -> FossilMatches:
    index = _get_index()
    return FossilMatches(index.fossils, index.resonators)


def find(query: str) -> FossilMatches:
    return _get_index().search(query)
