"""Read and verify an offline 2D physics transcript without network or uploads."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from skeleton.ai.game_builder.studio_ecosystem_catalog import (
    read_blueprint, StudioEcosystemError,
)
from skeleton.ai.game_builder.studio_ecosystem_walk_review import review_walk_events
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay source-owned offline walk events, including walls and object proximity"
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--events", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(args.events, flags), "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_size > 4*1024*1024):
                raise StudioQuestError("untrusted physics events must be bounded regular bytes")
            raw = stream.read(4*1024*1024+1)
        report = review_walk_events(raw, read_blueprint(args.project), authorized=True)
    except (StudioQuestError, StudioEcosystemError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
