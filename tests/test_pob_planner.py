import pathlib
import sys

import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from poe_mcp_server.models import (
    ItemBlueprint,
    ModRequirement,
    SocketBlueprint,
    SourceHint,
)
from poe_mcp_server.planner import assemble_plan_from_pob


@pytest.fixture()
def sample_blueprint() -> ItemBlueprint:
    return ItemBlueprint(
        name="Example Boots",
        base_item="Two-Toned Boots",
        item_class="Armour",
        influences=("Hunter",),
        sockets=SocketBlueprint(total=4, links=(4,), colours={"G": 2, "R": 1, "B": 1}),
        required_prefixes=(
            ModRequirement(
                text="+70 to maximum Life",
                mod_type="prefix",
                source_hint=SourceHint(kind="essence", detail="Deafening Essence of Greed"),
            ),
            ModRequirement(
                text="+1 to Level of all Chaos Skill Gems",
                mod_type="prefix",
                source_hint=SourceHint(kind="influence", detail="Hunter"),
            ),
        ),
        required_suffixes=(
            ModRequirement(
                text="Movement Speed",
                mod_type="suffix",
                source_hint=SourceHint(kind="bench", detail="Movement Speed"),
            ),
            ModRequirement(
                text="Lightning Resistance",
                mod_type="suffix",
                source_hint=SourceHint(kind="harvest", detail="Lightning Resistance"),
            ),
            ModRequirement(
                text="Totally made up mod",
                mod_type="suffix",
            ),
        ),
    )


def test_assemble_plan_from_pob(sample_blueprint: ItemBlueprint) -> None:
    plan = assemble_plan_from_pob([sample_blueprint])

    assert plan[0].action == "Acquire Two-Toned Boots"
    actions = [step.action for step in plan]
    assert "Configure sockets" in actions

    coverage: set[str] = set()
    essence_step = harvest_step = bench_step = influence_step = gap_step = None
    for step in plan:
        coverage.update(step.metadata.get("covers_mods", []))
        step_type = step.metadata.get("type")
        if step_type == "essence":
            essence_step = step
        elif step_type == "harvest":
            harvest_step = step
        elif step_type == "bench":
            bench_step = step
        elif step_type == "influence":
            influence_step = step
        elif step_type == "gap":
            gap_step = step

    expected_mods = {
        "+70 to maximum Life",
        "+1 to Level of all Chaos Skill Gems",
        "Movement Speed",
        "Lightning Resistance",
        "Totally made up mod",
    }
    assert coverage == expected_mods

    assert influence_step is not None
    assert "+1 to Level of all Chaos Skill Gems" in influence_step.metadata["covers_mods"]

    assert essence_step is not None
    assert essence_step.metadata["essence"]["name"] == "Deafening Essence of Greed"
    assert "+70 to maximum Life" in essence_step.metadata["covers_mods"]

    assert harvest_step is not None
    assert any(
        "Lightning" in line for line in harvest_step.metadata["harvest_crafts"][0]["description"]
    )

    assert bench_step is not None
    assert bench_step.metadata.get("consumes_suffix") is True
    assert "Movement Speed" in bench_step.metadata["covers_mods"]

    assert gap_step is not None
    assert gap_step.metadata.get("missing_source") is True

    essence_index = actions.index(essence_step.action)
    harvest_index = actions.index(harvest_step.action)
    bench_index = actions.index(bench_step.action)

    assert essence_index < bench_index
    assert harvest_index < bench_index
