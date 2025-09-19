"""Currency metadata loader."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence

from .utils import load_json


_STOPWORDS = {
    "a",
    "an",
    "and",
    "apply",
    "click",
    "for",
    "in",
    "item",
    "items",
    "left",
    "of",
    "on",
    "please",
    "right",
    "the",
    "then",
    "this",
    "to",
    "use",
    "with",
}


@dataclass(frozen=True)
class CurrencyEntry:
    name: str
    category: str
    effect: str
    restrictions: Sequence[str]
    description: str
    metadata_id: str
    aliases: Sequence[str]
    keywords: Sequence[str]


class _CurrencyIndex:
    def __init__(self) -> None:
        payload = load_json("currency.json")
        self._entries: List[CurrencyEntry] = [
            CurrencyEntry(
                name=entry.get("name", ""),
                category=entry.get("category", ""),
                effect=entry.get("effect", ""),
                restrictions=tuple(entry.get("restrictions", [])),
                description=entry.get("description", ""),
                metadata_id=entry.get("metadata_id", ""),
                aliases=tuple(entry.get("aliases", [])),
                keywords=tuple(entry.get("keywords", [])),
            )
            for entry in payload
        ]
        self._search_index: List[tuple[CurrencyEntry, Sequence[str]]] = [
            (entry, self._build_haystack(entry)) for entry in self._entries
        ]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def _build_haystack(self, entry: CurrencyEntry) -> Sequence[str]:
        sources: Iterable[str] = [
            entry.name,
            entry.category,
            entry.effect,
            entry.description,
            entry.metadata_id,
            *entry.aliases,
            *entry.restrictions,
            *entry.keywords,
        ]
        return [self._normalise(source) for source in sources if source]

    def search(self, query: str) -> List[CurrencyEntry]:
        needle = self._normalise(query)
        if not needle:
            return []
        raw_tokens = [token for token in needle.split() if token]
        tokens = [token for token in raw_tokens if token not in _STOPWORDS]
        if not tokens:
            tokens = raw_tokens
        matches: List[CurrencyEntry] = []
        for entry, haystack in self._search_index:
            if any(needle in candidate for candidate in haystack):
                matches.append(entry)
                continue
            if not tokens:
                continue
            if all(any(token in candidate for candidate in haystack) for token in tokens):
                matches.append(entry)
        return matches

    @property
    def entries(self) -> Sequence[CurrencyEntry]:
        return tuple(self._entries)


_index: _CurrencyIndex | None = None


def _get_index() -> _CurrencyIndex:
    global _index
    if _index is None:
        _index = _CurrencyIndex()
    return _index


def load() -> Sequence[CurrencyEntry]:
    return _get_index().entries


def find(query: str) -> Sequence[CurrencyEntry]:
    return tuple(_get_index().search(query))
