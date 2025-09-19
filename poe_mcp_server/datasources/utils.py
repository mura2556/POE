"""Helper functions for loading curated static data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_json(name: str) -> Any:
    """Load a JSON document from :mod:`data` using UTF-8 encoding."""
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Expected data file {path} was not found. Run scripts/sync_static_data.py first.")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
