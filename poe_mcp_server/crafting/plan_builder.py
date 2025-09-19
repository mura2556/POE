"""High level crafting plan generator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Sequence

from poe_mcp_server.crafting.analyzer import CraftingAnalyzer


@dataclass
class PlanStep:
    """A single crafting recommendation."""

    target: Dict[str, object]
    commentary: str

    def as_dict(self) -> Dict[str, object]:
        data = dict(self.target)
        data["commentary"] = self.commentary
        return data


class CraftingPlanBuilder:
    """Compose a high level plan using :class:`CraftingAnalyzer`."""

    def __init__(
        self,
        analyzer: CraftingAnalyzer,
    ) -> None:
        self.analyzer = analyzer

    def build_plan(
        self,
        base_identifier: str,
        desired_mods: Sequence[str],
        *,
        influences: Optional[Iterable[str]] = None,
    ) -> Dict[str, object]:
        """Return a structured crafting plan for the requested mods."""

        analysis = self.analyzer.analyse_item(
            base_identifier, desired_mods, influences=influences
        )
        steps = [self._build_step(mod) for mod in analysis["mods"]]
        return {
            "base": analysis["base"],
            "steps": [step.as_dict() for step in steps],
            "influences": analysis["influences"],
            "branch": analysis["branch"],
            "league": analysis["league"],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_step(self, mod_summary: Dict[str, object]) -> PlanStep:
        mod_id = mod_summary["mod_id"]
        display = mod_summary.get("display_name") or mod_id
        tier_info = mod_summary["tier"]
        tier = tier_info.get("tier")
        total = tier_info.get("total_tiers")
        spawn = mod_summary["spawn_weights"]

        if spawn.get("is_spawnable"):
            if tier and total:
                commentary = f"Roll until {display} (T{tier}/{total})."
            else:
                commentary = f"Roll until {display}."
            top_weights = spawn["relevant_tags"][:3]
            if top_weights:
                formatted = ", ".join(f"{tag}: {weight}" for tag, weight in top_weights)
                commentary += f" Key spawn tags → {formatted}."
        else:
            commentary = f"Cannot naturally roll {display}; rely on bench or special mechanics."

        bench = mod_summary.get("bench_options", [])
        if bench:
            option = bench[0]
            costs = ", ".join(
                f"{c['amount']}× {c['currency_name']}" for c in option.get("cost", [])
            )
            bench_line = f"Bench craft via {option.get('master')} (tier {option.get('bench_tier')})"
            if costs:
                bench_line += f" costing {costs}"
            commentary += f" {bench_line}."

        return PlanStep(target=mod_summary, commentary=commentary)


__all__ = ["CraftingPlanBuilder", "PlanStep"]
