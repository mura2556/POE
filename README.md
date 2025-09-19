# Path of Exile MCP static data

This repository packages a lightweight knowledge base that powers the
`poe_mcp_server` helpers for Path of Exile crafting planning.  Curated JSON
snapshots live under [`data/`](data/) and are loaded at runtime via the
[`poe_mcp_server.datasources`](poe_mcp_server/datasources) package.  The primary
consumer is [`assemble_crafting_plan`](poe_mcp_server/planner.py), which
augments free-form crafting steps with map boss unlocks, harvest crafts,
essence details, and bench recipe metadata.

## Curated datasets

The sync script stores the following files inside [`data/`](data/):

* `bench_recipes.json` – Master crafting bench options, including translated
  modifier text, bench tiers, supported item classes, action keywords, and
  exact crafting costs.
* `essences.json` – Essence tiers, minimum area level, and the translated
  modifiers they apply when used on an item.
* `harvest_crafts.json` – Harvest crafting options with their groups, tags, and
  any class restrictions to help match augment/remove actions.
* `bosses.json` – Atlas boss encounters and map boss metadata (map tier,
  resident bosses, and unlock requirements when available).

These JSON documents are consumed via thin loaders in
`poe_mcp_server/datasources/`.  Each loader normalises the text for fuzzy
matching so planner calls such as
`assemble_crafting_plan(["Run Maven's Crucible"])` automatically append the
relevant context to the returned `CraftingStep` objects.

## Sync workflow

The curated data is regenerated with
[`scripts/sync_static_data.py`](scripts/sync_static_data.py).  The script pulls
live data from the PoE Wiki and the RePoE project to ensure the knowledge base
stays current across leagues.

1. Ensure Python 3.10+ is available and install the only runtime dependency:
   ```bash
   pip install requests
   ```
2. Run the sync script from the repository root.  Without arguments it refreshes
   every dataset:
   ```bash
   python scripts/sync_static_data.py
   ```
3. To shorten reruns while iterating you can limit the sections.  For example,
   regenerate the boss dataset after tweaking keyword logic:
   ```bash
   python scripts/sync_static_data.py --sections bosses
   ```
4. Inspect the updated files under `data/` (e.g. spot-check that
   `bosses.json` unlock strings look clean) and commit the refreshed JSON along
   with code changes.

Each invocation rewrites the JSON files in-place.  Because the script relies on
external services, expect the boss export to take a couple of minutes while it
requests individual wiki pages.  Re-run the sync whenever GGG launches a new
league or the upstream data sources publish balance updates.

## Developing against the planner

When new knowledge is synced, no additional steps are needed for the planner:
`poe_mcp_server.datasources.utils.load_json` reads directly from `data/` and the
`assemble_crafting_plan` helper automatically surfaces the richer instructions.
If you expand the planner with new action keywords, add the necessary curated
fields to the sync script and rerun it so the JSON stays in lockstep with the
code.
