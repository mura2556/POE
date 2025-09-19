"""Shared data structures used by the server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class CraftingStep:
    """A single crafting instruction augmented with metadata."""

    action: str
    instruction: str
    metadata: Dict[str, Any] = field(default_factory=dict)
