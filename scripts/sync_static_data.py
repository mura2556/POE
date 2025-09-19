"""Download and cache external static datasets used by the server."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from poe_mcp_server.datasources.craftofexile import CraftOfExileClient, CraftOfExileError


def _sync_craft_of_exile(args: argparse.Namespace) -> None:
    client = CraftOfExileClient(bundle_url=args.craft_of_exile_url, timeout=args.timeout)
    dataset = client.fetch()

    output_dir = Path(args.craft_of_exile_output)
    if args.craft_of_exile_league:
        output_dir = output_dir / args.craft_of_exile_league
    output_path = output_dir / "data.json"
    CraftOfExileClient.dump_to_path(dataset, output_path, pretty=not args.craft_of_exile_compact)
    print(f"Craft of Exile data written to {output_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Network timeout (seconds) for downloads.",
    )
    parser.add_argument(
        "--craft-of-exile",
        action="store_true",
        help="Refresh the Craft of Exile simulator dataset.",
    )
    parser.add_argument(
        "--craft-of-exile-url",
        default=CraftOfExileClient.DEFAULT_URL,
        help="Override the Craft of Exile bundle URL.",
    )
    parser.add_argument(
        "--craft-of-exile-output",
        default="data/craft_of_exile",
        help="Directory to write the Craft of Exile dataset into.",
    )
    parser.add_argument(
        "--craft-of-exile-league",
        help="Optional league name to namespace the Craft of Exile cache.",
    )
    parser.add_argument(
        "--craft-of-exile-compact",
        action="store_true",
        help="Write the Craft of Exile cache without pretty-printing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.craft_of_exile:
        parser.error("Specify --craft-of-exile to refresh the Craft of Exile dataset.")

    try:
        _sync_craft_of_exile(args)
    except CraftOfExileError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
