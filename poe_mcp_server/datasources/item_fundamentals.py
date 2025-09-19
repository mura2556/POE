"""Item fundamentals lookup helper."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class ItemFundamental:
    category: str
    name: str
    summary: str
    details: str


class _FundamentalIndex:
    def __init__(self) -> None:
        payload = load_json("item_fundamentals.json")
        self._entries = [ItemFundamental(**entry) for entry in payload]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def search(self, query: str, limit: int | None = None) -> List[ItemFundamental]:
        needle = self._normalise(query)
        if not needle:
            return []
        tokens = needle.split()
        matches: List[tuple[float, ItemFundamental]] = []
        for entry in self._entries:
            fields: Iterable[str] = [entry.category, entry.name, entry.summary]
            field_norms = [self._normalise(field) for field in fields if field]
            if not field_norms:
                continue
            coverage = sum(1 for token in tokens if any(token in field for field in field_norms))
            best_ratio = max(difflib.SequenceMatcher(None, needle, field).ratio() for field in field_norms)
            if coverage == 0 and best_ratio < 0.45:
                continue
            score = coverage + best_ratio
            matches.append((score, entry))
        matches.sort(key=lambda item: (-item[0], item[1].category.lower(), item[1].name.lower()))
        if limit is not None:
            matches = matches[:limit]
        return [entry for _, entry in matches]

    @property
    def entries(self) -> Sequence[ItemFundamental]:
        return tuple(self._entries)


_index: _FundamentalIndex | None = None


def _get_index() -> _FundamentalIndex:
    global _index
    if _index is None:
        _index = _FundamentalIndex()
    return _index


def load() -> Sequence[ItemFundamental]:
    return _get_index().entries


def find(query: str, limit: int | None = None) -> Sequence[ItemFundamental]:
    return tuple(_get_index().search(query, limit=limit))
