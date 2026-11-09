"""Offline dataset release gate and train-only export for Skeleton.

Validation never fetches data or starts model training. Training admission
uses the repository's existing governed DatasetRegistry; candidate weights
still require separate independent evaluation and promotion authorization.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from skeleton.ai.training.offline_foundations import (
    SyntheticCurriculumError,
    evaluate_predictions,
    register_with_training_registry,
    validate_curriculum,
)
from skeleton.ai.training.sparse_capability import (
    DEFAULT_BUDGET, build_sparse_capability_plan,
    register_sparse_capability_plan, sparse_plan_receipt,
)


DEFAULT_DATASET = (
    Path(__file__).resolve().parents[2]
    / "skeleton/ai/training/datasets/offline_foundations_v1"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify_offline_foundations",
        description="Validate offline training data, register rights, or evaluate held-out predictions.",
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--register-db", type=Path,
                           help="register sparse 36-row training subset in local SQLite")
    operation.add_argument("--register-reference-bank-db", type=Path,
                           help="EXPLICITLY register all 504 train rows of the reference bank")
    operation.add_argument("--evaluate", type=Path,
                           help="predictions JSONL with id and prediction, never training records")
    operation.add_argument("--export-train", type=Path,
                           help="write 36-row sparse training corpus to a NEW file")
    operation.add_argument("--export-reference-bank", type=Path,
                           help="EXPLICITLY export the full 504-row train-only reference corpus")
    parser.add_argument("--split", choices=("validation", "test"), default=None,
                        help="held-out evaluation split (only used with --evaluate)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.split is not None and args.evaluate is None:
        print("--split requires --evaluate and may never select training data", file=sys.stderr)
        return 2
    try:
        report = validate_curriculum(args.dataset)
        sparse_mode = args.register_db is not None or args.export_train is not None
        if sparse_mode:
            plan = build_sparse_capability_plan(args.dataset, budget=DEFAULT_BUDGET)
            report = {**report, **sparse_plan_receipt(plan)}
        if args.register_db is not None or args.register_reference_bank_db is not None:
            from skeleton.ai.runtime.training.data import DatasetRegistry
            path = (
                args.register_db if args.register_db is not None
                else args.register_reference_bank_db
            ).expanduser()
            if path.is_symlink() or not path.parent.is_dir() or (
                path.exists() and not path.is_file()
            ):
                raise SyntheticCurriculumError("registry must be a local regular SQLite path")
            if path.absolute().is_relative_to(args.dataset.resolve()):
                raise SyntheticCurriculumError(
                    "training registry cannot be created inside source dataset"
                )
            registry = DatasetRegistry(path)
            try:
                digest = (
                    register_sparse_capability_plan(args.dataset, plan, registry)
                    if args.register_db is not None
                    else register_with_training_registry(args.dataset, registry)
                )
            finally:
                registry.close()
            report = {
                **report, "registered_dataset_digest": digest,
                "governed_training_ready": True,
                "registered_training_rows": (
                    DEFAULT_BUDGET if args.register_db is not None else 504
                ),
                "full_bank_explicitly_selected": args.register_reference_bank_db is not None,
                "trained_weights_promoted": False,
            }
        elif args.evaluate is not None:
            report = evaluate_predictions(
                args.dataset, args.evaluate, split=args.split or "validation"
            )
        elif args.export_train is not None or args.export_reference_bank is not None:
            destination = (
                args.export_train if args.export_train is not None
                else args.export_reference_bank
            ).expanduser().absolute()
            if destination.is_symlink() or destination.exists() or not destination.parent.is_dir():
                raise SyntheticCurriculumError("train export requires a new local file")
            if destination.is_relative_to(args.dataset.resolve()):
                raise SyntheticCurriculumError("cannot create export inside verified dataset")
            raw = (
                plan["training_text"]
                if args.export_train is not None
                else (args.dataset / "train_corpus.txt").read_bytes()
            )
            # Exclusive creation prevents clobbering another process' data.
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(destination, flags, 0o600)
            with os.fdopen(descriptor, "wb") as writer:
                writer.write(raw)
                writer.flush()
                os.fsync(writer.fileno())
            report = {
                **report,
                "exported_train_only": str(destination),
                "held_out_examples_exported": 0,
                "exported_training_rows": (
                    DEFAULT_BUDGET if args.export_train is not None else 504
                ),
                "full_bank_explicitly_selected": args.export_reference_bank is not None,
            }
        print(json.dumps(report, sort_keys=True, ensure_ascii=False))
        return 0
    except (SyntheticCurriculumError, ValueError, OSError, RuntimeError) as exc:
        print("offline training-data admission rejected: "
              + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
