"""Sparse capability-first model preparation and held-out proficiency CLI.

Default training material = 36 samples, one for each distinct task mode.
The 720-row source bank is retained as audited reference/evaluation data.
Never expand the source corpus, fetch URLs, or promote weights implicitly.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from skeleton.ai.training.offline_foundations import SyntheticCurriculumError
from skeleton.ai.training.sparse_capability import (
    DEFAULT_BUDGET, HARDWARE_BUDGETS,
    assess_heldout_capabilities, build_sparse_capability_plan,
    register_sparse_capability_plan, sparse_plan_receipt,
)


DATASET = (
    Path(__file__).resolve().parents[2]
    / "skeleton/ai/training/datasets/offline_foundations_v1"
)


def _new_file(destination: Path, payload: bytes, *, dataset: Path) -> Path:
    target = destination.expanduser().absolute()
    if (
        target.is_symlink() or target.exists() or not target.parent.is_dir()
        or target.is_relative_to(dataset.resolve())
    ):
        raise SyntheticCurriculumError(
            "sparse export requires a new regular file outside the dataset"
        )
    fd = os.open(
        target,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(fd, "wb") as writer:
            writer.write(payload)
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        # Never delete a competing writer's replacement after a failure.
        try:
            if target.exists() and target.stat().st_nlink >= 1:
                target.unlink()
        except OSError:
            pass
        raise
    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare 36-72 supervised samples without expanding the synthetic data bank."
    )
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--profile", choices=tuple(HARDWARE_BUDGETS), default="low-memory",
                        help="maximum active samples, not an actual hardware benchmark")
    parser.add_argument("--budget", type=int, default=None,
                        help="36-72 samples; cannot exceed selected hardware profile")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--export", type=Path,
                           help="write sparse train-only text, exclusive new file")
    operation.add_argument("--export-jsonl", type=Path,
                           help="write selected sparse train-only JSONL, exclusive new file")
    operation.add_argument("--register-db", type=Path,
                           help="register ONLY sparse training subset in existing governance")
    operation.add_argument("--evaluate", type=Path,
                           help="score predictions per capability; cannot be used to train")
    parser.add_argument("--split", choices=("validation", "test"), default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.split is not None and args.evaluate is None:
        print("--split requires --evaluate", file=sys.stderr)
        return 2
    budget = HARDWARE_BUDGETS[args.profile] if args.budget is None else args.budget
    if (
        type(budget) is not int or budget < DEFAULT_BUDGET
        or budget > HARDWARE_BUDGETS[args.profile]
    ):
        print("sparse data budget violates selected hardware profile", file=sys.stderr)
        return 2
    try:
        plan = build_sparse_capability_plan(args.dataset, budget=budget)
        report = sparse_plan_receipt(plan)
        report["hardware_profile"] = args.profile
        report["hardware_benchmark_run"] = False
        if args.export is not None:
            result = _new_file(
                args.export, plan["training_text"], dataset=args.dataset,
            )
            report["exported_sparse_training_text"] = str(result)
        elif args.export_jsonl is not None:
            result = _new_file(
                args.export_jsonl, plan["active_jsonl"], dataset=args.dataset,
            )
            report["exported_sparse_training_jsonl"] = str(result)
        elif args.register_db is not None:
            from skeleton.ai.runtime.training.data import DatasetRegistry
            target = args.register_db.expanduser().absolute()
            if (
                target.is_symlink() or not target.parent.is_dir()
                or (target.exists() and not target.is_file())
                or target.is_relative_to(args.dataset.resolve())
            ):
                raise SyntheticCurriculumError(
                    "sparse registry requires a local SQLite path outside source data"
                )
            registry = DatasetRegistry(target)
            try:
                digest = register_sparse_capability_plan(args.dataset, plan, registry)
            finally:
                registry.close()
            report["registered_sparse_dataset_digest"] = digest
            report["governed_training_ready"] = True
        elif args.evaluate is not None:
            report = {
                **report,
                "heldout_proficiency": assess_heldout_capabilities(
                    args.dataset, args.evaluate, split=args.split or "validation",
                ),
            }
        print(json.dumps(report, sort_keys=True, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(
            "sparse capability admission rejected: "
            + type(exc).__name__ + ": " + str(exc),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
