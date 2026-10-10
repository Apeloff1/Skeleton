"""Export original Dragon practice games to self-contained offline browser files.

This is an operator-initiated content build. It makes no network calls,
downloads no commercial media and never asserts hardware or legal sign-off.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from skeleton.ai.game_builder.contracts import canonical_json
from skeleton.ai.game_builder.practice_game_selection import (
    plan_practice_progression, practice_portfolio_receipt,
)

from skeleton.ai.game_builder.practice_game_library import (
    list_practice_games, load_practice_game, render_practice_game,
)
from skeleton.ai.game_builder.playable_export import write_playable_html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="Print packaged playable game IDs.")
    parser.add_argument("--catalog", action="store_true", help="Emit verified JSON portfolio.")
    parser.add_argument("--verify", action="store_true", help="Verify all original games without writing.")
    parser.add_argument("--progression", type=int, help="Show a 1-20 game increasing-difficulty route.")
    parser.add_argument("--theme", choices=("forest", "space", "desert", "ocean", "arcade"))
    parser.add_argument("--game", help="Original practice game ID to export.")
    parser.add_argument("--all", action="store_true", help="Export the complete bounded library.")
    parser.add_argument("--output", type=Path, help="Destination directory (must exist).")
    args = parser.parse_args(argv)
    if args.theme is not None and args.progression is None:
        parser.error("--theme is valid only for a progression")
    discoveries = sum((args.list, args.catalog, args.verify,
                       args.progression is not None))
    if discoveries > 1:
        parser.error("select one inventory, verification or progression action")
    if args.catalog or args.verify or args.progression is not None:
        if args.game or args.all or args.output:
            parser.error("discovery and verification actions cannot export files")
        if args.progression is not None:
            items = plan_practice_progression(
                authorized=True, count=args.progression, theme=args.theme,
            )
            print(canonical_json({
                "schema": "skeleton.dragon.practice_progression.v1",
                "advisory_only": True,
                "training_authorized": False,
                "games": [item.to_payload() for item in items],
            }))
        else:
            receipt = practice_portfolio_receipt(authorized=True)
            if args.catalog:
                print(canonical_json(receipt))
            else:
                print(f"verified {receipt['game_count']} original games: {receipt['digest']}")
        return 0
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
