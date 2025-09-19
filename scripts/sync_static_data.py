#!/usr/bin/env python3
"""Download and curate static datasets for the POE MCP knowledge base."""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

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
        mod_texts: List[str] = []
        for mod_id in data.get("mods", []):
            mod = mods.get(mod_id)
            if mod:
                mod_texts.extend(translator.translate(mod.get("stats", [])))
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


def _clean_html(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"<.*?>", " ", text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return clean_wiki_markup(text)


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    cleaned = re.sub(r"[\r\n]+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    sentences = [part.strip() for part in parts if part.strip()]
    return sentences


def _normalise_keyword(text: str) -> List[str]:
    cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
    tokens = [token for token in cleaned.split() if token]
    return tokens


def _derive_currency_category(metadata_id: str) -> str:
    if not metadata_id:
        return ""
    slug = metadata_id.split("/")[-1]
    if slug.lower().startswith("currency"):
        slug = slug[len("currency") :]
    slug = re.sub(r"[_-]+", " ", slug)
    slug = re.sub(r"(?<!^)(?=[A-Z])", " ", slug)
    words = [word for word in slug.split() if word]
    formatted = " ".join(word.capitalize() if len(word) > 1 else word.upper() for word in words)
    return formatted or "Currency"


def fetch_currency_rows() -> List[dict]:
    fields = [
        "items._pageName=Name",
        "items.metadata_id=MetadataID",
        "items.description=Description",
        "items.explicit_stat_text=Explicit",
        "items.help_text=HelpText",
        "items.drop_text=DropText",
        "items.is_drop_restricted=DropRestricted",
        "items.name_list=Aliases",
    ]
    where = (
        "items.class_id='StackableCurrency'"
        " AND items.metadata_id LIKE 'Metadata/Items/Currency/%'"
        " AND items.frame_type='currency'"
    )
    params = {
        "action": "cargoquery",
        "tables": "items",
        "fields": ",".join(fields),
        "where": where,
        "order_by": "items._pageName",
        "limit": 500,
        "format": "json",
    }
    rows: List[dict] = []
    offset = 0
    while True:
        params["offset"] = offset
        response = requests.get(POEWIKI_API, params=params, headers=HEADERS, timeout=60)
        response.raise_for_status()
        data = response.json()
        chunk = data.get("cargoquery", [])
        if not chunk:
            break
        for entry in chunk:
            rows.append(entry.get("title", {}))
        if len(chunk) < params["limit"]:
            break
        offset += len(chunk)
    return rows


def sync_currency_data() -> None:
    raw_rows = fetch_currency_rows()
    curated: List[dict] = []
    seen: set[str] = set()
    for row in raw_rows:
        name = row.get("Name", "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        metadata_id = row.get("MetadataID", "").strip()
        category = _derive_currency_category(metadata_id)
        description = _clean_html(row.get("Description")) or _clean_html(row.get("Explicit"))
        help_text = _clean_html(row.get("HelpText"))
        drop_text = _clean_html(row.get("DropText"))
        drop_restricted = row.get("DropRestricted", "0")

        effect = description or "Unknown effect"
        restrictions = _split_sentences(help_text)
        if drop_text:
            restrictions.append(drop_text)
        if drop_restricted and drop_restricted != "0":
            restrictions.append("Drop-restricted item.")
        restrictions = [line for index, line in enumerate(restrictions) if line and line not in restrictions[:index]]

        alias_field = row.get("Aliases", "")
        aliases = [alias.strip() for alias in alias_field.replace("�", "|").split("|") if alias.strip() and alias.strip() != name]

        description_lines = [effect]
        description_lines.extend(restrictions)
        formatted_description = "\n".join(description_lines)

        keyword_sources = [name, category, effect, *aliases, *restrictions]
        keywords_set: List[str] = []
        seen_keywords: set[str] = set()
        for source in keyword_sources:
            cleaned = source.lower().strip()
            if cleaned and cleaned not in seen_keywords:
                keywords_set.append(cleaned)
                seen_keywords.add(cleaned)
            for token in _normalise_keyword(source):
                if token and token not in seen_keywords:
                    keywords_set.append(token)
                    seen_keywords.add(token)
        if metadata_id:
            meta_lower = metadata_id.lower()
            if meta_lower not in seen_keywords:
                keywords_set.append(meta_lower)
                seen_keywords.add(meta_lower)
            tail = metadata_id.split("/")[-1]
            for token in _normalise_keyword(tail):
                if token and token not in seen_keywords:
                    keywords_set.append(token)
                    seen_keywords.add(token)

        curated.append(
            {
                "name": name,
                "category": category,
                "effect": effect,
                "restrictions": restrictions,
                "description": formatted_description,
                "metadata_id": metadata_id,
                "aliases": aliases,
                "keywords": keywords_set,
            }
        )

    curated.sort(key=lambda entry: entry["name"].lower())
    write_json("currency.json", curated)


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
        choices=["bosses", "bench", "currency", "essences", "harvest"],
        nargs="*",
        help="Limit execution to selected sections.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    ensure_data_dir()
    translator = build_translator()

    sections = set(args.sections or ["bosses", "bench", "currency", "essences", "harvest"])
    if "bench" in sections:
        LOGGER.info("Syncing crafting bench options...")
        sync_bench_data(translator)
    if "currency" in sections:
        LOGGER.info("Syncing currency data...")
        sync_currency_data()
    if "essences" in sections:
        LOGGER.info("Syncing essences...")
        sync_essence_data(translator)
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
