#!/usr/bin/env python3
"""Synchronise static data dependencies.

The script currently focuses on the RePoE dataset which powers the crafting
helper.  It can fetch multiple league branches and keeps them in separate
folders under ``data/repoe``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poe_mcp_server.datasources.repoe import REPOE_DEFAULT_BRANCH, download_repoe_data

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh bundled static data")
    parser.add_argument(
        "--branch",
        default=REPOE_DEFAULT_BRANCH,
        help="RePoE git branch to download (default: %(default)s)",
    )
    parser.add_argument(
        "--league",
        help="Optional league identifier.  Stored as an extra folder level for side-by-side exports.",
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        default=None,
        help="Override the data/repoe directory (defaults to the repository root)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even when the files are already present.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_path = download_repoe_data(
        base_path=args.base_path,
        branch=args.branch,
        league=args.league,
        force=args.force,
    )
    logger.info("RePoE data synced under %s", dataset_path)


if __name__ == "__main__":
    main()
