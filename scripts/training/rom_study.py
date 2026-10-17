"""Operator-run, resumable ROM census and *real Q-policy* training over local content.

No automatic download, no unknown content execution, no model-weight promotion.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.ai.training.rom_study import RomStudyError, inventory_page, train_page


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="operation", required=True)
    inventory = commands.add_parser("inventory", help="list operator-local ROM candidates")
    inventory.add_argument("--root", required=True, type=Path)
    inventory.add_argument("--cursor")
    inventory.add_argument("--limit", type=int, default=64)
    run = commands.add_parser("train-all", help="run reviewed ROM Q-policy training, page by page")
    run.add_argument("--root", required=True, type=Path)
    run.add_argument("--approvals", required=True, type=Path)
    run.add_argument("--output-dir", required=True, type=Path)
    run.add_argument("--cursor")
    run.add_argument("--limit", type=int, default=32)
    run.add_argument("--max-pages", type=int, default=1,
                     help="page admission per call; 0 means exhaust the collection")
    run.add_argument("--runs", type=int, default=12)
    run.add_argument("--steps", type=int, default=24)
    run.add_argument("--seed", type=int, default=0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.operation == "inventory":
            print(json.dumps(inventory_page(args.root, cursor=args.cursor, limit=args.limit),
                             sort_keys=True, indent=2))
            return 0
        if not 0 <= args.max_pages <= 100_000:
            raise RomStudyError("max_pages must be 0 (exhaustive) or 1..100000")
        cursor = args.cursor
        pages = 0
        while True:
            page = train_page(
                args.root, args.approvals, args.output_dir, cursor=cursor,
                limit=args.limit, runs=args.runs, steps=args.steps, seed=args.seed,
            )
            pages += 1
            print(json.dumps({
                "page_number": pages,
                "initial_cursor": cursor,
                "next_cursor": page["next_cursor"],
                "inventory_exhausted": page["finished_inventory"],
                "trained": page["q_policy_training_completed"],
                "blocked_or_unreviewed": page["blocked_or_unreviewed"],
                "results": page["page_results"],
                "neural_weights_updated": 0,
                "production_weights_modified": False,
            }, sort_keys=True), flush=True)
            cursor = page["next_cursor"]
            if cursor is None or args.max_pages and pages >= args.max_pages:
                return 0
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        print("ROM study stopped: " + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
