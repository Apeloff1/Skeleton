"""Export original Dragon practice games to self-contained offline browser files.

This is an operator-initiated content build. It makes no network calls,
downloads no commercial media and never asserts hardware or legal sign-off.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from skeleton.ai.game_builder.practice_game_library import (
    list_practice_games, load_practice_game, render_practice_game,
)
from skeleton.ai.game_builder.playable_export import write_playable_html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="Print packaged playable game IDs.")
    parser.add_argument("--game", help="Original practice game ID to export.")
    parser.add_argument("--all", action="store_true", help="Export the complete bounded library.")
    parser.add_argument("--output", type=Path, help="Destination directory (must exist).")
    args = parser.parse_args(argv)
    if args.list:
        if args.game or args.all or args.output:
            parser.error("--list cannot be combined with an export")
        print("\n".join(list_practice_games(authorized=True)))
        return 0
    if args.all == bool(args.game):
        parser.error("select exactly one of --all or --game")
    if args.output is None:
        parser.error("--output directory is required for game export")
    directory = args.output.expanduser()
    if not directory.is_dir() or directory.is_symlink():
        parser.error("--output must identify an existing non-symlink directory")
    names = (
        list_practice_games(authorized=True) if args.all else (args.game,)
    )
    for game_id in names:
        item = load_practice_game(game_id, authorized=True)
        bundle = render_practice_game(item.game_id, authorized=True)
        target = directory / (item.game_id + ".html")
        if target.exists() or target.is_symlink():
            parser.error(f"refusing to overwrite existing game: {target.name}")
        write_playable_html(bundle, target, authorized=True, overwrite=False)
        print(f"{item.game_id}\t{item.world_digest}\t{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
