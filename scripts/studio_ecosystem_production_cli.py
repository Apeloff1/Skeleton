"""Operator opt-in production of original studio HTML5/SVG/WAV packages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_portfolio import StudioPortfolio
from skeleton.ai.game_builder.studio_ecosystem_preview_batch import build_catalog_preview_batch


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Build original source-verified studio preview packages")
    parser.add_argument("--private-root",required=True,type=Path,
                        help="Existing private journal/storage directory (0700 on POSIX)")
    parser.add_argument("--output-root",required=True,type=Path,
                        help="Existing private output directory; never overwrite")
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--project",action="append",
                        help="One registered original project ID; repeat for multiple games")
    choice.add_argument("--all",action="store_true",
                        help="Explicitly select all registered matching projects")
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--interactive-story",action="store_true",
                      help="Package authored interactive stage choices (V2)")
    mode.add_argument("--walkable-story",action="store_true",
                      help="Produce full offline walkable scene quest prototype (V3)")
    parser.add_argument("--genre",help="Optional registered source taxonomy filter")
    parser.add_argument("--biome",help="Optional registered source taxonomy filter")
    parser.add_argument("--working-set-bytes",type=int,default=64*1024*1024,
                        help="Estimated per-project physical RAM needed; not a file limit")
    parser.add_argument("--estimated-output-bytes",type=int,default=4*1024*1024,
                        help="Estimated per-project output size, checked against live free disk")
    args=parser.parse_args(argv)
    from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
    from skeleton.ai.game_builder.studio_ecosystem_catalog import StudioEcosystemError
    try:
        owner=StudioPortfolio(args.private_root,authorized=True)
        selection=None if args.all else args.project
        report=build_catalog_preview_batch(
            owner,args.output_root,project_ids=selection,
            genre=args.genre,biome=args.biome,
            working_set_bytes=args.working_set_bytes,
            estimated_output_bytes=args.estimated_output_bytes,
            interactive_story=args.interactive_story,
            walkable_story=args.walkable_story,
            authorized=True)
    except (StudioQuestError,StudioEcosystemError,OSError,ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report,sort_keys=True,ensure_ascii=True,allow_nan=False))
    return 0 if report["all_projects_completed"] else 2


if __name__=="__main__":
    raise SystemExit(main())
