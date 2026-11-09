"""Offline sparse-frontier game: exploration, recovery, settlements and SQLite saves."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Sequence

from .original_world_campaign import SCENARIOS
from .original_world_frontier import (
    ACTIONS, DIRECTIONS, FrontierAction, FrontierError, SparseFrontier,
)

MAX_SCRIPT = 65536


def _parse_action(row: object) -> FrontierAction:
    if not isinstance(row, dict) or set(row) - {"verb", "option", "amount"}:
        raise FrontierError("invalid frontier action fields")
    try:
        action = FrontierAction(**row)
    except (TypeError, ValueError) as exc:
        raise FrontierError("frontier action missing required fields") from exc
    if action.verb not in ACTIONS:
        raise FrontierError("frontier action not supported")
    if type(action.amount) is not int or not 1 <= action.amount <= 3:
        raise FrontierError("invalid action quantity")
    if not isinstance(action.option, str) or len(action.option) > 32:
        raise FrontierError("invalid action option")
    return action


def parse_script(content: str) -> tuple[FrontierAction, ...]:
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_SCRIPT:
        raise FrontierError("script outside size budget")
    try:
        rows = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise FrontierError("invalid JSON frontier script") from exc
    if not isinstance(rows, list) or len(rows) > 1024:
        raise FrontierError("frontier script must be a bounded list")
    return tuple(_parse_action(row) for row in rows)


def parse_command(text: str) -> FrontierAction:
    try:
        words = shlex.split(text)
    except ValueError as exc:
        raise FrontierError("invalid terminal command") from exc
    if not words:
        raise FrontierError("empty command")
    verb = words[0].replace("-", "_")
    if verb not in ACTIONS:
        raise FrontierError("unknown frontier command")
    if verb in {"move", "redirect_rain"}:
        if len(words) not in (2, 3):
            raise FrontierError("direction required")
        try:
            return _parse_action({
                "verb": verb, "option": words[1],
                "amount": int(words[2]) if len(words) == 3 else 1,
            })
        except ValueError as exc:
            raise FrontierError("invalid quantity") from exc
    if len(words) not in (1, 2):
        raise FrontierError("expected verb and optional quantity")
    try:
        return _parse_action({
            "verb": verb, "amount": int(words[1]) if len(words) == 2 else 1,
        })
    except ValueError as exc:
        raise FrontierError("invalid quantity") from exc


def render(world: SparseFrontier, radius: int = 2) -> str:
    player = world.player()
    return "\n".join([
        world.nearby_map(radius),
        f"Health {player.health} | Energy {player.energy} | "
        f"Hunger {player.hunger} | AP {player.actions}",
        f"Food {player.food} | Water {player.water} | "
        f"Wood {player.wood} | Stone {player.stone} | "
        f"Tools {player.tools} | Coins {player.coins}",
        f"Trust {player.trust} | Knowledge {player.knowledge} | "
        f"Promises {player.promises} | Quilt {player.quilt}",
        f"Passages: {', '.join(world.passages())}",
        f"Current {world.tile().biome} tile: "
        f"food={world.tile().food}, wood={world.tile().wood}, "
        f"water={world.tile().water}, structure={world.tile().structure or 'none'}",
    ])


def _interactive(world: SparseFrontier) -> None:
    print("Sparse Original Frontier — persistent offline world.")
    print("Commands: help, map, status, quit, or any supported action.")
    print(render(world))
    while True:
        try:
            line = input("frontier> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nWorld data remains saved to its SQLite store.")
            break
        if not line:
            continue
        if line in {"quit", "exit"}:
            break
        if line in {"map", "status"}:
            print(render(world))
            continue
        if line == "help":
            print("Actions:", ", ".join(sorted(ACTIONS)))
            print("Usage: move north | forage 2 | settle | end_turn")
            continue
        try:
            receipt = world.act(parse_command(line))
            print(receipt.text)
            print(render(world))
        except FrontierError as exc:
            print("Action rejected:", exc)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play a sparse procedurally generated world.")
    parser.add_argument("--db", default=":memory:",
                        help="SQLite save file; default ephemeral memory")
    parser.add_argument("--world", choices=sorted(SCENARIOS), default="serenity-05")
    parser.add_argument("--seed", default="sparse-frontier")
    parser.add_argument("--actions-json", default="[]")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--show-map", action="store_true")
    args = parser.parse_args(argv)
    try:
        with SparseFrontier(args.db, args.world, args.seed) as game:
            receipts = [
                game.act(action) for action in parse_script(args.actions_json)
            ]
            if args.interactive:
                _interactive(game)
            elif args.show_map:
                print(render(game))
            else:
                print(json.dumps({
                    "status": "playable-sparse-frontier",
                    "world_id": game.world_id,
                    "seed": game.seed,
                    "player": game.player().__dict__,
                    "visited": game.visited_count(),
                    "modified_tiles": game.modified_count(),
                    "map": game.nearby_map(2),
                    "receipts": [r.__dict__ | {"action": r.action.__dict__}
                                 for r in receipts],
                    "note": "One streaming ruleset; coordinates are not independently authored games.",
                }, sort_keys=True, indent=2))
    except (FrontierError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
