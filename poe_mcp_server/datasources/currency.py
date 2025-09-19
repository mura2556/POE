from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Sequence

from .utils import load_json


@dataclass(frozen=True)
class CurrencyEntry:
    metadata_id: str | None
    name: str
    tags: Sequence[str]
    action: str
    constraints: str
    release_version: str | None
    removal_version: str | None


class _CurrencyIndex:
    def __init__(self) -> None:
        payload = load_json("currency.json")
        self._entries: List[CurrencyEntry] = [
            CurrencyEntry(
                metadata_id=entry.get("metadata_id"),
                name=entry["name"],
                tags=tuple(entry.get("tags", [])),
                action=entry.get("action", ""),
                constraints=entry.get("constraints", ""),
                release_version=entry.get("release_version"),
                removal_version=entry.get("removal_version"),
            )
            for entry in payload
        ]

    @staticmethod
    def _normalise(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return " ".join(cleaned.split())

    def search(self, query: str) -> List[CurrencyEntry]:
        needle = self._normalise(query)
        if not needle:
            return []
        matches: List[CurrencyEntry] = []
        for entry in self._entries:
            haystack: Iterable[str] = [
                entry.name,
                *entry.tags,
                entry.action,
                entry.constraints,
            ]
            if any(
                needle in self._normalise(candidate)
                for candidate in haystack
                if candidate
            ):
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
