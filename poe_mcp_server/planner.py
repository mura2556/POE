"""High level planner that enriches crafting steps with curated intel."""

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, List, Sequence

from .datasources import bench_recipes, bestiary, bosses, essences, harvest
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

        beastcraft_hits = bestiary.find(base_text)
        if beastcraft_hits:
            metadata["bestiary_recipes"] = [asdict(recipe) for recipe in beastcraft_hits]
            lines = []
            for recipe in beastcraft_hits[:3]:
                beasts_summary = []
                for beast in recipe.beasts:
                    descriptor = f"{beast.amount}× {beast.name}"
                    extras = [part for part in (beast.rarity, beast.group, beast.family) if part]
                    if beast.min_level:
                        extras.append(f"lvl {beast.min_level}+")
                    if extras:
                        descriptor += f" ({', '.join(extras)})"
                    beasts_summary.append(descriptor)
                beasts_text = ", ".join(beasts_summary) or "Unknown beasts"
                tags = []
                if recipe.category and recipe.category != recipe.outcome:
                    tags.append(recipe.category)
                if recipe.game_mode == "ruthless":
                    tags.append("Ruthless")
                tag_text = f" [{' ; '.join(tags)}]" if tags else ""
                note_text = f" – {recipe.notes}" if recipe.notes else ""
                title = recipe.outcome or recipe.category or recipe.identifier
                lines.append(f"- {title}{tag_text} – Requires {beasts_text}{note_text}")
            section = _format_section("Beastcraft Options:", lines)
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
