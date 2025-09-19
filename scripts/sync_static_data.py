#!/usr/bin/env python3
"""Download and curate static datasets for the POE MCP knowledge base."""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import requests

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
HEADERS = {"User-Agent": "poe-mcp-static-sync/1.0"}
POEWIKI_EXPORT = "https://www.poewiki.net/w/index.php"
POEWIKI_API = "https://www.poewiki.net/w/api.php"
REPOE_BASE = "https://raw.githubusercontent.com/brather1ng/RePoE/master/RePoE/data"

LOGGER = logging.getLogger("sync_static_data")


@dataclass
class StatTranslation:
    ids: Sequence[str]
    entries: Sequence[dict]


class StatTranslator:
    """Convert RePoE stat definitions into human readable strings."""

    def __init__(self, translations: Sequence[dict]) -> None:
        self._multi: dict[tuple[str, ...], List[dict]] = {}
        self._single: dict[str, List[dict]] = {}
        for entry in translations:
            ids = tuple(entry.get("ids", []))
            if not ids:
                continue
            english_entries = entry.get("English", [])
            if not english_entries:
                continue
            self._multi.setdefault(ids, []).extend(english_entries)
            for stat_id in ids:
                self._single.setdefault(stat_id, []).extend(english_entries)

    def _format_number(self, value: float | int) -> str:
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        if isinstance(value, float):
            text = f"{value:.2f}".rstrip("0").rstrip(".")
            return text or "0"
        return str(value)

    def _format_value(self, stat: dict, fmt: str) -> str:
        fmt = fmt or "#"
        fmt_lower = fmt.lower()
        if fmt_lower == "ignore":
            return ""
        min_value = stat.get("min")
        max_value = stat.get("max")
        if min_value is None and max_value is None:
            value = stat.get("value", 0)
            min_value = max_value = value
        if min_value is None:
            min_value = max_value
        if max_value is None:
            max_value = min_value
        if min_value == max_value:
            base = self._format_number(min_value)
        else:
            base = f"{self._format_number(min_value)}-{self._format_number(max_value)}"
        prefix = ""
        suffix = ""
        if fmt_lower.endswith("%"):
            suffix = "%"
            fmt_lower = fmt_lower[:-1]
        if fmt_lower.startswith("+"):
            prefix = "+"
            fmt_lower = fmt_lower[1:]
        if fmt_lower in {"# to #", "#to#"}:
            base = f"{self._format_number(min_value)} to {self._format_number(max_value)}"
        return f"{prefix}{base}{suffix}".strip()

    def _translate_entry(self, stats: Sequence[dict], english: dict) -> str:
        fmt = english.get("format", [])
        if not fmt:
            return english.get("string", "").strip()
        values = []
        for index, fmt_spec in enumerate(fmt):
            source = stats[min(index, len(stats) - 1)]
            values.append(self._format_value(source, fmt_spec))
        template = english.get("string", "")
        try:
            text = template.format(*values)
        except Exception:  # pragma: no cover - defensive for rare translation combos
            text = template + " " + " ".join(v for v in values if v)
        return text.strip()

    def translate(self, stats: Sequence[dict]) -> List[str]:
        if not stats:
            return []
        stat_ids = tuple(stat.get("id") for stat in stats)
        matches = self._multi.get(stat_ids)
        if matches:
            return [self._translate_entry(stats, matches[0])]
        rendered: List[str] = []
        for stat in stats:
            options = self._single.get(stat.get("id"), [])
            if options:
                rendered.append(self._translate_entry([stat], options[0]))
            else:
                value_text = self._format_value(stat, "#")
                rendered.append(f"{stat.get('id')} {value_text}".strip())
        return [line for line in rendered if line]


def fetch_json(url: str) -> object:
    LOGGER.debug("GET %s", url)
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    if response.headers.get("Content-Type", "").startswith("application/json"):
        return response.json()
    return json.loads(response.text)


