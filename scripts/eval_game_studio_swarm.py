#!/usr/bin/env python3
"""Score the game-studio swarm against the brief benchmark.

The fast subset is the CI-sized run. The full subset adds genre coverage and
one adversarial pitch. No network and no provider credentials are used.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import skeleton.swarm  # noqa: F401  — safe init order for the swarm package
from skeleton.automation.swarm.studio import run_benchmark


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the game-studio swarm benchmark.")
    parser.add_argument("--fast", action="store_true", help="Run only the small CI subset.")
    parser.add_argument("--workspace", default=None, help="Directory for case workspaces.")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace) if args.workspace else None
    report = run_benchmark(fast=args.fast, workspace_root=workspace)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if report["mean_total"] >= 0.75 else 1


if __name__ == "__main__":
    raise SystemExit(main())
