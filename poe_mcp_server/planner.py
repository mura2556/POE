"""High level planner that enriches crafting steps with curated intel."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, List, Sequence

from .datasources import bench_recipes, bosses, essences, harvest
from .models import CraftingStep, ItemBlueprint, ModRequirement, SocketBlueprint


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


@dataclass(frozen=True)
class _ModClassification:
    """Intermediate structure describing how to satisfy a modifier."""

    mod: ModRequirement
    kind: str
    matches: Sequence[object]
    search_terms: Sequence[str]


def _search_matches(searcher, terms: Sequence[str]) -> Sequence[object]:
    seen: set[str] = set()
    for term in terms:
        cleaned = term.strip()
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        results = searcher(cleaned)
        if results:
            return results
    return ()


def _classify_mod(blueprint: ItemBlueprint, mod: ModRequirement) -> _ModClassification:
    if mod.source_hint and mod.source_hint.kind == "influence":
        return _ModClassification(mod=mod, kind="influence", matches=tuple(blueprint.influences), search_terms=())

    hint_kind = mod.source_hint.kind if mod.source_hint else None
    terms: List[str] = []
    if mod.source_hint and mod.source_hint.detail:
        terms.append(mod.source_hint.detail)
    terms.append(mod.text)

    priority: List[str] = []
    if hint_kind in {"essence", "harvest", "bench"}:
        priority.append(hint_kind)
    for default in ("essence", "harvest", "bench"):
        if default not in priority:
            priority.append(default)

    for kind in priority:
        if kind == "essence":
            matches = _search_matches(essences.find, terms)
        elif kind == "harvest":
            matches = _search_matches(harvest.find, terms)
        else:  # bench
            matches = _search_matches(bench_recipes.find, terms)
        if matches:
            return _ModClassification(mod=mod, kind=kind, matches=matches, search_terms=tuple(terms))

    if blueprint.influences:
        term_blob = " ".join(terms).lower()
        if any(influence.lower() in term_blob for influence in blueprint.influences):
            return _ModClassification(
                mod=mod,
                kind="influence",
                matches=tuple(blueprint.influences),
                search_terms=tuple(terms),
            )

    return _ModClassification(mod=mod, kind="unresolved", matches=(), search_terms=tuple(terms))


def _describe_socket_plan(sockets: SocketBlueprint) -> str:
    parts: List[str] = []
    if sockets.total:
        parts.append(f"{sockets.total} sockets")
    if sockets.links:
        link = max(sockets.links)
        parts.append(f"{link}-link")
    if sockets.colours:
        colour_desc = ", ".join(f"{colour}:{amount}" for colour, amount in sockets.colours.items())
        parts.append(f"colours [{colour_desc}]")
    if sockets.notes:
        parts.extend(sockets.notes)
    return ", ".join(parts) if parts else "default sockets"


def _plan_for_blueprint(blueprint: ItemBlueprint) -> List[CraftingStep]:
    steps: List[CraftingStep] = []

    base_metadata: dict[str, object] = {
        "type": "base_item",
        "base_item": blueprint.base_item,
    }
    if blueprint.name:
        base_metadata["item_name"] = blueprint.name
    if blueprint.item_class:
        base_metadata["item_class"] = blueprint.item_class
    if blueprint.influences:
        base_metadata["influences"] = list(blueprint.influences)
    if blueprint.notes:
        base_metadata["blueprint_notes"] = list(blueprint.notes)

    base_instruction = [f"Start with a {blueprint.base_item}."]
    if blueprint.influences:
        influences = ", ".join(blueprint.influences)
        base_instruction.append(f"Prefer a base that already has {influences} influence.")
    if blueprint.notes:
        base_instruction.extend(blueprint.notes)

    steps.append(
        CraftingStep(
            action=f"Acquire {blueprint.base_item}",
            instruction="\n".join(base_instruction),
            metadata=base_metadata,
        )
    )

    if blueprint.sockets:
        socket_instruction: List[str] = [
            f"Target socket layout: {_describe_socket_plan(blueprint.sockets)}."
        ]
        socket_metadata: dict[str, object] = {
            "type": "sockets",
            "requested": asdict(blueprint.sockets),
        }
        bench_matches = ()
        if blueprint.sockets.links:
            bench_matches = bench_recipes.find(f"Link {max(blueprint.sockets.links)} sockets")
        elif blueprint.sockets.total:
            bench_matches = bench_recipes.find(f"{blueprint.sockets.total} sockets")
        if bench_matches:
            socket_metadata["bench_recipes"] = [asdict(recipe) for recipe in bench_matches[:3]]
            socket_instruction.append("Use the crafting bench or Vorici in Research to hit the link target early.")
        steps.append(
            CraftingStep(
                action="Configure sockets",
                instruction="\n".join(socket_instruction),
                metadata=socket_metadata,
            )
        )

    classifications = [_classify_mod(blueprint, mod) for mod in blueprint.all_required_mods()]

    essence_buckets: dict[str, dict[str, object]] = {}
    harvest_steps: List[tuple[_ModClassification, harvest.HarvestCraft]] = []
    bench_steps: List[tuple[_ModClassification, bench_recipes.BenchRecipe]] = []
    influence_mods: List[_ModClassification] = []
    unresolved_mods: List[_ModClassification] = []

    for classification in classifications:
        if classification.kind == "essence" and classification.matches:
            essence = classification.matches[0]
            key = getattr(essence, "identifier", classification.search_terms[0] if classification.search_terms else classification.mod.text)
            bucket = essence_buckets.setdefault(
                key,
                {
                    "essence": essence,
                    "mods": [],
                    "all_matches": classification.matches,
                },
            )
            bucket["mods"].append(classification.mod)
        elif classification.kind == "harvest" and classification.matches:
            harvest_steps.append((classification, classification.matches[0]))
        elif classification.kind == "bench" and classification.matches:
            bench_steps.append((classification, classification.matches[0]))
        elif classification.kind == "influence":
            influence_mods.append(classification)
        else:
            unresolved_mods.append(classification)

    if influence_mods:
        mod_texts = [entry.mod.text for entry in influence_mods]
        influence_instruction = [
            "The following modifiers require influenced bases or slams:",
            "- " + "\n- ".join(mod_texts),
            "Use Awakener's Orbs, influence-specific Exalted Orbs, or trade to secure these mods.",
        ]
        metadata: dict[str, object] = {
            "type": "influence",
            "covers_mods": mod_texts,
        }
        if blueprint.influences:
            metadata["influences"] = list(blueprint.influences)
            influence_instruction.insert(1, f"Relevant influences: {', '.join(blueprint.influences)}.")
        steps.append(
            CraftingStep(
                action="Handle influence-exclusive mods",
                instruction="\n".join(influence_instruction),
                metadata=metadata,
            )
        )

    for bucket in essence_buckets.values():
        essence = bucket["essence"]
        mods = bucket["mods"]
        mod_texts = [mod.text for mod in mods]
        instruction_lines = [
            f"Apply {getattr(essence, 'name', 'the selected essence')} to guarantee: {', '.join(mod_texts)}.",
            "Do this before bench crafts to keep modification options open.",
        ]
        metadata = {
            "type": "essence",
            "covers_mods": mod_texts,
            "essence": asdict(essence) if hasattr(essence, "identifier") else essence,
        }
        if bucket["all_matches"]:
            metadata["candidates"] = [
                asdict(match) if hasattr(match, "identifier") else match for match in bucket["all_matches"]
            ]
        steps.append(
            CraftingStep(
                action=f"Apply {getattr(essence, 'name', 'essence')}",
                instruction="\n".join(instruction_lines),
                metadata=metadata,
            )
        )

    for classification, craft in harvest_steps:
        mod = classification.mod
        mod_texts = [mod.text]
        description = craft.description[0] if craft.description else craft.identifier
        instruction_lines = [
            f"Use Harvest option '{description}' to secure {mod.text}.",
            "Aim to complete essence applications before this step to reduce random outcomes.",
        ]
        metadata = {
            "type": "harvest",
            "covers_mods": mod_texts,
            "harvest_crafts": [asdict(craft)] + [
                asdict(extra) for extra in classification.matches[1:3]
                if hasattr(extra, "identifier")
            ],
        }
        steps.append(
            CraftingStep(
                action=f"Harvest craft for {mod.text}",
                instruction="\n".join(instruction_lines),
                metadata=metadata,
            )
        )

    for classification, recipe in bench_steps:
        mod = classification.mod
        mod_texts = [mod.text]
        instruction_lines = [f"Use the crafting bench to craft '{recipe.display}'."]
        if mod.mod_type == "suffix":
            instruction_lines.append("Apply this craft last so a suffix remains open for other manipulations.")
        if mod.notes:
            instruction_lines.extend(mod.notes)
        metadata: dict[str, object] = {
            "type": "bench",
            "covers_mods": mod_texts,
            "bench_recipe": asdict(recipe),
        }
        if mod.mod_type == "suffix":
            metadata["consumes_suffix"] = True
        steps.append(
            CraftingStep(
                action=f"Bench craft: {recipe.display}",
                instruction="\n".join(instruction_lines),
                metadata=metadata,
            )
        )

    for classification in unresolved_mods:
        mod = classification.mod
        instruction_lines = [
            f"No curated recipe was found for '{mod.text}'.",
            "Consider fossil crafting, eldritch implicits, or trading to obtain this modifier.",
        ]
        metadata = {
            "type": "gap",
            "covers_mods": [mod.text],
            "missing_source": True,
        }
        if classification.search_terms:
            metadata["search_terms"] = list(classification.search_terms)
        if mod.notes:
            instruction_lines.extend(mod.notes)
            metadata["notes"] = list(mod.notes)
        steps.append(
            CraftingStep(
                action=f"Research sourcing for '{mod.text}'",
                instruction="\n".join(instruction_lines),
                metadata=metadata,
            )
        )

    return steps


def assemble_plan_from_pob(items: Sequence[ItemBlueprint]) -> List[CraftingStep]:
    """Convert PoB item blueprints into a sequenced list of crafting steps."""

    plan: List[CraftingStep] = []
    for blueprint in items:
        plan.extend(_plan_for_blueprint(blueprint))
    return plan
