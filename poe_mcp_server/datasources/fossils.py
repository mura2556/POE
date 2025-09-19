"""Load curated fossil and resonator metadata."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class Fossil:
    identifier: str
    name: str
    effects: Sequence[str]
    allowed_tags: Sequence[str]
    forbidden_tags: Sequence[str]


@dataclass(frozen=True)
class Resonator:
    identifier: str
    name: str
    effects: Sequence[str]
    socket_count: int | None
    tags: Sequence[str]


@dataclass(frozen=True)
class FossilSearchResult:
    fossils: Sequence[Fossil]
    resonators: Sequence[Resonator]


def _normalise(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(cleaned.split())


def _tokenise_text(text: str) -> set[str]:
    tokens: set[str] = set()
    if not text:
        return tokens
    normalised = _normalise(text)
    if not normalised:
        return tokens
    for token in normalised.split():
        tokens.add(token)
        if token.endswith("s") and len(token) > 3:
            tokens.add(token[:-1])
    return tokens


def _tokenise_many(values: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        tokens.update(_tokenise_text(value))
    return tokens


class _FossilIndex:
    def __init__(self) -> None:
        payload = load_json("fossils.json")
        fossil_entries = payload.get("fossils", []) if isinstance(payload, dict) else []
        resonator_entries = payload.get("resonators", []) if isinstance(payload, dict) else []

        self._fossils: List[Fossil] = [
            Fossil(
                identifier=entry["identifier"],
                name=entry["name"],
                effects=tuple(entry.get("effects", [])),
                allowed_tags=tuple(entry.get("allowed_tags", [])),
                forbidden_tags=tuple(entry.get("forbidden_tags", [])),
            )
            for entry in fossil_entries
            if entry.get("identifier") and entry.get("name")
        ]
        self._resonators: List[Resonator] = [
            Resonator(
                identifier=entry["identifier"],
                name=entry["name"],
                effects=tuple(entry.get("effects", [])),
                socket_count=entry.get("socket_count"),
                tags=tuple(entry.get("tags", [])),
            )
            for entry in resonator_entries
            if entry.get("identifier") and entry.get("name")
        ]

        self._fossils.sort(key=lambda fossil: fossil.name)
        self._resonators.sort(key=lambda resonator: (resonator.socket_count or 0, resonator.name))

        self._fossil_name_tokens = {f.identifier: _tokenise_text(f.name) for f in self._fossils}
        self._resonator_name_tokens = {r.identifier: _tokenise_text(r.name) for r in self._resonators}
        self._fossil_tokens = {
            fossil.identifier: _tokenise_many(
                [
                    fossil.name,
                    *fossil.effects,
                    *[tag.replace("_", " ") for tag in fossil.allowed_tags],
                    *[tag.replace("_", " ") for tag in fossil.forbidden_tags],
                ]
            )
            for fossil in self._fossils
        }
        self._resonator_tokens = {
            resonator.identifier: _tokenise_many(
                [
                    resonator.name,
                    *resonator.effects,
                    *[tag.replace("_", " ") for tag in resonator.tags],
                    f"{resonator.socket_count}-socket" if resonator.socket_count else "",
                ]
            )
            for resonator in self._resonators
        }
        self._trigger_tokens = {"fossil", "fossils", "resonator", "resonators"}

    def _matches_tokens(self, entry_id: str, table: dict[str, set[str]], tokens: set[str]) -> bool:
        return bool(tokens & table.get(entry_id, set()))

    def _matches_name(self, entry_id: str, tokens: set[str], name_tokens: dict[str, set[str]]) -> bool:
        candidate = name_tokens.get(entry_id, set())
        return bool(candidate) and candidate <= tokens

    def search(self, query: str) -> FossilSearchResult:
        tokens = _tokenise_text(query)
        if not tokens:
            return FossilSearchResult((), ())

        relevant = bool(tokens & self._trigger_tokens)
        if not relevant:
            relevant = any(self._matches_name(fid, tokens, self._fossil_name_tokens) for fid in self._fossil_name_tokens)
        if not relevant:
            relevant = any(
                self._matches_name(rid, tokens, self._resonator_name_tokens) for rid in self._resonator_name_tokens
            )
        if not relevant:
            return FossilSearchResult((), ())

        socket_numbers = {int(token) for token in tokens if token.isdigit()}

        name_hits: List[Fossil] = []
        tag_hits: List[Fossil] = []
        fossil_seen: set[str] = set()
        for fossil in self._fossils:
            if self._matches_name(fossil.identifier, tokens, self._fossil_name_tokens):
                if fossil.identifier not in fossil_seen:
                    name_hits.append(fossil)
                    fossil_seen.add(fossil.identifier)
            elif self._matches_tokens(fossil.identifier, self._fossil_tokens, tokens):
                if fossil.identifier not in fossil_seen:
                    tag_hits.append(fossil)
                    fossil_seen.add(fossil.identifier)
        fossil_matches: List[Fossil] = (name_hits + tag_hits)[:6]

        if not fossil_matches and "fossil" in tokens:
            fossil_matches = self._fossils[:5]

        name_resonators: List[Resonator] = []
        tag_resonators: List[Resonator] = []
        resonator_seen: set[str] = set()
        for resonator in self._resonators:
            if socket_numbers and resonator.socket_count not in socket_numbers:
                continue
            if self._matches_name(resonator.identifier, tokens, self._resonator_name_tokens):
                if resonator.identifier not in resonator_seen:
                    name_resonators.append(resonator)
                    resonator_seen.add(resonator.identifier)
            elif self._matches_tokens(resonator.identifier, self._resonator_tokens, tokens):
                if resonator.identifier not in resonator_seen:
                    tag_resonators.append(resonator)
                    resonator_seen.add(resonator.identifier)
        resonator_matches: List[Resonator] = (name_resonators + tag_resonators)[:4]

        if not resonator_matches and "resonator" in tokens:
            resonator_matches = self._resonators[:3]

        return FossilSearchResult(tuple(fossil_matches), tuple(resonator_matches))

    @property
    def fossils(self) -> Sequence[Fossil]:
        return tuple(self._fossils)

    @property
    def resonators(self) -> Sequence[Resonator]:
        return tuple(self._resonators)


_index: _FossilIndex | None = None


def _get_index() -> _FossilIndex:
    global _index
    if _index is None:
        _index = _FossilIndex()
    return _index


def load() -> FossilSearchResult:
    index = _get_index()
    return FossilSearchResult(index.fossils, index.resonators)


def find(query: str) -> FossilSearchResult:
    return _get_index().search(query)
