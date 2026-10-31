"""Score the studio swarm against the bare builder on held-out briefs.

The fast subset is one held-out brief plus the negative controls. Exit status
is 0 when both the studio and the bare builder clear the build and core-loop
bar, the studio attaches planner notes and a QA review, and negatives stay
low. Boots is not_measured while playtest is off. When Godot is available the
runs require a real boot.
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
    parser.add_argument("--workspace", default=None, help="Directory for studio eval workspaces.")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace) if args.workspace else None
    report = run_benchmark(fast=args.fast, workspace_root=workspace)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
