"""High level planner that enriches crafting steps with curated intel."""

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, List, Sequence

from .datasources import (
    bench_recipes,
    bestiary,
    betrayal,
    bosses,
    crafting_strategies,
    essences,
    fossils,
    harvest,
    vendor_recipes,
)
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

        fossil_hits = fossils.find(base_text)
        if fossil_hits.fossils:
            metadata["fossils"] = [asdict(fossil) for fossil in fossil_hits.fossils]
            lines = []
            for fossil in fossil_hits.fossils[:3]:
                effect = fossil.effects[0] if fossil.effects else "See details"
                constraint = f" (Constraints: {', '.join(fossil.constraints)})" if fossil.constraints else ""
                lines.append(f"- {fossil.name}: {effect}{constraint}")
            section = _format_section("Fossil Options:", lines)
            if section:
                instruction_parts.append(section)
        if fossil_hits.resonators:
            metadata["resonators"] = [asdict(resonator) for resonator in fossil_hits.resonators]
            lines = [
                f"- {resonator.name} ({resonator.sockets} socket{'s' if resonator.sockets != 1 else ''})"
                + (f": {resonator.description}" if resonator.description else "")
                for resonator in fossil_hits.resonators[:3]
            ]
            section = _format_section("Resonator Choices:", lines)
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

        beastcraft_hits = bestiary.find(base_text)
        if beastcraft_hits:
            metadata["beastcrafts"] = [asdict(craft) for craft in beastcraft_hits]
            lines = []
            for craft in beastcraft_hits[:3]:
                beasts = ", ".join(
                    f"{req.quantity}x {req.name}" + (f" ({req.rarity})" if req.rarity else "")
                    for req in craft.beasts
                )
                detail = f"Requires: {beasts}" if beasts else ""
                note = craft.notes[0] if craft.notes else ""
                suffix_parts = [part for part in [detail, note] if part]
                suffix = f" – {'; '.join(suffix_parts)}" if suffix_parts else ""
                lines.append(f"- {craft.header} – {craft.result or 'Outcome'} ({craft.game_mode}){suffix}")
            section = _format_section("Bestiary Crafts:", lines)
            if section:
                instruction_parts.append(section)

        betrayal_hits = betrayal.find(base_text)
        if betrayal_hits:
            metadata["betrayal_benches"] = [asdict(bench) for bench in betrayal_hits]
            lines = [
                f"- {bench.member} ({bench.division} rank {bench.rank}) – {bench.summary}"
                for bench in betrayal_hits[:3]
            ]
            section = _format_section("Betrayal Benches:", lines)
            if section:
                instruction_parts.append(section)

        strategy_hits = crafting_strategies.find(base_text)
        if strategy_hits:
            metadata["strategies"] = [asdict(strategy) for strategy in strategy_hits]
            lines = [
                f"- {strategy.name}: {strategy.summary}"
                + (f" (Best for: {strategy.best_for[0]})" if strategy.best_for else "")
                for strategy in strategy_hits[:3]
            ]
            section = _format_section("Crafting Strategies:", lines)
            if section:
                instruction_parts.append(section)

        vendor_hits = vendor_recipes.find(base_text)
        if vendor_hits:
            metadata["vendor_recipes"] = [asdict(recipe) for recipe in vendor_hits]
            lines = [
                f"- {recipe.name} → {recipe.reward} (Inputs: {', '.join(recipe.inputs)})"
                + (f" – {recipe.notes[0]}" if recipe.notes else "")
                for recipe in vendor_hits[:3]
            ]
            section = _format_section("Vendor Recipes:", lines)
            if section:
                instruction_parts.append(section)

        instruction = "\n\n".join(part for part in instruction_parts if part)
        enriched_steps.append(CraftingStep(action=base_text, instruction=instruction, metadata=metadata))

    return enriched_steps
