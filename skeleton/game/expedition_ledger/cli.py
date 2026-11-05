"""Run original offline expeditions; JSON output and no external calls."""
from __future__ import annotations

import argparse
import json

from .runtime import (
    CHAPTER_IDS, evidence, load_episode, new_game, run_episode,
    shortest_plan, snapshot,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic expedition player")
    parser.add_argument("--episode", choices=CHAPTER_IDS, required=True)
    parser.add_argument("--plan", action="store_true",
                        help="run the bounded source-derived winning route")
    parser.add_argument("--moves", default="",
                        help="comma-separated directions: north,south,east,west")
    args = parser.parse_args(argv)
    ep = load_episode(args.episode)
    if args.plan and args.moves:
        parser.error("--plan and --moves are mutually exclusive")
    commands = shortest_plan(ep) if args.plan else (
        tuple(args.moves.split(",")) if args.moves else ()
    )
    state = run_episode(ep, commands) if commands else new_game(ep)
    print(json.dumps({
        "episode": ep.chapter_id,
        "title": ep.quest["title"],
        "commands": list(commands),
        "receipt": evidence(ep, state),
        "save": snapshot(ep, state),
    }, sort_keys=True, separators=(",", ":")))
    return 0 if state.status != "lost" else 2


if __name__ == "__main__":
    raise SystemExit(main())
