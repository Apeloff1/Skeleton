"""Operator-controlled game specialization from *verified live Jeeves weights*.

This command is the execution seam for a compiled Skeleton app. It cannot
create a production parent, fake a runtime attestation, or use scratch weights.
It checks custody, backs up the immutable parent, trains a separate candidate,
and produces a fresh output comparison for independent game-design review.

No automatic production activation. Operator retains sole promotion authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import re
import sys
import time
from typing import Any

from .jeeves_production_game_train import ProductionCheckpointError, train
from .jeeves_production_readiness import (
    _save_new_private,
    inspect,
    prepare_training_copy,
)
from .jeeves_game_design_benchmark import compare, publish_review

SCHEMA = "skeleton.jeeves.production_game_training_session.v1"
_RUN_ID = re.compile(r"[a-z][a-z0-9_-]{2,47}")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _new_receipt(target: Path, payload: dict[str, Any]) -> None:
    data = (json.dumps(payload, sort_keys=True, indent=2,
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    _save_new_private(target, data)


def required_free_bytes(
    *, checkpoint_bytes: int, snapshot_bytes: int,
    batches_per_epoch: int, epochs: int,
) -> int:
    """Admission budget for immutable batch snapshots and retained evidence.

    Snapshot growth (extra tokens), JSON staging, and concurrent fsync files
    can raise peak disk use above the sum of finalized artifacts; reserve 2x
    snapshot storage, 3x parent bytes, and a 512 MiB operating-system margin.
    """
    values = (checkpoint_bytes, snapshot_bytes, batches_per_epoch, epochs)
    if any(type(value) is not int or value < 1 for value in values):
        raise ProductionCheckpointError("missing valid checkpoint size or optimizer batch estimate")
    if epochs > 3 or batches_per_epoch > 100:
        raise ProductionCheckpointError("training snapshot storage estimate exceeds bounds")
    return (
        512 * 1024 * 1024
        + 3 * checkpoint_bytes
        + 2 * snapshot_bytes * (batches_per_epoch * epochs + 1)
    )


def run(
    *,
    run_id: str,
    attestation: Path,
    output_directory: Path,
    epochs: int = 1,
    learning_rate: float = 0.005,
    max_domain_regression: float = 0,
    min_coverage: float = 0.8,
    dry_run: bool = False,
    expand_vocabulary: bool = False,
    max_optimizer_steps: int = 25000,
    max_training_seconds: int = 1200,
    resume: bool = False,
    dataset_manifest: Path | None = None,
    studio_corpus: Path | None = None,
    studio_corpus_expected_sha256: str | None = None,
) -> dict[str, Any]:
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ProductionCheckpointError("run id must be 3-48 safe lowercase characters")
    if any(type(flag) is not bool for flag in (dry_run, expand_vocabulary, resume)):
        raise ProductionCheckpointError("dry_run, expand_vocabulary and resume must be boolean")
    if type(epochs) is not int or not 1 <= epochs <= 3:
        raise ProductionCheckpointError("epochs must be between 1 and 3")
    for label, value, upper in (
        ("learning rate", learning_rate, .03),
        ("minimum coverage", min_coverage, 1.0),
        ("maximum regression", max_domain_regression, 0.10),
    ):
        if type(value) not in (int, float) or not 0 <= value <= upper or not float(value) < float("inf"):
            raise ProductionCheckpointError("invalid " + label)
    if learning_rate <= 0:
        raise ProductionCheckpointError("training learning rate must be > 0")
    if (studio_corpus is None) != (studio_corpus_expected_sha256 is None):
        raise ProductionCheckpointError("studio training corpus must be independently pinned")
    if studio_corpus is not None and dataset_manifest is not None:
        raise ProductionCheckpointError(
            "approved external holdout corpus and original-only game corpus cannot be combined"
        )
    replayed_count = 0
    if studio_corpus is not None:
        from .jeeves_studio_curriculum import load_studio_curriculum
        measured, _ = load_studio_curriculum(
            studio_corpus, expected_sha256=studio_corpus_expected_sha256,
        )
        replayed_count = len(measured)
    report = inspect(
        attestation=attestation, candidate_directory=output_directory,
        allow_vocabulary_expansion=expand_vocabulary,
        dataset_manifest=dataset_manifest,
    )
    if report["status"] == "ready_for_operator_training":
        minimum = required_free_bytes(
            checkpoint_bytes=report["checkpoint_bytes"],
            snapshot_bytes=report["selected_model_snapshot_bytes"],
            batches_per_epoch=report["training_batches_per_epoch"] + (replayed_count + 7) // 8,
            epochs=epochs,
        )
        report["estimated_required_free_bytes"] = minimum
        current_free = shutil.disk_usage(output_directory).free
        report["currently_free_bytes"] = current_free
        if current_free < minimum:
            report["blockers"].append("insufficient_disk_for_immutable_batch_checkpoints")
            report["status"] = "blocked"
    if dry_run or report["status"] != "ready_for_operator_training":
        return {
            "schema_version": SCHEMA,
            "status": "dry_run_ready" if dry_run and report["status"] == "ready_for_operator_training" else "blocked",
            "training_executed": False,
            "production_weights_modified": False,
            "candidate_promoted": False,
            "preflight": report,
            "studio_corpus_sha256": studio_corpus_expected_sha256,
            "studio_replayed_examples": replayed_count,
        }
    baseline = Path(report["checkpoint_path"])
    if output_directory.resolve() == baseline.parent.resolve():
        raise ProductionCheckpointError("training outputs cannot share the live checkpoint folder")
    if attestation.resolve().parent == output_directory.resolve():
        raise ProductionCheckpointError("attestation and training receipts must reside in separate directories")
    out = output_directory.expanduser()
    names = {
        "backup": out / (run_id + "-parent-backup.json"),
        "candidate": out / (run_id + "-candidate.json"),
        "training": out / (run_id + "-training.json"),
        "game_review": out / (run_id + "-game-review.json"),
        "manifest": out / (run_id + "-manifest.json"),
    }
    if len({x.resolve() for x in names.values()}) != len(names):
        raise ProductionCheckpointError("training output path identity collision")
    for label, path in names.items():
        if path.is_symlink() or (path.exists() and not (resume and label == "backup")):
            raise ProductionCheckpointError("training output already exists: " + path.name)
    if resume and not names["backup"].is_file():
        raise ProductionCheckpointError("resume requires the previous exact parent backup")
    start_sha = report["checkpoint_sha256"]
    if _sha(baseline) != start_sha:
        raise ProductionCheckpointError("active production state changed since preflight")

    # Write an independently verified, immutable parent copy before any SGD.
    if resume:
        if _sha(names["backup"]) != start_sha:
            raise ProductionCheckpointError("resumed parent backup differs from verified production state")
        backup = {"parent_sha256": start_sha}
    else:
        backup = prepare_training_copy(
            attestation=attestation,
            candidate_directory=out,
            copy_destination=names["backup"],
            allow_vocabulary_expansion=expand_vocabulary,
            dataset_manifest=dataset_manifest,
        )
    if _sha(baseline) != _sha(names["backup"]):
        raise ProductionCheckpointError("serving weights differ from prepared backup")

    trained = train(
        baseline,
        expected=start_sha,
        candidate=names["candidate"],
        report=names["training"],
        epochs=epochs,
        lr=float(learning_rate),
        min_coverage=float(min_coverage),
        max_domain_regression=float(max_domain_regression),
        expand_vocabulary=expand_vocabulary,
        dataset_manifest=dataset_manifest,
        studio_corpus=studio_corpus,
        studio_corpus_expected_sha256=studio_corpus_expected_sha256,
        max_optimizer_steps=max_optimizer_steps,
        max_training_seconds=max_training_seconds,
        progress_directory=out,
        progress_run_id=run_id,
        resume=resume,
    )
    if _sha(baseline) != start_sha:
        raise ProductionCheckpointError("live serving weights changed during training")
    if trained["status"] == "rejected_evaluation_gate":
        outcome = {
            "schema_version": SCHEMA,
            "status": "rejected_heldout_gate",
            "parent_checkpoint_sha256": start_sha,
            "parent_backup_sha256": backup["parent_sha256"],
            "training_report_path": str(names["training"].resolve()),
            "studio_corpus_sha256": trained["studio_corpus_sha256"],
            "studio_replay_verified_examples": trained["studio_replay_verified_examples"],
            "candidate_promoted": False,
            "game_design_improvement_established": False,
            "production_weights_modified": False,
        }
        _new_receipt(names["manifest"], outcome)
        return outcome

    if not names["candidate"].is_file():
        raise ProductionCheckpointError("trainer claims success but candidate checkpoint missing")
    review = publish_review(
        compare(baseline, names["candidate"], expected_parent_sha256=start_sha),
        names["game_review"],
    )
    if _sha(baseline) != start_sha:
        raise ProductionCheckpointError("live serving weights changed during game-design review")
    outcome = {
        "schema_version": SCHEMA,
        "status": "candidate_trained_requires_independent_review",
        "run_id": run_id,
        "parent_checkpoint_sha256": start_sha,
        "parent_backup_sha256": backup["parent_sha256"],
        "parent_backup_path": str(names["backup"].resolve()),
        "candidate_path": str(names["candidate"].resolve()),
        "candidate_sha256": _sha(names["candidate"]),
        "training_report_path": str(names["training"].resolve()),
        "training_report_sha256": _sha(names["training"]),
        "game_review_report_path": str(names["game_review"].resolve()),
        "game_review_report_sha256": _sha(names["game_review"]),
        "benchmark_prompts": review["fresh_heldout_prompts"],
        "vocabulary_expansion_opted_in": expand_vocabulary,
        "max_optimizer_steps": max_optimizer_steps,
        "max_training_seconds": max_training_seconds,
        "resumed_from_existing_progress": resume,
        "resumable_optimizer_cursors": True,
        "dataset_manifest": None if dataset_manifest is None else str(dataset_manifest.resolve()),
        "dataset_source": trained["dataset_receipt"],
        "studio_corpus_sha256": trained["studio_corpus_sha256"],
        "studio_replay_verified_examples": trained["studio_replay_verified_examples"],
        "human_review_complete": False,
        "game_design_improvement_established": False,
        "production_weights_modified": False,
        "candidate_promoted": False,
    }
    _new_receipt(names["manifest"], outcome)
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--studio-corpus", type=Path)
    parser.add_argument("--studio-corpus-expected-sha256")
    parser.add_argument("--dataset-manifest", type=Path,
                        help="rights-approved external game training/evaluation corpus")
    parser.add_argument("--attestation", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true",
                        help="resume an interrupted run from its immutable optimizer stages")
    parser.add_argument("--expand-vocabulary", action="store_true",
                        help="opt in to native BPE token growth on cloned candidate")
    parser.add_argument("--epochs", default=1, type=int)
    parser.add_argument("--max-optimizer-steps", default=25000, type=int)
    parser.add_argument("--max-training-seconds", default=1200, type=int)
    parser.add_argument("--learning-rate", default=0.005, type=float)
    parser.add_argument("--max-domain-regression", default=0.0, type=float)
    parser.add_argument("--min-coverage", default=0.8, type=float)
    args = parser.parse_args(argv)
    try:
        result = run(
            run_id=args.run_id,
            attestation=args.attestation,
            output_directory=args.output_directory,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            max_domain_regression=args.max_domain_regression,
            min_coverage=args.min_coverage,
            dry_run=args.dry_run,
            expand_vocabulary=args.expand_vocabulary,
            max_optimizer_steps=args.max_optimizer_steps,
            max_training_seconds=args.max_training_seconds,
            resume=args.resume,
            dataset_manifest=args.dataset_manifest,
            studio_corpus=args.studio_corpus,
            studio_corpus_expected_sha256=args.studio_corpus_expected_sha256,
        )
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        return 0 if result["status"] in (
            "dry_run_ready", "candidate_trained_requires_independent_review"
        ) else 3
    except (OSError, ValueError, RuntimeError, TypeError, ImportError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:500]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
