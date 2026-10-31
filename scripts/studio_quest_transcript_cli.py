"""Verify a copied interactive browser quest transcript without any web server."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint,StudioEcosystemError
from skeleton.ai.game_builder.studio_ecosystem_story_review import inspect_browser_story_receipt
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description="Replay an untrusted offline story transcript")
    parser.add_argument("--project",required=True)
    parser.add_argument("--transcript",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)
        with os.fdopen(os.open(args.transcript,flags),"rb") as stream:
            stat_info=os.fstat(stream.fileno())
            if not stat.S_ISREG(stat_info.st_mode) or stat_info.st_size>65536:
                raise StudioQuestError("story transcript must be a bounded regular file")
            raw=stream.read(65537)
        if len(raw)>65536:
            raise StudioQuestError("story transcript exceeds replay budget")
        report=inspect_browser_story_receipt(raw,read_blueprint(args.project),
                                               authorized=True)
    except (StudioQuestError,StudioEcosystemError,OSError,ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report,ensure_ascii=True,sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
