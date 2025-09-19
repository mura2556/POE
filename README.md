# POE Crafting MCP

This repository contains tooling for Path of Exile crafting guidance that is
backed by the open-source [RePoE](https://github.com/brather1ng/RePoE)
export.  The helper consumes curated data sets describing mods, master crafting
options, item bases and influence-specific spawn weights so that responses can
quote precise tier information.

## Static data synchronisation

Run the sync script whenever you want to refresh the embedded RePoE export:

```bash
scripts/sync_static_data.py
```

The script accepts a handful of flags so you can pin the dataset to a specific
league snapshot or stage it into a custom location:

```
usage: sync_static_data.py [-h] [--branch BRANCH] [--league LEAGUE] [--base-path BASE_PATH] [--force]
```

* `--branch` – Git branch to pull from the upstream RePoE repository (defaults
  to `master`).
* `--league` – Optional label stored as an extra folder level to keep multiple
  league exports side-by-side (for example `--league sentinel`).
* `--base-path` – Override the default `data/repoe` target directory.
* `--force` – Re-download the files even if they are already cached locally.

The data is written to `data/repoe/<branch>/<league?>/` and the repository keeps
only a `.gitkeep` placeholder so that large JSON files never end up in version
control.  The downloader normalises the upstream JSON into human-readable,
pretty-printed files which makes ad-hoc inspection easier.

## Crafting analysis

`poe_mcp_server.datasources.repoe` encapsulates the download logic and provides a
`RePoEData` helper that indexes mods, tier families, master crafting options and
spawn weights.  Higher level systems such as
`poe_mcp_server.crafting.analyzer.CraftingAnalyzer` and
`poe_mcp_server.crafting.plan_builder.CraftingPlanBuilder` use this information
to:

* resolve item bases and translate currency metadata into human friendly names,
* report exact mod tiers and stat ranges,
* expose spawn-weight breakdowns including influence-only tags, and
* surface bench crafting prerequisites (master, tier and cost).

These enriched details are surfaced by the MCP when generating crafting advice,
improving the accuracy of weight calculations and highlighting alternative
bench options when a mod cannot naturally spawn.

## Development notes

* The downloader uses standard library modules and therefore works in fresh
  virtual environments without additional dependencies.
* `CraftingAnalyzer` accepts `auto_download=True` if you want it to grab the
  RePoE export automatically in ephemeral environments, otherwise it will raise
  a helpful error instructing you to run the sync script.
* The plan builder returns structured data so that downstream consumers can
  present either textual guidance or rich UI summaries.
