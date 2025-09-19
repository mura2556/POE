"""High level planner that enriches crafting steps with curated intel."""

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, List, Sequence

from .datasources import bench_recipes, bosses, currency, essences, harvest
from .models import CraftingStep


def _format_section(header: str, lines: Iterable[str]) -> str:
    body = [line for line in lines if line]
    if not body:
        return ""
    return "\n".join([header, *body])


def _format_costs(costs: Sequence[bench_recipes.BenchCost]) -> str:
    if not costs:
        return "free"
    return ", ".join(f"{cost.amount} {cost.currency}" for cost in costs)


def assemble_crafting_plan(actions: Sequence[str]) -> List[CraftingStep]:
    """Attach structured intel to a list of crafting actions."""

    enriched_steps: List[CraftingStep] = []
    for raw_action in actions:
        base_text = raw_action.strip()
        instruction_parts: List[str] = [base_text]
        metadata: dict[str, object] = {}

        boss_hits = bosses.search(base_text)
        atlas_bosses = boss_hits.get("atlas_bosses", [])
        map_bosses = boss_hits.get("map_bosses", [])
        if atlas_bosses:
            metadata["atlas_bosses"] = [asdict(boss) for boss in atlas_bosses]
            lines = [
                f"- {boss.name} ({boss.encounter})"
                + (f" – Unlock: {boss.unlock[0]}" if boss.unlock else "")
                for boss in atlas_bosses[:3]
            ]
            section = _format_section("Boss Intel:", lines)
            if section:
                instruction_parts.append(section)
        if map_bosses:
            metadata["map_bosses"] = [asdict(boss) for boss in map_bosses]
            lines = [
                f"- {boss.map} (Tier {boss.tier}) – {', '.join(boss.bosses)}"
                + (f"; {boss.unlock[0]}" if boss.unlock else "")
                for boss in map_bosses[:3]
            ]
            section = _format_section("Map Boss Details:", lines)
            if section:
                instruction_parts.append(section)

        bench_hits = bench_recipes.find(base_text)
        if bench_hits:
            metadata["bench_recipes"] = [asdict(recipe) for recipe in bench_hits]
            lines = [
                f"- {recipe.display} ({recipe.master}, tier {recipe.bench_tier}; cost {_format_costs(recipe.costs)})"
                for recipe in bench_hits[:3]
            ]
            section = _format_section("Workbench Options:", lines)
            if section:
                instruction_parts.append(section)

        currency_hits = currency.find(base_text)
        if currency_hits:
            metadata["currency"] = [asdict(entry) for entry in currency_hits]
            lines: List[str] = []
            for entry in currency_hits[:3]:
                base_line = f"- {entry.name}"
                if entry.action and entry.constraints:
                    lines.append(f"{base_line}: {entry.action} – {entry.constraints}")
                elif entry.action:
                    lines.append(f"{base_line}: {entry.action}")
                elif entry.constraints:
                    lines.append(f"{base_line}: {entry.constraints}")
                else:
                    lines.append(base_line)
            section = _format_section("Currency Options:", lines)
            if section:
                instruction_parts.append(section)

        harvest_hits = harvest.find(base_text)
        if harvest_hits:
            metadata["harvest_crafts"] = [asdict(craft) for craft in harvest_hits]
            lines = [
                f"- {craft.description[0]}" + (f" [{', '.join(craft.groups)}]" if craft.groups else "")
                for craft in harvest_hits[:3]
            ]
            section = _format_section("Harvest Options:", lines)
            if section:
                instruction_parts.append(section)

        essence_hits = essences.find(base_text)
        if essence_hits:
            metadata["essences"] = [asdict(essence) for essence in essence_hits]
            lines = [
                f"- {essence.name} (Tier {essence.tier}, lvl {essence.level}) – {', '.join(essence.mods[:2])}"
                for essence in essence_hits[:3]
            ]
            section = _format_section("Essence Notes:", lines)
            if section:
                instruction_parts.append(section)

        instruction = "\n\n".join(part for part in instruction_parts if part)
        enriched_steps.append(CraftingStep(action=base_text, instruction=instruction, metadata=metadata))

    return enriched_steps
