"""Import utilities for Path of Building (PoB) build strings."""
from __future__ import annotations

import base64
import binascii
import zlib
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - optional dependency
    from lxml import etree as ET
except ImportError:  # pragma: no cover - fallback when lxml is missing
    import xml.etree.ElementTree as ET  # type: ignore[no-redef]


def parse_pob_build(encoded: str) -> Dict[str, Any]:
    """Decode and parse a PoB build string.

    Parameters
    ----------
    encoded:
        The base64-encoded PoB build string.

    Returns
    -------
    dict
        A dictionary containing the character information, passive tree,
        and the items found in the build export.

    Raises
    ------
    ValueError
        If the data cannot be decoded, decompressed, or parsed as XML.
    """

    if not isinstance(encoded, str):  # pragma: no cover - defensive
        raise TypeError("encoded build must be a string")

    cleaned = "".join(encoded.split())

    try:
        compressed = base64.b64decode(cleaned, validate=True)
    except (binascii.Error, ValueError) as exc:  # pragma: no cover - actual branch
        raise ValueError("Invalid base64-encoded PoB string") from exc

    try:
        xml_bytes = zlib.decompress(compressed)
    except zlib.error as exc:
        raise ValueError("Unable to decompress PoB data") from exc

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:  # type: ignore[attr-defined]
        raise ValueError("Unable to parse PoB XML data") from exc

    return {
        "character": extract_character(root),
        "tree": extract_tree(root),
        "items": extract_items(root),
    }


def extract_character(xml_root: ET.Element) -> Dict[str, Any]:
    """Return the character attributes from the XML tree."""

    build = xml_root.find("Build")
    if build is None:
        return {}

    return {key: _coerce_value(value) for key, value in build.attrib.items()}


def extract_tree(xml_root: ET.Element) -> Dict[str, Any]:
    """Return the passive tree information from the XML tree."""

    tree = xml_root.find("Tree")
    if tree is None:
        return {}

    spec = tree.find("Spec")
    if spec is None:
        return {}

    data: Dict[str, Any] = {
        key: _coerce_value(value)
        for key, value in spec.attrib.items()
        if key != "nodes"
    }

    data["nodes"] = _parse_nodes(spec.get("nodes"))

    url = spec.findtext("URL")
    if url:
        data["url"] = url.strip()

    return data


def extract_items(xml_root: ET.Element) -> List[Dict[str, Any]]:
    """Return a list of items encoded in the PoB XML tree."""

    items_section = xml_root.find("Items")
    if items_section is None:
        return []

    items: List[Dict[str, Any]] = []
    for item in items_section.findall("Item"):
        entry = {
            "id": item.get("id"),
            "slot": item.get("slot"),
        }
        parsed_text = _parse_item_text(item.text or "")
        entry.update(parsed_text)
        items.append(entry)

    return items


def _parse_nodes(value: Optional[str]) -> List[int]:
    if not value:
        return []

    nodes: List[int] = []
    for node in value.split(","):
        node = node.strip()
        if not node:
            continue
        try:
            nodes.append(int(node))
        except ValueError:
            continue
    return nodes


def _parse_item_text(text: str) -> Dict[str, Any]:
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    header: List[str] = []
    body_start = 0
    for idx, line in enumerate(lines):
        if line == "--------":
            body_start = idx + 1
            break
        header.append(line)
    else:
        body_start = len(lines)

    rarity: Optional[str] = None
    name: Optional[str] = None
    base_type: Optional[str] = None

    for line in header:
        if line.startswith("Rarity:"):
            rarity = line.split(":", 1)[1].strip()
        elif name is None:
            name = line
        elif base_type is None:
            base_type = line

    if base_type is None:
        base_type = name

    sockets: List[List[str]] = []
    affixes = {"prefixes": [], "suffixes": []}

    for line in lines[body_start:]:
        if line.startswith("Sockets:"):
            sockets = _parse_socket_groups(line.split(":", 1)[1].strip())
        elif line.startswith("Prefix:"):
            affixes["prefixes"].append(line.split(":", 1)[1].strip())
        elif line.startswith("Suffix:"):
            affixes["suffixes"].append(line.split(":", 1)[1].strip())

    return {
        "name": name,
        "base_type": base_type,
        "rarity": rarity,
        "sockets": sockets,
        "affixes": affixes,
    }


def _parse_socket_groups(socket_line: str) -> List[List[str]]:
    if not socket_line:
        return []

    groups: List[List[str]] = []
    for group in socket_line.split(" "):
        group = group.strip()
        if not group:
            continue
        if "(" in group:
            group = group.split("(", 1)[0].strip()
        sockets = [socket for socket in group.split("-") if socket]
        if sockets:
            groups.append(sockets)
    return groups


def _coerce_value(value: Optional[str]) -> Any:
    if value is None:
        return None

    for converter in (_to_int, _to_float):
        converted = converter(value)
        if converted is not None:
            return converted
    return value


def _to_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: str) -> Optional[float]:
    try:
        if value.count(".") == 1 and any(ch.isdigit() for ch in value):
            return float(value)
    except (TypeError, ValueError):
        return None
    return None


def _clean_line(line: str) -> str:
    return line.strip("\n\r ")


__all__ = [
    "parse_pob_build",
    "extract_character",
    "extract_tree",
    "extract_items",
]
