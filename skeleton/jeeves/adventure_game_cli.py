#!/usr/bin/env python3
"""CLI for meticulous adventure game capability."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from adventure_game_capability import make_adventure_capability  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Adventure game design capability")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("card")
    p_pipe = sub.add_parser("pipeline")
    p_pipe.add_argument("--title", required=True)
    p_pipe.add_argument("--era", default="16bit")
    p_pipe.add_argument("--rooms", type=int, default=10)

    p_assets = sub.add_parser("assets")
    p_assets.add_argument("--era", default="16bit")
    p_assets.add_argument("--tier", default="polished")

    args = parser.parse_args(argv)
    cap = make_adventure_capability()

    if args.cmd == "card":
        print(cap.model_card())
    elif args.cmd == "pipeline":
        print(json.dumps(cap.full_adventure_pipeline(args.title, args.era, args.rooms), indent=2, default=str))
    elif args.cmd == "assets":
        print(json.dumps(cap.asset_quality_spec(args.era, args.tier), indent=2))
    else:
        parser.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
