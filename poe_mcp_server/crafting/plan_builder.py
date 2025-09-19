"""Helpers to build crafting plans using Craft of Exile statistics."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from poe_mcp_server.datasources.craftofexile import (
    CraftOfExileClient,
    CraftOfExileDataset
)


@dataclass
class CraftingPlanStep:
    """A single step in a crafting plan."""

    action: str
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class CraftingPlanBuilder:
    """Constructs crafting plans enriched with Craft of Exile data."""

    def __init__(
        self,
        *,
        craft_of_exile_base_path: Path | str = Path("data/craft_of_exile"),
        craft_of_exile_league: Optional[str] = None,
    ) -> None:
        self.craft_of_exile_base_path = Path(craft_of_exile_base_path)
        self.craft_of_exile_league = craft_of_exile_league
        self._craft_of_exile_cache: Optional[CraftOfExileDataset] = None

    def _craft_of_exile_path(self) -> Path:
        path = self.craft_of_exile_base_path
        if self.craft_of_exile_league:
            path = path / self.craft_of_exile_league
        return path / "data.json"

    def _load_craft_of_exile(self) -> CraftOfExileDataset:
        if self._craft_of_exile_cache is None:
            data_path = self._craft_of_exile_path()
            self._craft_of_exile_cache = CraftOfExileClient.load_from_path(data_path)
        return self._craft_of_exile_cache

    def _resolve_reference(self, step: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        dataset = self._load_craft_of_exile()
        lookup_type = step.get("reference_type")
        lookup_key = step.get("reference_id")
        if not lookup_type or not lookup_key:
            return None

        if lookup_type == "fossil":
            return dataset.fossil(lookup_key)
        if lookup_type == "harvest":
            return dataset.harvest_craft(lookup_key)
        if lookup_type == "bench":
            return dataset.bench_recipe(lookup_key)
        if lookup_type == "meta":
            return dataset.meta_craft(lookup_key)
        return None

    def build(self, steps: Iterable[Mapping[str, Any]]) -> List[CraftingPlanStep]:
        """Build a plan enriched with Craft of Exile lookup metadata."""

        plan: List[CraftingPlanStep] = []
        for step in steps:
            metadata = dict(step.get("metadata", {}))
            reference = self._resolve_reference(step)
            if reference:
                metadata["craft_of_exile"] = reference
            plan.append(
                CraftingPlanStep(
                    action=str(step.get("action", "")),
                    description=str(step.get("description", "")),
                    metadata=metadata,
                )
            )
        return plan


__all__ = ["CraftingPlanBuilder", "CraftingPlanStep"]

