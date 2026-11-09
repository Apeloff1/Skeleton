#!/usr/bin/env python3
"""CLI for full game creation & planning capability."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from full_game_creation_capability import make_full_creation_capability  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Full game creation & planning")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("card")
    p = sub.add_parser("package")
    p.add_argument("--title", required=True)
    p.add_argument("--genre", default="adventure")
    p.add_argument("--era", default="16bit")

    p2 = sub.add_parser("plan")
    p2.add_argument("--title", required=True)
    p2.add_argument("--weeks", type=int, default=40)

    args = parser.parse_args(argv)
    cap = make_full_creation_capability()

    if args.cmd == "card":
        print(cap.model_card())
    elif args.cmd == "package":
        print(json.dumps(cap.full_creation_package(args.title, args.genre, args.era), indent=2, default=str))
    elif args.cmd == "plan":
        print(json.dumps(cap.create_master_plan(args.title, weeks=args.weeks), indent=2, default=str))
    else:
        parser.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
