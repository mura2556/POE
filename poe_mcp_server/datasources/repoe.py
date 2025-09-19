"""Utilities for downloading and working with the RePoE export.

The RePoE project exposes a JSON export of Path of Exile game data.  The
crafting assistant relies on a subset of that export to provide accurate
mod, bench and spawn-weight information.  This module centralises the logic
for retrieving the export from GitHub and exposing convenient helpers for
other parts of the application.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

logger = logging.getLogger(__name__)

REPOE_REPOSITORY = "https://raw.githubusercontent.com/brather1ng/RePoE"
REPOE_DEFAULT_BRANCH = "master"
REPOE_DATA_DIR = "RePoE/data"

_DATASET_FILES: Mapping[str, Tuple[str, ...]] = {
    "mods": ("mods.json", "mods.min.json"),
    "master_mods": (
        "master_mods.json",
        "crafting_bench_options.json",
        "crafting_bench_options.min.json",
    ),
    "item_bases": ("item_bases.json", "base_items.json", "base_items.min.json"),
    "tags": ("tags.json", "tags.min.json"),
    "mod_types": ("mod_types.json", "mod_types.min.json"),
}

# The subset of files we download when refreshing the export.  The keys match
# the public names used by :class:`RePoEData` while the values refer to the
# concrete file inside the upstream repository.
_DEFAULT_REMOTE_FILES: Mapping[str, str] = {
    "mods": "mods.min.json",
    "master_mods": "crafting_bench_options.min.json",
    "item_bases": "base_items.min.json",
    "tags": "tags.min.json",
    "mod_types": "mod_types.min.json",
}


def _repoe_data_root(base_path: Optional[Path], branch: str, league: Optional[str]) -> Path:
    """Return the folder that should contain the RePoE export.

    Parameters
    ----------
    base_path:
        Root directory where the ``data/repoe`` folder lives.  When ``None`` the
        project root is inferred relative to this file.
    branch:
        Git branch of the upstream export (``master`` by default).
    league:
        Optional league identifier.  When provided the data is stored in a
        ``<branch>/<league>`` sub-folder so that multiple exports can coexist.
    """

    if base_path is None:
        base_path = Path(__file__).resolve().parents[2] / "data" / "repoe"
    destination = Path(base_path) / branch
    if league:
        destination /= league
    return destination


def download_repoe_data(
    *,
    base_path: Optional[Path] = None,
    branch: str = REPOE_DEFAULT_BRANCH,
    league: Optional[str] = None,
    files: Optional[Mapping[str, str]] = None,
    force: bool = False,
) -> Path:
    """Download the required RePoE JSON files.

    The helper mirrors a curated subset of the upstream repository in a local
    ``data/repoe`` directory.  The folder layout looks as follows::

        data/
          repoe/
            master/
              mods.json
              master_mods.json
              item_bases.json
              tags.json
              mod_types.json

    Parameters
    ----------
    base_path:
        Alternative location for the ``data/repoe`` folder.
    branch:
        Upstream git branch.  The RePoE project exposes league-specific branches
        (for example ``master`` or ``3.24``) which can be selected here.
    league:
        Optional logical league name.  When supplied the dataset will be stored
        under ``data/repoe/<branch>/<league>`` which allows keeping different
        variants side-by-side.
    files:
        Custom mapping of logical names to the remote file that should be
        downloaded.  When omitted :data:`_DEFAULT_REMOTE_FILES` is used.
    force:
        When ``True`` all files are re-downloaded even if they already exist.

    Returns
    -------
    pathlib.Path
        Directory containing the downloaded data.
    """

    destination = _repoe_data_root(base_path, branch, league)
    destination.mkdir(parents=True, exist_ok=True)

    remote_files = dict(_DEFAULT_REMOTE_FILES)
    if files:
        remote_files.update(files)

    for logical_name, remote_name in remote_files.items():
        url = f"{REPOE_REPOSITORY}/{branch}/{REPOE_DATA_DIR}/{remote_name}"
        local_path = destination / f"{logical_name}.json"
        if local_path.exists() and not force:
            logger.debug("Skipping %s (already cached)", logical_name)
            continue

        logger.info("Downloading %s from %s", logical_name, url)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "poe-mcp-agent"})
            with urllib.request.urlopen(request) as response:  # nosec: B310 - trusted host
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # pragma: no cover - network failure
            raise RuntimeError(f"Failed to download {url}: {exc}") from exc

        data = json.loads(payload)
        with local_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")

    return destination


def _load_json_file(root: Path, candidates: Iterable[str]) -> object:
    for candidate in candidates:
        path = root / candidate
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
    raise FileNotFoundError(f"Unable to find any of {candidates} in {root}")


@dataclass
class SpawnWeightBreakdown:
    """Detailed spawn weight information for a mod."""

    relevant_tags: List[Tuple[str, int]]
    total_weight: int
    disabled_tags: List[str]

    @property
    def is_spawnable(self) -> bool:
        return any(weight > 0 for _, weight in self.relevant_tags)


class RePoEData:
    """Container around the subset of the RePoE export we care about."""

    def __init__(self, root: Path):
        self.root = Path(root)
        if not self.root.exists():
            raise FileNotFoundError(
                f"RePoE export not found in {self.root}. Run scripts/sync_static_data.py first."
            )

        self.mods: MutableMapping[str, MutableMapping[str, object]] = _load_json_file(
            self.root, _DATASET_FILES["mods"]
        )

        raw_master = _load_json_file(self.root, _DATASET_FILES["master_mods"])
        if isinstance(raw_master, dict):
            self.master_mods: List[MutableMapping[str, object]] = list(raw_master.values())
        else:
            self.master_mods = list(raw_master)

        self.item_bases: MutableMapping[str, MutableMapping[str, object]] = _load_json_file(
            self.root, _DATASET_FILES["item_bases"]
        )
        self.tags: List[str] = list(_load_json_file(self.root, _DATASET_FILES["tags"]))
        self.mod_types: MutableMapping[str, MutableMapping[str, object]] = _load_json_file(
            self.root, _DATASET_FILES["mod_types"]
        )

        self._tag_set = set(self.tags)
        self._mods_by_group: Dict[str, List[Tuple[str, MutableMapping[str, object]]]] = {}
        self._mods_by_name: Dict[str, List[Tuple[str, MutableMapping[str, object]]]] = {}
        self._base_index: Dict[str, List[Tuple[str, MutableMapping[str, object]]]] = {}
        self._bench_by_mod: Dict[str, List[MutableMapping[str, object]]] = {}

        self._build_indexes()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_indexes(self) -> None:
        for mod_id, mod_data in self.mods.items():
            name = str(mod_data.get("name", "")).strip().lower()
            if name:
                self._mods_by_name.setdefault(name, []).append((mod_id, mod_data))

            for group in mod_data.get("groups", []) or [mod_id]:
                self._mods_by_group.setdefault(group, []).append((mod_id, mod_data))

        for group, entries in self._mods_by_group.items():
            entries.sort(
                key=lambda item: (
                    int(item[1].get("required_level", 0)),
                    item[1].get("generation_type", ""),
                    item[0],
                ),
                reverse=True,
            )

        for base_id, base_data in self.item_bases.items():
            name = str(base_data.get("name", "")).strip().lower()
            if name:
                self._base_index.setdefault(name, []).append((base_id, base_data))

        for option in self.master_mods:
            actions = option.get("actions", {})
            explicit = actions.get("add_explicit_mod")
            if explicit:
                self._bench_by_mod.setdefault(explicit, []).append(option)
            veiled = actions.get("add_random_veiled_modifier")
            if veiled:
                self._bench_by_mod.setdefault(veiled, []).append(option)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def resolve_base(self, base_identifier: str) -> Tuple[str, MutableMapping[str, object]]:
        """Return the base item entry for a metadata id or display name."""

        base_identifier = base_identifier.strip()
        if base_identifier in self.item_bases:
            return base_identifier, self.item_bases[base_identifier]

        matches = self._base_index.get(base_identifier.lower(), [])
        if not matches:
            raise KeyError(f"Unknown base item '{base_identifier}'")
        if len(matches) > 1:
            names = ", ".join(base_id for base_id, _ in matches)
            raise KeyError(
                f"Base item name '{base_identifier}' is ambiguous: {names}. Use the metadata id."
            )
        return matches[0]

    def resolve_mod(self, mod_identifier: str) -> Tuple[str, MutableMapping[str, object]]:
        """Return a mod entry for an internal id or display name."""

        mod_identifier = mod_identifier.strip()
        if mod_identifier in self.mods:
            return mod_identifier, self.mods[mod_identifier]

        matches = self._mods_by_name.get(mod_identifier.lower(), [])
        if not matches:
            raise KeyError(f"Unknown mod '{mod_identifier}'")
        if len(matches) > 1:
            ids = ", ".join(mod_id for mod_id, _ in matches[:5])
            if len(matches) > 5:
                ids += ", …"
            raise KeyError(
                f"Mod name '{mod_identifier}' is ambiguous (candidates: {ids}). Use the internal id."
            )
        return matches[0]

    def describe_base(self, base_id: str, base_data: Mapping[str, object]) -> Dict[str, object]:
        tags = list(base_data.get("tags", []))
        return {
            "id": base_id,
            "name": base_data.get("name"),
            "item_class": base_data.get("item_class"),
            "drop_level": base_data.get("drop_level"),
            "tags": tags,
            "implicits": list(base_data.get("implicits", [])),
            "requirements": base_data.get("requirements", {}),
        }

    def tier_breakdown(self, mod_id: str) -> Dict[str, object]:
        mod = self.mods[mod_id]
        groups = mod.get("groups", []) or [mod_id]
        primary_group = groups[0]
        entries = self._mods_by_group.get(primary_group, [])
        breakdown = []
        current_tier = None
        for index, (candidate_id, candidate_data) in enumerate(entries, start=1):
            entry = {
                "tier": index,
                "id": candidate_id,
                "name": candidate_data.get("name"),
                "required_level": candidate_data.get("required_level", 0),
                "stats": candidate_data.get("stats", []),
            }
            if candidate_id == mod_id:
                current_tier = index
            breakdown.append(entry)
        return {
            "group": primary_group,
            "tier": current_tier,
            "total_tiers": len(entries),
            "tiers": breakdown,
        }

    def influence_tags(self, base_tags: Iterable[str], influences: Iterable[str]) -> List[str]:
        resolved: List[str] = []
        lowered_influences = {inf.lower() for inf in influences}
        for tag in base_tags:
            for influence in lowered_influences:
                candidate = f"{tag}_{influence}"
                if candidate in self._tag_set:
                    resolved.append(candidate)
        return resolved

    def spawn_weights(
        self,
        mod_id: str,
        base_tags: Iterable[str],
        influences: Optional[Iterable[str]] = None,
    ) -> SpawnWeightBreakdown:
        mod = self.mods[mod_id]
        tag_weights = mod.get("spawn_weights", [])
        tags_to_check = set(base_tags)
        if influences:
            tags_to_check.update(self.influence_tags(base_tags, influences))
        tags_to_check.add("default")

        relevant = []
        disabled = []
        total = 0
        for weight_info in tag_weights:
            tag = weight_info.get("tag")
            weight = int(weight_info.get("weight", 0))
            if tag in tags_to_check:
                relevant.append((tag, weight))
                total += max(weight, 0)
            elif weight == 0:
                disabled.append(tag)
        relevant.sort(key=lambda item: item[1], reverse=True)
        return SpawnWeightBreakdown(relevant_tags=relevant, total_weight=total, disabled_tags=disabled)

    def bench_options(self, mod_id: str) -> List[Dict[str, object]]:
        options = self._bench_by_mod.get(mod_id, [])
        described = []
        for option in options:
            described.append(
                {
                    "master": option.get("master"),
                    "bench_tier": option.get("bench_tier"),
                    "item_classes": option.get("item_classes", []),
                    "cost": self._describe_cost(option.get("cost", {})),
                    "actions": option.get("actions", {}),
                }
            )
        return described

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    def _describe_cost(self, cost: Mapping[str, object]) -> List[Dict[str, object]]:
        output: List[Dict[str, object]] = []
        for currency_id, value in cost.items():
            base = self.item_bases.get(currency_id, {})
            output.append(
                {
                    "currency_id": currency_id,
                    "currency_name": base.get("name", currency_id.split("/")[-1]),
                    "amount": value,
                }
            )
        return output


_DATA_CACHE: Dict[Tuple[Path, str, Optional[str]], RePoEData] = {}


def load_repoe_data(
    *,
    base_path: Optional[Path] = None,
    branch: str = REPOE_DEFAULT_BRANCH,
    league: Optional[str] = None,
    download: bool = False,
) -> RePoEData:
    """Load the curated subset of the RePoE dataset.

    Parameters
    ----------
    base_path:
        Override the default ``data/repoe`` folder.
    branch / league:
        Identify the dataset variant to load.
    download:
        When ``True`` the function will attempt to download the dataset if it is
        missing.  This is primarily useful for development environments.
    """

    root = _repoe_data_root(base_path, branch, league)
    cache_key = (root, branch, league)
    if cache_key in _DATA_CACHE:
        return _DATA_CACHE[cache_key]

    if download and not root.exists():
        download_repoe_data(base_path=base_path, branch=branch, league=league)

    data = RePoEData(root)
    _DATA_CACHE[cache_key] = data
    return data


__all__ = [
    "REPOE_REPOSITORY",
    "REPOE_DEFAULT_BRANCH",
    "download_repoe_data",
    "load_repoe_data",
    "RePoEData",
    "SpawnWeightBreakdown",
]
