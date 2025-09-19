"""High level planner that enriches crafting steps with curated intel."""

from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, List, Sequence

from .datasources import bench_recipes, bosses, essences, fossils, harvest
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


def _dedupe_preserve_order(lines: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for line in lines:
        cleaned = line.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered


def _format_weight(weight: fossils.TagWeight) -> str:
    value = int(weight.weight) if float(weight.weight).is_integer() else weight.weight
    return f"{weight.tag} ({value})"


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

        fossil_hits = fossils.find(base_text)
        fossil_matches = list(fossil_hits.fossils)
        resonator_matches = list(fossil_hits.resonators)
        if fossil_matches or resonator_matches:
            metadata["fossils"] = {
                "fossils": [asdict(entry) for entry in fossil_matches],
                "resonators": [asdict(entry) for entry in resonator_matches],
            }
            fossil_lines: List[str] = []
            for fossil_entry in fossil_matches[:3]:
                effect_parts = _dedupe_preserve_order(
                    [*fossil_entry.descriptions, *fossil_entry.mod_texts, *fossil_entry.notes]
                )
                summary = "; ".join(effect_parts[:4])
                tag_bits: List[str] = []
                if fossil_entry.allowed_tags:
                    tag_bits.append("allows " + ", ".join(fossil_entry.allowed_tags[:4]))
                if fossil_entry.forbidden_tags:
                    tag_bits.append("blocks " + ", ".join(fossil_entry.forbidden_tags[:4]))
                if fossil_entry.positive_mod_weights:
                    tag_bits.append(
                        "weights+ "
                        + ", ".join(_format_weight(weight) for weight in fossil_entry.positive_mod_weights[:3])
                    )
                if fossil_entry.negative_mod_weights:
                    tag_bits.append(
                        "weights- "
                        + ", ".join(_format_weight(weight) for weight in fossil_entry.negative_mod_weights[:3])
                    )
                details: List[str] = []
                if summary:
                    details.append(summary)
                if tag_bits:
                    details.append("[" + "; ".join(tag_bits) + "]")
                line = f"- {fossil_entry.name}"
                if details:
                    line += " – " + " | ".join(details)
                fossil_lines.append(line)

            for resonator_entry in resonator_matches[:3]:
                effect_parts = _dedupe_preserve_order(
                    [resonator_entry.description, *resonator_entry.effects, *resonator_entry.notes]
                )
                sockets_text = ""
                if effect_parts and effect_parts[0].lower().startswith("supports up to"):
                    sockets_text = effect_parts.pop(0)
                elif resonator_entry.sockets:
                    sockets_text = (
                        f"Supports up to {resonator_entry.sockets} fossil"
                        f"{'s' if resonator_entry.sockets != 1 else ''}"
                    )
                details: List[str] = []
                if sockets_text:
                    details.append(sockets_text)
                if effect_parts:
                    details.append("; ".join(effect_parts[:3]))
                if resonator_entry.allowed_fossils:
                    details.append("favours " + ", ".join(resonator_entry.allowed_fossils[:4]))
                line = f"- {resonator_entry.name}"
                if details:
                    line += " – " + " | ".join(part for part in details if part)
                fossil_lines.append(line)

            section = _format_section("Fossil & Resonator Options:", fossil_lines)
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
