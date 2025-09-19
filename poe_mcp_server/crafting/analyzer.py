"""Item analysis helpers backed by the RePoE export."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from poe_mcp_server.datasources.repoe import (
    REPOE_DEFAULT_BRANCH,
    RePoEData,
    SpawnWeightBreakdown,
    load_repoe_data,
)

logger = logging.getLogger(__name__)


@dataclass
class ModAnalysis:
    """Summary of a single desired mod for an item."""

    mod_id: str
    display_name: Optional[str]
    tier: Dict[str, object]
    spawn_weights: SpawnWeightBreakdown
    bench_options: List[Dict[str, object]]
    stats: List[Dict[str, object]]

    def as_dict(self) -> Dict[str, object]:
        return {
            "mod_id": self.mod_id,
            "display_name": self.display_name,
            "tier": self.tier,
            "spawn_weights": {
                "relevant_tags": self.spawn_weights.relevant_tags,
                "total_weight": self.spawn_weights.total_weight,
                "disabled_tags": self.spawn_weights.disabled_tags,
                "is_spawnable": self.spawn_weights.is_spawnable,
            },
            "bench_options": self.bench_options,
            "stats": self.stats,
        }


class CraftingAnalyzer:
    """Analyse an item base with regard to a set of desired mods."""

    def __init__(
        self,
        *,
        data: Optional[RePoEData] = None,
        base_path: Optional[Path] = None,
        branch: str = REPOE_DEFAULT_BRANCH,
        league: Optional[str] = None,
        auto_download: bool = False,
    ) -> None:
        if data is None:
            self.data = load_repoe_data(
                base_path=base_path, branch=branch, league=league, download=auto_download
            )
        else:
            self.data = data
        self.branch = branch
        self.league = league

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyse_item(
        self,
        base_identifier: str,
        desired_mods: Sequence[str],
        *,
        influences: Optional[Iterable[str]] = None,
    ) -> Dict[str, object]:
        """Analyse an item base and the requested mods.

        Parameters
        ----------
        base_identifier:
            Either the display name or metadata id for the base item.
        desired_mods:
            Collection of mod identifiers or display names.
        influences:
            Optional influences that should be considered when computing spawn
            weights (for example ``["shaper", "crusader"]``).
        """

        base_id, base_data = self.data.resolve_base(base_identifier)
        base_description = self.data.describe_base(base_id, base_data)
        base_tags = base_description["tags"]

        analyses: List[ModAnalysis] = []
        for entry in desired_mods:
            try:
                mod_id, mod_data = self.data.resolve_mod(entry)
            except KeyError as exc:
                logger.warning("Skipping unknown mod '%s': %s", entry, exc)
                continue

            tier_info = self.data.tier_breakdown(mod_id)
            spawn_weights = self.data.spawn_weights(mod_id, base_tags, influences)
            bench = self.data.bench_options(mod_id)
            stats = [
                {
                    "id": stat.get("id"),
                    "min": stat.get("min"),
                    "max": stat.get("max"),
                    "type": stat.get("type"),
                }
                for stat in mod_data.get("stats", [])
            ]

            analyses.append(
                ModAnalysis(
                    mod_id=mod_id,
                    display_name=mod_data.get("name"),
                    tier=tier_info,
                    spawn_weights=spawn_weights,
                    bench_options=bench,
                    stats=stats,
                )
            )

        return {
            "base": base_description,
            "mods": [analysis.as_dict() for analysis in analyses],
            "influences": sorted({inf.lower() for inf in influences} if influences else []),
            "branch": self.branch,
            "league": self.league,
        }


__all__ = ["CraftingAnalyzer", "ModAnalysis"]