def fetch_cargo_rows(table: str, fields: str, where: str | None = None) -> List[dict]:
    """Query the PoE Wiki Cargo API and return rows for a table."""

    rows: List[dict] = []
    limit = 500
    offset = 0
    while True:
        params = {
            "action": "cargoquery",
            "format": "json",
            "tables": table,
            "fields": fields,
            "limit": limit,
            "offset": offset,
        }
        if where:
            params["where"] = where
        LOGGER.debug("Cargo %s offset %s", table, offset)
        response = requests.get(POEWIKI_API, params=params, headers=HEADERS, timeout=60)
        response.raise_for_status()
        data = response.json()
        chunk = data.get("cargoquery", [])
        if not chunk:
            break
        for entry in chunk:
            title = entry.get("title", {})
            if title:
                rows.append(title)
        if len(chunk) < limit:
            break
        offset += len(chunk)
    return rows


def dedupe_strings(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for raw in items:
        if not raw:
            continue
        text = str(raw).strip()
        if not text:
            continue
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def collect_keywords(*values: object) -> List[str]:
    terms: set[str] = set()

    def _handle(value: object) -> None:
        if not value:
            return
        if isinstance(value, str):
            terms.add(value.lower())
        elif isinstance(value, Iterable):
            for entry in value:
                _handle(entry)
        else:
            terms.add(str(value).lower())

    for value in values:
        _handle(value)
    return sorted(terms)


def humanise_descriptor(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[_\s]+", " ", text)
    cleaned = re.sub(r"(?<=[a-z0-9])([A-Z])", r" \1", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().capitalize()


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def write_json(name: str, payload: object) -> None:
    path = DATA_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    LOGGER.info("Wrote %s", path)


def build_translator() -> StatTranslator:
    stats_url = f"{REPOE_BASE}/stat_translations.min.json"
    translations = fetch_json(stats_url)
    return StatTranslator(translations)


def sync_bench_data(translator: StatTranslator) -> None:
    bench_url = f"{REPOE_BASE}/crafting_bench_options.min.json"
    mods_url = f"{REPOE_BASE}/mods.min.json"
    base_items_url = f"{REPOE_BASE}/base_items.min.json"
    bench_entries = fetch_json(bench_url)
    mods = fetch_json(mods_url)
    base_items = fetch_json(base_items_url)

    colour_map = {"R": "red", "G": "green", "B": "blue", "W": "white"}
    curated: List[dict] = []
    for entry in bench_entries:
        actions = entry.get("actions", {})
        identifier = None
        display = ""
        keywords: List[str] = []
        if "add_explicit_mod" in actions:
            identifier = actions["add_explicit_mod"]
            mod = mods.get(identifier)
            if not mod:
                continue
            lines = translator.translate(mod.get("stats", []))
            display = "; ".join(lines) or identifier
            keywords.extend([identifier.lower(), *(line.lower() for line in lines)])
        elif "add_enchant_mod" in actions:
            identifier = actions["add_enchant_mod"]
            mod = mods.get(identifier)
            if not mod:
                continue
            lines = translator.translate(mod.get("stats", []))
            display = "; ".join(lines) or identifier
            keywords.extend([identifier.lower(), *(line.lower() for line in lines)])
        elif "change_socket_count" in actions:
            count = actions["change_socket_count"]
            display = f"Set number of sockets to {count}"
            keywords.extend(["socket", f"{count}-socket"])
        elif "color_sockets" in actions:
            colour = actions["color_sockets"]
            colour_name = colour_map.get(colour, str(colour))
            display = f"Force a {colour_name} socket"
            keywords.extend(["colour", colour_name])
        elif "link_sockets" in actions:
            links = actions["link_sockets"]
            display = f"Link {links} sockets"
            keywords.extend(["link", f"{links}-link"])
        elif "remove_crafted_mods" in actions:
            display = "Remove crafted modifiers"
            keywords.extend(["remove crafted", "craft remove"])
        elif "remove_enchantments" in actions:
            display = "Remove enchantments"
            keywords.extend(["remove enchant", "enchant"])
        else:
            identifier = next(iter(actions.values()), None)
            display = ", ".join(f"{key}: {value}" for key, value in actions.items())
            keywords.extend(actions.keys())
        if not identifier:
            identifier = f"{entry.get('master','Unknown')}::{display}"

        costs = []
        for metadata_id, amount in entry.get("cost", {}).items():
            base = base_items.get(metadata_id, {})
            currency_name = base.get("name") or metadata_id.split("/")[-1]
            costs.append({"currency": currency_name, "amount": amount})

        curated.append(
            {
                "identifier": identifier,
                "display": display,
                "description": display,
                "bench_tier": entry.get("bench_tier", 0),
                "master": entry.get("master", "Unknown"),
                "item_classes": entry.get("item_classes", []),
                "action": next(iter(actions.keys()), "unknown"),
                "keywords": keywords,
                "costs": costs,
            }
        )

    write_json("bench_recipes.json", curated)


def sync_essence_data(translator: StatTranslator) -> None:
    essences_url = f"{REPOE_BASE}/essences.min.json"
    mods_url = f"{REPOE_BASE}/mods.min.json"
    essences_raw = fetch_json(essences_url)
    mods = fetch_json(mods_url)
    curated: List[dict] = []
    for identifier, data in essences_raw.items():
        raw_mods = data.get("mods") or {}
        if isinstance(raw_mods, dict):
            mod_ids_iterable = raw_mods.values()
        else:
            mod_ids_iterable = raw_mods

        mod_ids = dedupe_strings(mod_ids_iterable)
        mod_texts: List[str] = []
        for mod_id in mod_ids:
            mod = mods.get(mod_id)
            if not mod:
                continue
            translations = translator.translate(mod.get("stats", []))
            if translations:
                mod_texts.extend(translations)
            else:
                mod_texts.append(mod_id)
        mod_texts = dedupe_strings(mod_texts)
        tier = data.get("name", "").split(" Essence ")[0]
        curated.append(
            {
                "identifier": identifier,
                "name": data.get("name", identifier),
                "tier": tier,
                "level": data.get("level", 0),
                "type": data.get("type", ""),
                "mods": mod_texts,
                "item_level_restriction": data.get("item_level_restriction"),
                "spawn_level_min": data.get("spawn_level_min"),
                "spawn_level_max": data.get("spawn_level_max"),
            }
        )
    write_json("essences.json", curated)


def clean_wiki_markup(text: str) -> str:
    text = re.sub(r"\{\{.*?\}\}", "", text)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"''+", "", text)
    text = re.sub(r"^[*#\s]+", "", text)
    return text.strip()


def fetch_map_rows() -> List[dict]:
    params = {
        "title": "Special:CargoExport",
        "tables": "maps",
        "fields": "maps._pageName=Map,maps.tier,maps.series",
        "where": "maps.tier>0",
        "limit": 500,
        "format": "json",
    }
    rows: List[dict] = []
    offset = 0
    while True:
        params["offset"] = offset
        response = requests.get(POEWIKI_EXPORT, params=params, headers=HEADERS, timeout=60)
        response.raise_for_status()
        chunk = response.json()
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < params["limit"]:
            break
        offset += len(chunk)
    return rows


def fetch_wikitext(title: str) -> str | None:
    params = {"action": "parse", "page": title, "prop": "wikitext", "format": "json"}
    response = requests.get(POEWIKI_API, params=params, headers=HEADERS, timeout=60)
    if response.status_code != 200:
        return None
    data = response.json()
    return data.get("parse", {}).get("wikitext", {}).get("*")


def extract_map_boss_info(title: str, tier: int) -> dict | None:
    wikitext = fetch_wikitext(title)
    if not wikitext:
        return None
    section_split = wikitext.split("==Boss==", 1)
    bosses: List[str] = []
    unlock: List[str] = []
    if len(section_split) > 1:
        boss_section = section_split[1].split("==", 1)[0]
        for chunk in boss_section.split("[[")[1:]:
            name = chunk.split("]]", 1)[0]
            cleaned = clean_wiki_markup(name)
            if cleaned:
                bosses.append(cleaned)
        lines = [clean_wiki_markup(line) for line in boss_section.splitlines() if line.strip()]
        keywords = ("access", "require", "obtain", "fragment", "invitation", "witness")
        for line in lines:
            lower = line.lower()
            if any(word in lower for word in keywords):
                unlock.append(line)
                if len(unlock) >= 2:
                    break
    bosses = list(dict.fromkeys(bosses))
    return {
        "map": title,
        "tier": tier,
        "bosses": bosses or ["Unknown"],
        "unlock": unlock,
    }


SPECIAL_BOSSES = [
    {"name": "The Maven", "page": "The_Maven", "encounter": "Maven's Crucible", "aliases": ["maven", "maven's crucible"]},
    {"name": "Sirus, Awakener of Worlds", "page": "Sirus,_Awakener_of_Worlds", "encounter": "Eye of the Storm", "aliases": ["sirus", "awakener"]},
    {"name": "The Shaper", "page": "The_Shaper", "encounter": "The Shaper's Realm", "aliases": ["shaper"]},
    {"name": "The Elder", "page": "The_Elder", "encounter": "The Elder", "aliases": ["elder"]},
    {"name": "The Uber Elder", "page": "The_Shaper_and_the_Elder", "encounter": "Uber Elder", "aliases": ["uber elder"]},
    {"name": "The Eater of Worlds", "page": "The_Eater_of_Worlds", "encounter": "Absence of Symmetry and Harmony", "aliases": ["eater"]},
    {"name": "The Searing Exarch", "page": "The_Searing_Exarch", "encounter": "Absence of Patience and Wisdom", "aliases": ["exarch", "searing exarch"]},
]


def extract_special_boss(entry: dict) -> dict:
    wikitext = fetch_wikitext(entry["page"])
    lines = []
    notes = []
    if wikitext:
        raw_lines = [clean_wiki_markup(line) for line in wikitext.splitlines() if line.strip()]
        keywords = ("access", "unlock", "requires", "fragment", "invitation", "witness", "writ", "collect")
        for line in raw_lines:
            lower = line.lower()
            if any(word in lower for word in keywords):
                lines.append(line)
            elif "reward" in lower or "drops" in lower:
                notes.append(line)
            if len(lines) >= 3 and len(notes) >= 2:
                break
    return {
        "name": entry["name"],
        "aliases": entry.get("aliases", []),
        "encounter": entry.get("encounter", entry["name"]),
        "unlock": lines,
        "notes": notes[:3],
    }


def sync_boss_data() -> None:
    rows = fetch_map_rows()
    curated_maps: List[dict] = []
    chosen: dict[str, dict] = {}
    for row in rows:
        title = row.get("Map")
        if not title:
            continue
        base_title = title
        if base_title.startswith("Map:"):
            base_title = base_title[4:]
        if " (" in base_title:
            base_title = base_title.split(" (", 1)[0]
        if base_title.startswith("Shaped "):
            base_title = base_title[len("Shaped "):]
        if base_title.startswith("Elder "):
            base_title = base_title[len("Elder "):]
        base_title = base_title.replace("_", " ")
        series = row.get("series", "")
        tier = int(row.get("tier", 0))
        if series == "Settlers" and tier < 14:
            continue
        if series not in {"Settlers", "Mercenaries"}:
            continue
        priority = 1 if series == "Settlers" else 0
        current = chosen.get(base_title)
        if current is None or priority > current["priority"]:
            chosen[base_title] = {"title": base_title, "tier": tier, "priority": priority}
    for selection in chosen.values():
        info = extract_map_boss_info(selection["title"], selection["tier"])
        if info:
            curated_maps.append(info)
    atlas_bosses = [extract_special_boss(entry) for entry in SPECIAL_BOSSES]
    payload = {"atlas_bosses": atlas_bosses, "map_bosses": curated_maps}
    write_json("bosses.json", payload)


def sync_crafting_methods(translator: StatTranslator) -> None:
    fossils_url = f"{REPOE_BASE}/fossils.min.json"
    mods_url = f"{REPOE_BASE}/mods.min.json"
    base_items_url = f"{REPOE_BASE}/base_items.min.json"
    fossils_raw: Dict[str, dict] = fetch_json(fossils_url)
    mods: Dict[str, dict] = fetch_json(mods_url)
    base_items: Dict[str, dict] = fetch_json(base_items_url)

    def parse_notes(value: str | None) -> List[str]:
        if not value:
            return []
        text = html.unescape(value)
        text = text.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
        segments: List[str] = []
        for chunk in text.split("\n"):
            for part in chunk.split(";"):
                cleaned = part.strip()
                if cleaned:
                    segments.append(cleaned)
        return dedupe_strings(segments)

    def parse_int(value: object, default: int = 1) -> int:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return default

    fossils_payload: List[dict] = []
    for identifier, entry in sorted(fossils_raw.items(), key=lambda item: item[1].get("name", "")):
        name = entry.get("name") or identifier.split("/")[-1]
        effect_lines: List[str] = list(entry.get("descriptions", []))
        for mod_id in [*entry.get("added_mods", []), *entry.get("forced_mods", [])]:
            mod = mods.get(mod_id)
            if not mod:
                continue
            effect_lines.extend(translator.translate(mod.get("stats", [])))
        positive_tags = sorted({weight.get("tag") for weight in entry.get("positive_mod_weights", []) if weight.get("tag")})
        if positive_tags:
            effect_lines.append(f"Favors {', '.join(positive_tags)} modifiers")
        negative_tags = sorted({weight.get("tag") for weight in entry.get("negative_mod_weights", []) if weight.get("tag")})
        if negative_tags:
            effect_lines.append(f"Suppresses {', '.join(negative_tags)} modifiers")
        if entry.get("rolls_lucky"):
            effect_lines.append("Rolls are lucky")
        if entry.get("rolls_white_sockets"):
            effect_lines.append("Can roll white sockets")
        if entry.get("changes_quality"):
            effect_lines.append("Modifies item quality")
        effects = dedupe_strings(effect_lines)

        constraints: List[str] = []
        allowed_tags = entry.get("allowed_tags", [])
        if allowed_tags:
            constraints.append(f"Allowed item tags: {', '.join(sorted(allowed_tags))}")
        forbidden_tags = entry.get("forbidden_tags", [])
        if forbidden_tags:
            constraints.append(f"Forbidden item tags: {', '.join(sorted(forbidden_tags))}")
        blocked_descriptions = [humanise_descriptor(desc) for desc in entry.get("blocked_descriptions", [])]
        if blocked_descriptions:
            constraints.append(f"Blocks: {', '.join(blocked_descriptions)}")
        if entry.get("corrupted_essence_chance"):
            chance = entry.get("corrupted_essence_chance")
            constraints.append(f"{chance}% chance to corrupt Essence outcomes")
        constraints = dedupe_strings(constraints)

        fossils_payload.append(
            {
                "identifier": identifier,
                "name": name,
                "effects": effects,
                "constraints": constraints,
                "keywords": collect_keywords(name, effects, constraints, identifier),
            }
        )
    fossils_payload.sort(key=lambda item: item["name"].lower())

    resonators_payload: List[dict] = []
    for identifier, entry in base_items.items():
        name = entry.get("name", "")
        if "Resonator" not in name:
            continue
        properties = entry.get("properties", {}) or {}
        description = properties.get("description", "")
        directions = properties.get("directions", "")
        socket_match = re.search(r"(\d+)$", identifier)
        sockets = int(socket_match.group(1)) if socket_match else 1
        resonators_payload.append(
            {
                "identifier": identifier,
                "name": name,
                "sockets": sockets,
                "description": description,
                "directions": directions,
                "keywords": collect_keywords(name, description, directions, f"{sockets}-socket"),
            }
        )
    resonators_payload.sort(key=lambda item: (item["sockets"], item["name"].lower()))

    recipes = fetch_cargo_rows(
        "bestiary_recipes",
        "id=id,header=header,subheader=subheader,notes=notes,game_mode=game_mode",
    )
    component_rows = fetch_cargo_rows(
        "bestiary_recipe_components",
        "recipe_id=recipe_id,component_id=component_id,amount=amount",
    )
    beast_rows = fetch_cargo_rows(
        "bestiary_components",
        "id=id,monster=monster,rarity=rarity,beast_group=beast_group,family=family,genus=genus",
    )

    components_by_recipe: Dict[str, List[dict]] = defaultdict(list)
    for component in component_rows:
        recipe_id = component.get("recipe_id")
        if not recipe_id:
            continue
        components_by_recipe[recipe_id].append(component)

    beast_lookup = {entry.get("id"): entry for entry in beast_rows if entry.get("id")}
    game_mode_labels = {"1": "Standard", "2": "Ruthless"}
    beastcraft_payload: List[dict] = []
    for recipe in recipes:
        recipe_id = recipe.get("id")
        if not recipe_id:
            continue
        header = html.unescape(recipe.get("header", ""))
        result = html.unescape(recipe.get("subheader", ""))
        notes = parse_notes(recipe.get("notes"))
        game_mode = game_mode_labels.get(str(recipe.get("game_mode")), "Any")
        beasts: List[dict] = []
        for component in components_by_recipe.get(recipe_id, []):
            component_id = component.get("component_id", "")
            info = beast_lookup.get(component_id, {})
            name = info.get("monster") or info.get("genus") or info.get("family") or humanise_descriptor(component_id)
            beasts.append(
                {
                    "id": component_id,
                    "name": name,
                    "rarity": info.get("rarity"),
                    "family": info.get("family"),
                    "genus": info.get("genus"),
                    "group": info.get("beast_group"),
                    "quantity": parse_int(component.get("amount"), 1),
                }
            )
        beasts.sort(key=lambda item: (item["name"], item["id"]))
        beastcraft_payload.append(
            {
                "id": recipe_id,
                "header": header,
                "result": result,
                "notes": notes,
                "game_mode": game_mode,
                "beasts": beasts,
                "keywords": collect_keywords(recipe_id, header, result, notes, [beast["name"] for beast in beasts]),
            }
        )
    beastcraft_payload.sort(key=lambda item: (item["header"].lower(), item["result"].lower()))

    raw_betrayal_entries = [
        {
            "member": "Aisling Laffrey",
            "division": "Research",
            "rank": 4,
            "ability": "Add a Veiled modifier",
            "summary": "Slams a random Veiled prefix or suffix and removes an existing crafted modifier.",
            "requirements": [
                "Unlock by defeating Aisling as Research safehouse leader (rank 4).",
                "Target item must be rare with an open prefix or suffix.",
            ],
        },
        {
            "member": "Hillock",
            "division": "Fortification",
            "rank": 3,
            "ability": "Quality bench",
            "summary": "Boosts quality on weapons, armour, or flasks depending on item type (up to 30%).",
            "requirements": [
                "Encounter Hillock as Fortification safehouse leader (rank 3).",
                "Applies to the item type Hillock inspected in the safehouse encounter.",
            ],
        },
        {
            "member": "Vorici",
            "division": "Research",
            "rank": 3,
            "ability": "White socket bench",
            "summary": "Allows forcing 1-3 white sockets on an item at the cost of a level 8 bench craft.",
            "requirements": [
                "Unlock Vorici in the Research safehouse at rank 3 or higher.",
                "Costs 25 Vaal Orbs for three white sockets.",
            ],
        },
        {
            "member": "Tora",
            "division": "Research",
            "rank": 3,
            "ability": "Gem experience bench",
            "summary": "Grants large amounts of experience to socketed gems (up to level 20).",
            "requirements": [
                "Complete the Research safehouse with Tora at rank 3.",
                "Socket target gems into the bench before activating.",
            ],
        },
        {
            "member": "Jorgin",
            "division": "Research",
            "rank": 3,
            "ability": "Talisman imprint",
            "summary": "Imprints a Talisman onto an amulet, transforming it into that talisman with retained quality.",
            "requirements": [
                "Encounter Jorgin as Research safehouse leader at rank 3.",
                "Consumes the input amulet and chosen talisman.",
            ],
        },
    ]

    betrayal_payload: List[dict] = []
    for entry in raw_betrayal_entries:
        requirements = dedupe_strings(entry.get("requirements", []))
        payload_entry = {
            **entry,
            "requirements": requirements,
            "keywords": collect_keywords(entry.get("member"), entry.get("division"), entry.get("ability"), entry.get("summary"), requirements),
        }
        betrayal_payload.append(payload_entry)
    betrayal_payload.sort(key=lambda item: (item["division"], item["member"]))

    raw_strategies = [
        {
            "name": "Multimodding",
            "summary": "Use the bench craft 'Can have up to 3 Crafted Modifiers' to stack powerful crafts.",
            "requirements": [
                "Unlock Jun's rank 3 unveiling for the multimod craft.",
                "Item must be rare with at least two open modifier slots.",
                "Costs 2 Divine Orbs to apply the craft in current leagues.",
            ],
            "best_for": [
                "Meta-crafting influenced rares where specific crafted prefixes/suffixes are required.",
                "Items that already have strong natural modifiers but need crafted fillers.",
            ],
            "steps": [
                "Apply the multimod craft at the crafting bench.",
                "Add two additional crafted modifiers to fill remaining affix slots.",
                "Remove the multimod craft later if you need to reroll or replace crafts.",
            ],
        },
        {
            "name": "Alteration/Augmentation Spamming",
            "summary": "Roll blue items with Orbs of Alteration and finish with Augmentation/Regal when you hit target mods.",
            "requirements": [
                "Base item of the correct item level.",
                "Access to a large stack of Orbs of Alteration and Augmentation.",
            ],
            "best_for": [
                "Targeting specific prefixes or suffixes on single-mod bases such as amulets or belts.",
                "Preparing for metamods like 'Prefixes Cannot Be Changed' before further crafting.",
            ],
            "steps": [
                "Use Alteration Orbs until one desired mod appears.",
                "Use an Augmentation Orb if you need the opposite affix type.",
                "Regal the item to rare and evaluate whether to continue, annul, or restart.",
            ],
        },
        {
            "name": "Chaos Spamming",
            "summary": "Apply Chaos Orbs repeatedly to reroll all modifiers until the item meets your minimum requirements.",
            "requirements": [
                "Rare item of the appropriate item level.",
                "A supply of Chaos Orbs (or Harvest reforges) for repeated attempts.",
            ],
            "best_for": [
                "Early- and mid-game rares when deterministic options are not unlocked.",
                "Bases with broad desired mod pools (e.g., life + resist armour).",
            ],
            "steps": [
                "Spam Chaos Orbs or Harvest 'Reforge with lucky modifiers' crafts.",
                "Stop when mandatory stats roll acceptably, then bench-craft missing values.",
            ],
        },
        {
            "name": "Essence Spamming",
            "summary": "Lock in a specific powerful modifier by applying the same Essence repeatedly.",
            "requirements": [
                "Essence of the desired tier (Screaming, Deafening, etc.).",
                "Base item that can roll the forced modifier (check item level).",
            ],
            "best_for": [
                "Items where one mod provides the majority of value (e.g., Essence of Greed life rolls).",
                "Combining with bench crafts or Harvest reforges to finish prefixes/suffixes.",
            ],
            "steps": [
                "Apply the Essence to guarantee the key modifier.",
                "Evaluate the remaining mods; consider Harvest reforges to fix the opposite affix type.",
                "Finish with bench crafts or meta-crafting once satisfied.",
            ],
        },
    ]

    strategies_payload: List[dict] = []
    for entry in raw_strategies:
        best_for = dedupe_strings(entry.get("best_for", []))
        steps = dedupe_strings(entry.get("steps", []))
        requirements = dedupe_strings(entry.get("requirements", []))
        strategies_payload.append(
            {
                **entry,
                "best_for": best_for,
                "steps": steps,
                "requirements": requirements,
                "keywords": collect_keywords(entry.get("name"), entry.get("summary"), best_for, steps, requirements),
            }
        )
    strategies_payload.sort(key=lambda item: item["name"].lower())

    raw_vendor_recipes = [
        {
            "name": "Chromatic Orb Recipe",
            "reward": "Chromatic Orb",
            "inputs": ["Item with linked red, green, and blue sockets"],
            "notes": ["Sockets must be linked.", "Item rarity does not matter."],
        },
        {
            "name": "Jeweller's Orb Recipe",
            "reward": "7 Jeweller's Orbs",
            "inputs": ["Any item with 6 sockets"],
            "notes": ["Item must be unidentified for double reward in Ruthless."],
        },
        {
            "name": "Orb of Fusing Recipe",
            "reward": "1 Orb of Fusing",
            "inputs": ["Any item with a 5-link"],
            "notes": ["Links must be on the same item; sockets can be any colour."],
        },
        {
            "name": "Chaos Orb Recipe",
            "reward": "Chaos Orb",
            "inputs": ["Full rare item set (ilvl 60-74)"],
            "notes": [
                "Include two rings, amulet, belt, gloves, boots, helmet, body armour, and weapon/shield.",
                "Unidentified set yields an extra Chaos Orb.",
            ],
        },
        {
            "name": "Regal Orb Recipe",
            "reward": "Regal Orb",
            "inputs": ["Full rare item set (ilvl 75+)"],
            "notes": ["Unidentified sets reward an extra Regal Orb.", "Most efficient when done with high level maps."],
        },
        {
            "name": "Gemcutter's Prism Recipe",
            "reward": "Gemcutter's Prism",
            "inputs": ["Sell gems whose total quality equals 40%"],
            "notes": ["Multiple gems can be combined to reach 40%.", "Works with any mix of skill and support gems."],
        },
    ]

    vendor_payload: List[dict] = []
    for entry in raw_vendor_recipes:
        inputs = dedupe_strings(entry.get("inputs", []))
        notes = dedupe_strings(entry.get("notes", []))
        vendor_payload.append(
            {
                **entry,
                "inputs": inputs,
                "notes": notes,
                "keywords": collect_keywords(entry.get("name"), entry.get("reward"), inputs, notes),
            }
        )
    vendor_payload.sort(key=lambda item: item["name"].lower())

    payload = {
        "fossils": fossils_payload,
        "resonators": resonators_payload,
        "beastcrafts": beastcraft_payload,
        "betrayal_benches": betrayal_payload,
        "strategies": strategies_payload,
        "vendor_recipes": vendor_payload,
    }
    write_json("crafting_methods.json", payload)


def sync_harvest_data(translator: StatTranslator) -> None:
    mods_url = f"{REPOE_BASE}/mods.min.json"
    mods = fetch_json(mods_url)
    curated: List[dict] = []
    for identifier, mod in mods.items():
        if not identifier.lower().startswith("harvest"):
            continue
        description = translator.translate(mod.get("stats", [])) or [identifier]
        curated.append(
            {
                "identifier": identifier,
                "description": description,
                "groups": mod.get("groups", []),
                "tags": list({*mod.get("adds_tags", []), *mod.get("implicit_tags", [])}),
                "item_classes": mod.get("item_classes", []),
            }
        )
    write_json("harvest_crafts.json", curated)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sections",
        choices=["bosses", "bench", "crafting_methods", "essences", "harvest"],
        nargs="*",
        help="Limit execution to selected sections.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    ensure_data_dir()
    translator = build_translator()

    sections = set(args.sections or ["bosses", "bench", "crafting_methods", "essences", "harvest"])
    if "bench" in sections:
        LOGGER.info("Syncing crafting bench options...")
        sync_bench_data(translator)
    if "essences" in sections:
        LOGGER.info("Syncing essences...")
        sync_essence_data(translator)
    if "crafting_methods" in sections:
        LOGGER.info("Syncing crafting methods...")
        sync_crafting_methods(translator)
    if "harvest" in sections:
        LOGGER.info("Syncing Harvest crafts...")
        sync_harvest_data(translator)
    if "bosses" in sections:
        LOGGER.info("Syncing boss data...")
        sync_boss_data()

    LOGGER.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
