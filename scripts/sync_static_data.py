#!/usr/bin/env python3
"""Download and curate static datasets for the POE MCP knowledge base."""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import requests

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
HEADERS = {"User-Agent": "poe-mcp-static-sync/1.0"}
POEWIKI_EXPORT = "https://www.poewiki.net/w/index.php"
POEWIKI_API = "https://www.poewiki.net/w/api.php"
REPOE_BASE = "https://raw.githubusercontent.com/brather1ng/RePoE/master/RePoE/data"
CARGO_PAGE_SIZE = 500
TARGET_VERSION = (3, 26)

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


def fetch_cargo_rows(
    table: str,
    fields: Sequence[str],
    where: str | None = None,
    order_by: str | None = None,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    offset = 0
    while True:
        params = {
            "title": "Special:CargoExport",
            "tables": table,
            "fields": ",".join(fields),
            "limit": CARGO_PAGE_SIZE,
            "offset": offset,
            "format": "csv",
        }
        if where:
            params["where"] = where
        if order_by:
            params["order_by"] = order_by
        response = requests.get(POEWIKI_EXPORT, params=params, headers=HEADERS, timeout=60)
        response.raise_for_status()
        text = response.text.strip()
        if not text:
            break
        reader = csv.DictReader(io.StringIO(text))
        chunk: List[Dict[str, str]] = []
        for row in reader:
            cleaned: Dict[str, str] = {}
            for key, value in row.items():
                if key is None:
                    continue
                if isinstance(value, str):
                    cleaned[key] = value.strip()
                else:
                    cleaned[key] = value
            if cleaned:
                chunk.append(cleaned)
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < CARGO_PAGE_SIZE:
            break
        offset += CARGO_PAGE_SIZE
    return rows


def _normalise_tags(raw: str) -> List[str]:
    tags = [tag.strip() for tag in (raw or "").split(",")]
    seen: Dict[str, None] = {}
    for tag in tags:
        if tag and tag not in seen:
            seen[tag] = None
    return list(seen.keys())


def _version_key_map() -> Dict[str, Tuple[int, int, int, Tuple[int, ...]]]:
    rows = fetch_cargo_rows(
        "versions",
        [
            "versions.version=version",
            "versions.major_part=major",
            "versions.minor_part=minor",
            "versions.patch_part=patch",
            "versions.revision_part=revision",
        ],
    )
    mapping: Dict[str, Tuple[int, int, int, Tuple[int, ...]]] = {}
    for row in rows:
        version = row.get("version", "").strip()
        if not version:
            continue
        major = int(row.get("major") or 0)
        minor = int(row.get("minor") or 0)
        patch = int(row.get("patch") or 0)
        revision_text = (row.get("revision") or "").strip()
        revision_key = tuple(ord(char) for char in revision_text)
        mapping[version] = (major, minor, patch, revision_key)
    return mapping


def _parse_version_key(version: str, mapping: Dict[str, Tuple[int, int, int, Tuple[int, ...]]]) -> Tuple[int, int, int, Tuple[int, ...]] | None:
    version = (version or "").strip()
    if not version:
        return None
    cached = mapping.get(version)
    if cached:
        return cached
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?(.*)$", version)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3) or 0)
    revision_text = match.group(4).strip()
    revision_key = tuple(ord(char) for char in revision_text)
    key = (major, minor, patch, revision_key)
    mapping[version] = key
    return key


def _is_removed(version_key: Tuple[int, int, int, Tuple[int, ...]] | None) -> bool:
    if version_key is None:
        return False
    major, minor, patch, revision = version_key
    target_major, target_minor = TARGET_VERSION
    if major < target_major:
        return True
    if major > target_major:
        return False
    if minor < target_minor:
        return True
    if minor > target_minor:
        return False
    # Removal during target cycle counts as removed for catalogue purposes.
    return True


def _parse_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def _clean_text(raw: str | None) -> str:
    text = html.unescape(raw or "")
    text = text.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\n", "; ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ;")


def sync_currency_data() -> None:
    version_map = _version_key_map()
    rows = fetch_cargo_rows(
        "items",
        [
            "items.metadata_id=metadata_id",
            "items.name=name",
            "items.tags=tags",
            "items.description=action",
            "items.help_text=constraints",
            "items.release_version=release_version",
            "items.removal_version=removal_version",
            "items.is_in_game=is_in_game",
        ],
        where='items.frame_type="currency" AND items.tags HOLDS "currency"',
        order_by="items.name",
    )

    entries: List[dict] = []
    seen_ids: set[str] = set()
    target_revision_ceiling: Tuple[int, int, int, Tuple[int, ...]] = (
        TARGET_VERSION[0],
        TARGET_VERSION[1],
        999,
        (255,),
    )

    for row in rows:
        metadata_id = row.get("metadata_id", "").strip()
        name = row.get("name", "").strip()
        if not name:
            continue
        if metadata_id:
            if metadata_id in seen_ids:
                continue
            seen_ids.add(metadata_id)
        if not _parse_bool(row.get("is_in_game")):
            continue
        release_key = _parse_version_key(row.get("release_version"), version_map)
        if release_key and release_key > target_revision_ceiling:
            continue
        removal_key = _parse_version_key(row.get("removal_version"), version_map)
        if _is_removed(removal_key):
            continue
        entry = {
            "metadata_id": metadata_id or None,
            "name": name,
            "tags": _normalise_tags(row.get("tags", "")),
            "action": _clean_text(row.get("action")),
            "constraints": _clean_text(row.get("constraints")),
            "release_version": (row.get("release_version") or "").strip() or None,
            "removal_version": (row.get("removal_version") or "").strip() or None,
        }
        entries.append(entry)

    entries.sort(key=lambda item: item["name"].lower())
    write_json("currency.json", entries)


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
    if "essences" in sections:
        LOGGER.info("Syncing essences...")
        sync_essence_data(translator)
    if "harvest" in sections:
        LOGGER.info("Syncing Harvest crafts...")
        sync_harvest_data(translator)
    if "currency" in sections:
        LOGGER.info("Syncing currency catalogue...")
        sync_currency_data()
    if "bosses" in sections:
        LOGGER.info("Syncing boss data...")
        sync_boss_data()

    LOGGER.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
