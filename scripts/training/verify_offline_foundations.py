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
                           help="register synthetic rights and quality gates in local SQLite")
    operation.add_argument("--evaluate", type=Path,
                           help="predictions JSONL with id and prediction, never training records")
    operation.add_argument("--export-train", type=Path,
                           help="write a NEW train-only plain text corpus; never export held-out labels")
    parser.add_argument("--split", choices=("validation", "test"), default="validation",
                        help="held-out evaluation split (only used with --evaluate)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = validate_curriculum(args.dataset)
        if args.register_db is not None:
            from skeleton.ai.runtime.training.data import DatasetRegistry
            path = args.register_db.expanduser()
            if path.is_symlink() or not path.parent.is_dir() or (
                path.exists() and not path.is_file()
            ):
                raise SyntheticCurriculumError("registry must be a local regular SQLite path")
            registry = DatasetRegistry(path)
            try:
                digest = register_with_training_registry(args.dataset, registry)
            finally:
                registry.close()
            report = {
                **report, "registered_dataset_digest": digest,
                "governed_training_ready": True,
                "trained_weights_promoted": False,
            }
        elif args.evaluate is not None:
            report = evaluate_predictions(args.dataset, args.evaluate, split=args.split)
        elif args.export_train is not None:
            destination = args.export_train.expanduser().absolute()
            if destination.is_symlink() or destination.exists() or not destination.parent.is_dir():
                raise SyntheticCurriculumError("train export requires a new local file")
            if destination.parent.resolve() == args.dataset.resolve():
                raise SyntheticCurriculumError("cannot create export inside verified dataset")
            raw = (args.dataset / "train_corpus.txt").read_bytes()
            # Exclusive creation prevents clobbering another process' data.
            with destination.open("xb") as writer:
                writer.write(raw)
                writer.flush()
                os.fsync(writer.fileno())
            if os.name == "posix":
                os.chmod(destination, 0o600)
            report = {
                **report,
                "exported_train_only": str(destination),
                "held_out_examples_exported": 0,
            }
        print(json.dumps(report, sort_keys=True, ensure_ascii=False))
        return 0
    except (SyntheticCurriculumError, ValueError, OSError, RuntimeError) as exc:
        print("offline training-data admission rejected: "
              + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
