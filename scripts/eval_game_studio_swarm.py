"""Score held-out game briefs against build_playable_game.

The fast subset is one held-out build plus the negative controls. Exit status
is 0 only when positives clear the build/core-loop bar and negatives stay low.
A perfect 1.0 mean is rejected: playtest-off runs cannot claim a Godot boot.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skeleton.automation.swarm.studio import run_benchmark


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the game-studio swarm benchmark.")
    parser.add_argument("--fast", action="store_true", help="Run only the small CI subset.")
    parser.add_argument("--workspace", default=None, help="Unused. Kept so older invocations still parse.")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace) if args.workspace else None
    report = run_benchmark(fast=args.fast, workspace_root=workspace)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
