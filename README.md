# POE

This repository contains support utilities for Path of Exile master control processes.  
Recent changes add first-class support for synchronising data from the [Craft of Exile](https://www.craftofexile.com/) simulator so that crafting plans can reference simulator odds and recipe costs directly.

## Craft of Exile dataset

The Craft of Exile team publishes their simulator dataset in a Git repository.  The ``CraftOfExileClient`` included in this project downloads the published JSON bundle and exposes helpers for commonly used sections:

* Fossil combinations and descriptions.
* Harvest crafting options.
* Crafting bench recipes.
* Meta-crafting odds and costs.

### Refreshing cached data

Use ``scripts/sync_static_data.py`` to download and cache the dataset locally:

```bash
python scripts/sync_static_data.py --craft-of-exile \
    --craft-of-exile-url https://raw.githubusercontent.com/CraftOfExile/data/refs/heads/master/data.json \
    --craft-of-exile-output data/craft_of_exile \
    --craft-of-exile-league Settlers
```

The command writes ``data/craft_of_exile/data.json`` by default.  Provide ``--craft-of-exile-league`` to namespace caches per league, or ``--craft-of-exile-compact`` to store a compact (non pretty-printed) JSON file.  All options accept sensible defaults, so specifying ``--craft-of-exile`` alone is enough to refresh the default cache.

### Planning integrations

``poe_mcp_server/crafting/plan_builder.py`` automatically loads the cached Craft of Exile dataset when building plans.  Any step that supplies a ``reference_type`` (``fossil``, ``harvest``, ``bench``, or ``meta``) and ``reference_id`` will be annotated with the corresponding Craft of Exile entry so the generated plans can cite simulator statistics inline.
