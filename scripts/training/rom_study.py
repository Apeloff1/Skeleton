"""Operator CLI: discover all local ROMs, then train each admitted ROM on real cores."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from skeleton.ai.training.rom_study import (
    RomFleetError, _write_new, discover, train_all, validate_manifest,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Inventory local ROMs and train only individually rights-cleared sources."
    )
    subs = p.add_subparsers(dest="operation", required=True)
    scan = subs.add_parser("inventory", help="write review-pending ROM inventory, no execution")
    scan.add_argument("--root", required=True, type=Path)
    scan.add_argument("--output", required=True, type=Path)
    check = subs.add_parser("verify", help="validate operator-owned ROM manifest")
    check.add_argument("--manifest", required=True, type=Path)
    train = subs.add_parser("train-all", help="train admitted ROMs on actual compatible cores")
    train.add_argument("--manifest", required=True, type=Path)
    train.add_argument("--output-dir", required=True, type=Path)
    train.add_argument("--seed", type=int, default=0)
    train.add_argument("--runs", type=int, default=12)
    train.add_argument("--steps", type=int, default=12)
    train.add_argument("--neural", action="store_true",
                       help="train local candidate MLP as well as verified tabular Q")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.operation == "inventory":
            result = discover(args.root)
            _write_new(args.output, result)
            summary = {
                "status": "awaiting_individual_rights_review",
                "manifest": str(args.output),
                "discovered_roms": result["inventory_count"],
                "model_training_executed": False,
            }
        elif args.operation == "verify":
            _root, rows, digest = validate_manifest(args.manifest)
            summary = {
                "status": "manifest_verified",
                "roms": len(rows), "manifest_sha256": digest,
                "authorized_roms": sum(
                    r["rights"].get("training_permitted") is True for r in rows),
                "training_executed": False,
            }
        else:
            summary = train_all(
                args.manifest, args.output_dir, seed=args.seed,
                max_runs=args.runs, steps=args.steps, neural=args.neural,
            )
            # Any partial or blocked result is surfaced to the operator.
            # Per-ROM receipts are committed separately after actual training.
        print(json.dumps(summary, sort_keys=True, indent=2))
        return 0 if summary.get("roms_covered", 0) == summary.get("roms_authorized", 0) else 2
    except (RomFleetError, OSError, ValueError, RuntimeError, ImportError) as exc:
        print("ROM fleet blocked: " + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
