"""Inspect all local ROM candidates and train eligible ROM Q-policies on the real emulator lab.

No ROM download, emulated-completion claim, or automatic production-weight change.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.ai.training.rom_study import (
    RomStudyError, inventory_page, train_page,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="operation", required=True)
    inventory = commands.add_parser("inventory", help="read-only ROM inventory")
    inventory.add_argument("--root", required=True, type=Path)
    inventory.add_argument("--cursor")
    inventory.add_argument("--limit", type=int, default=64)
    train = commands.add_parser("train-all", help="run approved Q-policy learning per ROM")
    train.add_argument("--root", required=True, type=Path)
    train.add_argument("--approvals", required=True, type=Path)
    train.add_argument("--output-dir", required=True, type=Path)
    train.add_argument("--cursor")
    train.add_argument("--limit", type=int, default=32)
    train.add_argument("--max-pages", type=int, default=1,
                       help="0 scans all pages in this foreground invocation")
    train.add_argument("--runs", type=int, default=12)
    train.add_argument("--steps", type=int, default=24)
    train.add_argument("--seed", type=int, default=0)
    train.add_argument("--neural-world", action="store_true",
                       help="also train a checkpointed candidate neural world model from replay evidence")
    train.add_argument("--neural-epochs", type=int, default=4)
    train.add_argument("--neural-width", type=int, default=8)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.operation == "inventory":
            print(json.dumps(inventory_page(args.root, cursor=args.cursor, limit=args.limit),
                             sort_keys=True))
            return 0
        if type(args.max_pages) is not int or not 0 <= args.max_pages <= 100_000:
            raise RomStudyError("max_pages must be 0 (whole inventory) or 1..100000")
        cursor, pages = args.cursor, 0
        while True:
            result = train_page(
                args.root, args.approvals, args.output_dir, cursor=cursor,
                limit=args.limit, runs=args.runs, steps=args.steps, seed=args.seed,
                neural_world=args.neural_world, neural_epochs=args.neural_epochs,
                neural_width=args.neural_width,
            )
            pages += 1
            print(json.dumps({
                "page_number": pages,
                "initial_cursor": cursor,
                "next_cursor": result["next_cursor"],
                "inventory_exhausted": result["finished_inventory"],
                "q_policies_updated": result["q_policy_training_completed"],
                "executed_without_updates": result["q_policy_runs_without_updates"],
                "blocked_or_unreviewed": result["blocked_or_unreviewed"],
                "neural_candidates_trained": result["neural_candidate_training_completed"],
                "results": result["page_results"],
                "neural_weights_updated": 0,
                "production_weights_modified": False,
            }, sort_keys=True), flush=True)
            cursor = result["next_cursor"]
            if cursor is None or args.max_pages and pages >= args.max_pages:
                return 0
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        print("ROM training blocked: " + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
