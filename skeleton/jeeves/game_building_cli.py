#!/usr/bin/env python3
"""CLI for Game Building, Design, and Story capability."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from skeleton.ai.agents.jeeves.game_building_capability import make_game_capability  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Game building / design / story capability")
    parser.add_argument("--fleet", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("genres")
    sub.add_parser("eras")
    sub.add_parser("card")
    sub.add_parser("curriculum")

    p_brief = sub.add_parser("brief")
    p_brief.add_argument("--title", required=True)
    p_brief.add_argument("--genre", default="platformer")
    p_brief.add_argument("--era", default="16bit")

    p_pipe = sub.add_parser("pipeline")
    p_pipe.add_argument("--title", required=True)
    p_pipe.add_argument("--genre", default="rpg")
    p_pipe.add_argument("--era", default="16bit")

    p_story = sub.add_parser("story")
    p_story.add_argument("--title", default="Untitled")
    p_story.add_argument("--genre", default="adventure")
    p_story.add_argument("--era", default="16bit")

    p_cores = sub.add_parser("cores")
    p_cores.add_argument("--era", default="16bit")

    args = parser.parse_args(argv)
    cap = make_game_capability(args.fleet)

    if args.cmd == "genres":
        print(json.dumps(cap.available_genres(), indent=2))
    elif args.cmd == "eras":
        print(json.dumps(cap.available_eras(), indent=2))
    elif args.cmd == "card":
        print(cap.model_card())
    elif args.cmd == "curriculum":
        print(json.dumps(cap.curriculum_game_design(), indent=2))
    elif args.cmd == "brief":
        b = cap.design_brief(args.title, args.genre, args.era)
        print(json.dumps(b.__dict__, indent=2))
    elif args.cmd == "pipeline":
        print(json.dumps(cap.full_pipeline(args.title, args.genre, args.era), indent=2, default=str))
    elif args.cmd == "story":
        b = cap.design_brief(args.title, args.genre, args.era)
        print(json.dumps(cap.generate_story_arc(b), indent=2))
    elif args.cmd == "cores":
        print(json.dumps(cap.recommend_cores_for_era(args.era), indent=2))
    else:
        parser.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
