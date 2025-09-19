"""Shared data structures used by the server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Mapping, Sequence


@dataclass
class CraftingStep:
    """A single crafting instruction augmented with metadata."""

    action: str
    instruction: str
    metadata: Dict[str, Any] = field(default_factory=dict)


ModType = Literal["prefix", "suffix", "implicit", "crafted"]


@dataclass(frozen=True)
class SourceHint:
    """Optional pointer describing the expected origin of a modifier."""

    kind: Literal["essence", "bench", "harvest", "influence", "other"]
    detail: str | None = None


@dataclass(frozen=True)
class ModRequirement:
    """Represents a modifier that must appear on the finished item."""

    text: str
    mod_type: ModType
    required: bool = True
    source_hint: SourceHint | None = None
    notes: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class SocketBlueprint:
    """Socket configuration requested by the blueprint."""

    total: int | None = None
    links: Sequence[int] = field(default_factory=tuple)
    colours: Mapping[str, int] = field(default_factory=dict)
    notes: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class ItemBlueprint:
    """High level description of the desired end-state item."""

    name: str | None
    base_item: str
    item_class: str | None
    influences: Sequence[str] = field(default_factory=tuple)
    required_prefixes: Sequence[ModRequirement] = field(default_factory=tuple)
    required_suffixes: Sequence[ModRequirement] = field(default_factory=tuple)
    sockets: SocketBlueprint | None = None
    notes: Sequence[str] = field(default_factory=tuple)

    def all_required_mods(self) -> Sequence[ModRequirement]:
        """Return every modifier requirement that must be satisfied."""

        return (*self.required_prefixes, *self.required_suffixes)
