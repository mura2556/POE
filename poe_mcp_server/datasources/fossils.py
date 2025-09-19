"""Fossil and resonator metadata loader."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class TagWeight:
    """Modifier weight adjustment for a fossil."""

    tag: str
    weight: float


@dataclass(frozen=True)
class Fossil:
    """Curated fossil metadata."""

    identifier: str
    name: str
    descriptions: Sequence[str]
    blocked_descriptions: Sequence[str]
    mod_texts: Sequence[str]
    notes: Sequence[str]
    allowed_tags: Sequence[str]
    forbidden_tags: Sequence[str]
    positive_mod_weights: Sequence[TagWeight]
    negative_mod_weights: Sequence[TagWeight]


@dataclass(frozen=True)
class Resonator:
    """Curated resonator metadata."""

    identifier: str
    name: str
    sockets: int
    description: str
    effects: Sequence[str]
    notes: Sequence[str]
    allowed_fossils: Sequence[str]


@dataclass(frozen=True)
class SearchResults:
    """Result container for fossil lookups."""

    fossils: Sequence[Fossil]
    resonators: Sequence[Resonator]


class _FossilIndex:
    """Index fossils and resonators for keyword search."""

    _STOP_TOKENS = {
        "a",
        "an",
        "and",
        "apply",
        "craft",
        "crafting",
        "for",
        "in",
        "into",
        "on",
        "socket",
        "sockets",
        "socketed",
        "the",
        "to",
        "use",
        "using",
        "with",
    }
    _SOCKET_WORDS = {
        "single": 1,
        "one": 1,
        "double": 2,
        "two": 2,
        "triple": 3,
        "three": 3,
        "quad": 4,
        "quadruple": 4,
        "four": 4,
    }

    def __init__(self) -> None:
        payload = load_json("fossils.json")
        fossils_raw = payload.get("fossils", [])
        resonators_raw = payload.get("resonators", [])
        self._fossils = [self._build_fossil(entry) for entry in fossils_raw]
        self._resonators = [self._build_resonator(entry) for entry in resonators_raw]

    @staticmethod
    def _build_fossil(entry: dict) -> Fossil:
        def build_weights(values: Iterable[dict]) -> List[TagWeight]:
            weights: List[TagWeight] = []
            for item in values:
                tag = str(item.get("tag", "")).strip()
                if not tag:
                    continue
                raw_weight = item.get("weight", 0)
                if isinstance(raw_weight, (int, float)):
                    weight = float(raw_weight)
                else:
                    try:
                        weight = float(raw_weight)
                    except (TypeError, ValueError):
                        weight = 0.0
                weights.append(TagWeight(tag=tag, weight=weight))
            return weights

        return Fossil(
            identifier=str(entry.get("identifier", "")),
            name=str(entry.get("name", "")),
            descriptions=tuple(str(text) for text in entry.get("descriptions", []) if text),
            blocked_descriptions=tuple(str(text) for text in entry.get("blocked_descriptions", []) if text),
            mod_texts=tuple(str(text) for text in entry.get("mod_texts", []) if text),
            notes=tuple(str(text) for text in entry.get("notes", []) if text),
            allowed_tags=tuple(str(text) for text in entry.get("allowed_tags", []) if text),
            forbidden_tags=tuple(str(text) for text in entry.get("forbidden_tags", []) if text),
            positive_mod_weights=tuple(build_weights(entry.get("positive_mod_weights", []))),
            negative_mod_weights=tuple(build_weights(entry.get("negative_mod_weights", []))),
        )

    @staticmethod
    def _build_resonator(entry: dict) -> Resonator:
        sockets = entry.get("sockets")
        if not isinstance(sockets, int):
            try:
                sockets = int(sockets)
            except (TypeError, ValueError):
                sockets = 0
        return Resonator(
            identifier=str(entry.get("identifier", "")),
            name=str(entry.get("name", "")),
            sockets=sockets,
            description=str(entry.get("description", "")),
            effects=tuple(str(text) for text in entry.get("effects", []) if text),
            notes=tuple(str(text) for text in entry.get("notes", []) if text),
            allowed_fossils=tuple(str(text) for text in entry.get("allowed_fossils", []) if text),
        )

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def _tokenise(self, text: str) -> List[str]:
        return [token for token in self._normalise(text).split() if token]

    def _filter_tokens(self, tokens: Sequence[str], *, drop_socket_words: bool = False) -> List[str]:
        filtered: List[str] = []
        for token in tokens:
            if token in self._STOP_TOKENS:
                continue
            if drop_socket_words and token in self._SOCKET_WORDS:
                continue
            filtered.append(token)
        return filtered

    def _contains_tokens(self, haystack: Iterable[str], tokens: Sequence[str]) -> bool:
        if not tokens:
            return False
        normalised = [self._normalise(candidate) for candidate in haystack if candidate]
        if not normalised:
            return False
        for token in tokens:
            if not any(token in candidate for candidate in normalised):
                return False
        return True

    def _parse_socket_hints(self, query: str) -> set[int]:
        hints: set[int] = set()
        lowered = query.lower()
        for match in re.findall(r"(\d+)[\s-]*(?:socket|sock|slot)", lowered):
            try:
                hints.add(int(match))
            except ValueError:
                continue
        for word, value in self._SOCKET_WORDS.items():
            if word in lowered:
                hints.add(value)
        return hints

    def search_fossils(self, query: str) -> List[Fossil]:
        raw_tokens = self._tokenise(query)
        tokens = self._filter_tokens(raw_tokens)
        tokens = [
            token
            for token in tokens
            if token not in {"resonator", "resonators"}
            and token not in self._SOCKET_WORDS
            and not token.isdigit()
        ]
        matches: List[Fossil] = []
        for fossil in self._fossils:
            haystack = [
                fossil.identifier,
                fossil.name,
                *fossil.descriptions,
                *fossil.blocked_descriptions,
                *fossil.mod_texts,
                *fossil.notes,
                *fossil.allowed_tags,
                *fossil.forbidden_tags,
                *(weight.tag for weight in fossil.positive_mod_weights),
                *(weight.tag for weight in fossil.negative_mod_weights),
            ]
            if tokens and self._contains_tokens(haystack, tokens):
                matches.append(fossil)
        if not matches and ("fossil" in raw_tokens or "fossils" in raw_tokens):
            matches = list(self._fossils)
        return matches

    def search_resonators(self, query: str) -> List[Resonator]:
        raw_tokens = self._tokenise(query)
        tokens = self._filter_tokens(raw_tokens, drop_socket_words=True)
        socket_hints = self._parse_socket_hints(query)
        matches: List[Resonator] = []
        for resonator in self._resonators:
            haystack = [
                resonator.identifier,
                resonator.name,
                resonator.description,
                *resonator.effects,
                *resonator.notes,
                *resonator.allowed_fossils,
                str(resonator.sockets),
            ]
            if tokens and self._contains_tokens(haystack, tokens):
                if socket_hints and resonator.sockets not in socket_hints:
                    continue
                matches.append(resonator)
                continue
            if socket_hints and resonator.sockets in socket_hints:
                matches.append(resonator)
        if not matches and ("resonator" in raw_tokens or "resonators" in raw_tokens):
            matches = list(self._resonators)
        return matches

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


def load_fossils() -> Sequence[Fossil]:
    """Return all curated fossils."""

    return _get_index().fossils


def load_resonators() -> Sequence[Resonator]:
    """Return all curated resonators."""

    return _get_index().resonators


def find(query: str) -> SearchResults:
    """Return fossils and resonators matching *query*."""

    index = _get_index()
    fossil_hits = index.search_fossils(query)
    resonator_hits = index.search_resonators(query)
    return SearchResults(fossils=tuple(fossil_hits), resonators=tuple(resonator_hits))
