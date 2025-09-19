import base64
import pathlib
import sys
import zlib

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from poe_mcp_server.pob import extract_character, extract_items, extract_tree, parse_pob_build

try:  # pragma: no cover - align with importer
    from lxml import etree as ET
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as ET  # type: ignore[no-redef]


@pytest.fixture()
def pob_string() -> str:
    xml = """
    <PathOfBuilding>
      <Build level=\"90\" className=\"Templar\" ascendClassName=\"Inquisitor\" mainSkill=\"Arc\" />
      <Tree>
        <Spec nodes=\"1,2,3,4\" classId=\"3\" ascendClassId=\"2\">
          <URL>https://example.com/tree</URL>
        </Spec>
      </Tree>
      <Items>
        <Item id=\"1\" slot=\"Weapon\">
    Rarity: Rare
    Storm Chant
    Imbued Wand
    --------
    Sockets: B-G-B
    --------
    Prefix: {range:0}Glowing
    Suffix: {range:0}of Lightning
        </Item>
        <Item id=\"2\" slot=\"Ring\">
    Rarity: Unique
    Berek's Grip
    Two-Stone Ring
    --------
    Suffix: {range:0}of Power
        </Item>
      </Items>
    </PathOfBuilding>
    """.strip()

    compressed = zlib.compress(xml.encode("utf-8"))
    return base64.b64encode(compressed).decode("utf-8")


@pytest.fixture()
def xml_root(pob_string: str) -> ET.Element:
    xml_bytes = zlib.decompress(base64.b64decode(pob_string))
    return ET.fromstring(xml_bytes)


def test_parse_pob_build_extracts_sections(pob_string: str) -> None:
    parsed = parse_pob_build(pob_string)

    assert parsed["character"]["className"] == "Templar"
    assert parsed["character"]["level"] == 90

    assert parsed["tree"]["classId"] == 3
    assert parsed["tree"]["nodes"] == [1, 2, 3, 4]
    assert parsed["tree"]["url"] == "https://example.com/tree"

    assert len(parsed["items"]) == 2
    assert parsed["items"][0]["base_type"] == "Imbued Wand"


def test_extract_items_returns_structured_data(xml_root: ET.Element) -> None:
    items = extract_items(xml_root)

    assert items[0]["sockets"] == [["B", "G", "B"]]
    assert items[0]["affixes"]["prefixes"] == ["{range:0}Glowing"]
    assert items[0]["affixes"]["suffixes"] == ["{range:0}of Lightning"]

    assert items[1]["base_type"] == "Two-Stone Ring"
    assert items[1]["sockets"] == []


def test_extract_character_and_tree(xml_root: ET.Element) -> None:
    character = extract_character(xml_root)
    tree = extract_tree(xml_root)

    assert character == {
        "level": 90,
        "className": "Templar",
        "ascendClassName": "Inquisitor",
        "mainSkill": "Arc",
    }

    assert tree["nodes"] == [1, 2, 3, 4]
    assert tree["classId"] == 3
    assert tree["ascendClassId"] == 2


def test_parse_pob_build_rejects_invalid_data() -> None:
    with pytest.raises(ValueError):
        parse_pob_build("not-a-valid-pob-string")
