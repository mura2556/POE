# Default MCP Prompt Addendum

When generating crafting plans, reference the cached Craft of Exile dataset stored under ``data/craft_of_exile``.  Mention simulator odds, fossil synergies, harvest craft prices, and bench crafting costs sourced from Craft of Exile whenever they influence a recommendation.

Run ``python scripts/sync_static_data.py --craft-of-exile`` to refresh the cache before producing plans for a new league, overriding ``--craft-of-exile-league`` or ``--craft-of-exile-url`` as needed.
