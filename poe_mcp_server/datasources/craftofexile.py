"""Craft of Exile data client and helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CraftOfExileError(RuntimeError):
    """Raised when the Craft of Exile bundle cannot be retrieved or parsed."""


@dataclass
class CraftOfExileDataset:
    """Typed accessors around the Craft of Exile data bundle."""

    payload: Mapping[str, Any]

    def _section(self, *candidates: str) -> Any:
        for key in candidates:
            if not key:
                continue
            if key in self.payload:
                return self.payload[key]
        return None

    @property
    def fossils(self) -> Any:
        """Return the fossil definitions provided by Craft of Exile."""

        return self._section("fossils", "Fossils", "fossil") or {}

    @property
    def harvest_crafts(self) -> Any:
        """Return the harvest craft definitions."""

        return self._section("harvest", "harvestCrafts", "Harvest", "HarvestCrafts") or {}

    @property
    def bench_recipes(self) -> Any:
        """Return the crafting bench recipes."""

        return self._section("bench", "benchRecipes", "Bench", "recipes", "craftingBench") or {}

    @property
    def meta_crafting_odds(self) -> Any:
        """Return meta-crafting odds sourced from the simulator."""

        return self._section(
            "metaCraftingOdds",
            "meta",
            "metaCraft",
            "metaCrafting",
            "meta_crafting_odds",
        ) or {}

    def iter_entries(self, section: Any) -> Iterable[Mapping[str, Any]]:
        """Yield mapping-like entries from heterogeneous sections."""

        if section is None:
            return []
        if isinstance(section, Mapping):
            for key, value in section.items():
                if isinstance(value, Mapping):
                    merged: Dict[str, Any] = dict(value)
                    merged.setdefault("id", key)
                    merged.setdefault("key", key)
                    yield merged
                else:
                    yield {"id": key, "value": value}
        elif isinstance(section, Iterable) and not isinstance(section, (str, bytes)):
            for entry in section:
                if isinstance(entry, Mapping):
                    yield entry
                else:
                    yield {"value": entry}
        else:
            yield {"value": section}

    def find(self, section: Any, identifier: str) -> Optional[Mapping[str, Any]]:
        """Find a specific entry by id, key or name."""

        if section is None:
            return None
        ident_lower = str(identifier).casefold()
        for entry in self.iter_entries(section):
            for candidate_key in ("id", "key", "name", "slug", "label"):
                value = entry.get(candidate_key)
                if value is None:
                    continue
                if str(value).casefold() == ident_lower:
                    return entry
        return None

    def fossil(self, identifier: str) -> Optional[Mapping[str, Any]]:
        """Look up a fossil by id/name."""

        return self.find(self.fossils, identifier)

    def harvest_craft(self, identifier: str) -> Optional[Mapping[str, Any]]:
        """Look up a harvest craft by id/name."""

        return self.find(self.harvest_crafts, identifier)

    def bench_recipe(self, identifier: str) -> Optional[Mapping[str, Any]]:
        """Look up a bench recipe by id/name."""

        return self.find(self.bench_recipes, identifier)

    def meta_craft(self, identifier: str) -> Optional[Mapping[str, Any]]:
        """Look up a meta craft by id/name."""

        return self.find(self.meta_crafting_odds, identifier)


class CraftOfExileClient:
    """Client capable of downloading the Craft of Exile data bundle."""

    DEFAULT_URL = "https://raw.githubusercontent.com/CraftOfExile/data/refs/heads/master/data.json"
    FALLBACK_URLS = (
        "https://raw.githubusercontent.com/CraftOfExile/data/refs/heads/main/data.json",
        "https://raw.githubusercontent.com/CraftOfExile/data/master/data.json",
        "https://raw.githubusercontent.com/CraftOfExile/data/main/data.json",
    )

    def __init__(self, bundle_url: Optional[str] = None, timeout: float = 30.0):
        self.bundle_url = bundle_url or self.DEFAULT_URL
        self.timeout = timeout

    def _candidate_urls(self) -> Iterable[str]:
        urls = [self.bundle_url]
        if self.bundle_url == self.DEFAULT_URL:
            urls.extend(url for url in self.FALLBACK_URLS if url not in urls)
        return urls

    def fetch(self) -> CraftOfExileDataset:
        """Download and parse the Craft of Exile dataset."""

        errors: list[str] = []
        raw: bytes | None = None
        for candidate in self._candidate_urls():
            request = Request(candidate, headers={"User-Agent": "poe-mcp-server/1.0"})
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                break
            except (HTTPError, URLError) as exc:  # pragma: no cover - network error paths
                errors.append(f"{candidate}: {exc}")
        else:  # pragma: no cover - depends on network
            error_msg = "; ".join(errors) if errors else "no candidates succeeded"
            raise CraftOfExileError(f"Unable to download Craft of Exile bundle ({error_msg}).")

        assert raw is not None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - depends on upstream data
            raise CraftOfExileError("Craft of Exile payload is not valid JSON") from exc

        return CraftOfExileDataset(payload)

    @staticmethod
    def load_from_path(path: Path | str) -> CraftOfExileDataset:
        """Load a previously cached Craft of Exile bundle."""

        data_path = Path(path)
        if not data_path.exists():
            raise CraftOfExileError(f"Craft of Exile dataset not found at {data_path}")

        try:
            payload = json.loads(data_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - depends on cache integrity
            raise CraftOfExileError(
                f"Craft of Exile cache at {data_path} is not valid JSON"
            ) from exc
        return CraftOfExileDataset(payload)

    @staticmethod
    def dump_to_path(dataset: CraftOfExileDataset, path: Path | str, *, pretty: bool = True) -> None:
        """Persist a Craft of Exile dataset to disk."""

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8") as handle:
            if pretty:
                json.dump(dataset.payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            else:
                json.dump(dataset.payload, handle, ensure_ascii=False)

