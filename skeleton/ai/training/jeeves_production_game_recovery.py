"""Finish an interrupted production-derived game candidate WITHOUT retraining.

Only runs where immutable candidate weights and the original training report
already exist may be finalized. Recovery replays the 24 independent game-design
prompts against the original and candidate. It never updates serving weights,
overwrites an existing review, reuses another source checkpoint, or promotes.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any

from .jeeves_game_corpus import load_approved_corpus
from .jeeves_game_design_benchmark import compare, publish_review
from .jeeves_production_game_train import (
    MAX_BYTES, ProductionCheckpointError, SCHEMA as TRAIN_SCHEMA, _strict_json,
)
from .jeeves_production_readiness import _canonical, _save_new_private, inspect
from .jeeves_production_game_session import SCHEMA as SESSION_SCHEMA

RUN_ID = re.compile(r"[a-z][a-z0-9_-]{2,47}\Z")


def _read(path: Path, maximum: int = MAX_BYTES) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ProductionCheckpointError("recovery requires existing regular candidate artifacts")
    if not 64 <= path.stat().st_size <= maximum:
        raise ProductionCheckpointError("recovery artifact outside bounded file size")
    return _strict_json(path.read_bytes())


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finalize(
    *, run_id: str, attestation: Path, output_directory: Path,
    dataset_manifest: Path, expand_vocabulary: bool = False,
) -> dict[str, Any]:
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ProductionCheckpointError("invalid interrupted run ID")
    if type(expand_vocabulary) is not bool:
        raise ProductionCheckpointError("vocabulary expansion flag must be boolean")
    if output_directory.is_symlink() or not output_directory.is_dir():
        raise ProductionCheckpointError("recovery directory must be a regular existing folder")
    names = {
        "backup": output_directory / (run_id + "-parent-backup.json"),
        "candidate": output_directory / (run_id + "-candidate.json"),
        "training": output_directory / (run_id + "-training.json"),
        "review": output_directory / (run_id + "-game-review.json"),
        "manifest": output_directory / (run_id + "-manifest.json"),
    }
    if any(path.is_symlink() for path in names.values()):
        raise ProductionCheckpointError("recovery refuses symlink candidate artifacts")
    if names["manifest"].exists():
        raise ProductionCheckpointError("training session has already been finalized")
    if output_directory.resolve() == dataset_manifest.resolve().parent:
        raise ProductionCheckpointError("model outputs cannot share dataset source directory")
    preflight = inspect(
        attestation=attestation,
        candidate_directory=output_directory,
        dataset_manifest=dataset_manifest,
        allow_vocabulary_expansion=expand_vocabulary,
    )
    if preflight["status"] != "ready_for_operator_training":
        raise ProductionCheckpointError(
            "production recovery admission blocked:" + ";".join(preflight["blockers"])
        )
    parent = Path(preflight["checkpoint_path"])
    expected = preflight["checkpoint_sha256"]
    _read(names["backup"])
    if _sha(names["backup"]) != expected:
        raise ProductionCheckpointError("backup does not match currently attested serving parent")
    candidate = _read(names["candidate"])
    training = _read(names["training"], maximum=16 * 1024 * 1024)
    if training.get("schema_version") != TRAIN_SCHEMA:
        raise ProductionCheckpointError("recovery requires an actual training receipt")
    if training.get("status") != "candidate_trained_needs_game_design_review":
        raise ProductionCheckpointError("recovery requires accepted candidate training, not a rejected run")
    if any(training.get(field) != value for field, value in (
        ("source_checkpoint_sha256", expected),
        ("candidate_sha256", _sha(names["candidate"])),
        ("production_weights_modified", False),
        ("candidate_promoted", False),
    )):
        raise ProductionCheckpointError("candidate/training receipt lineage or nonpromotion mismatch")
    if (type(training.get("training_steps_before")) is not int or
            type(training.get("training_steps_after")) is not int or
            training["training_steps_after"] <= training["training_steps_before"]):
        raise ProductionCheckpointError("candidate has no recorded genuine optimizer updates")
    _training, _heldout, corpus = load_approved_corpus(dataset_manifest)
    receipt = training.get("dataset_receipt")
    if not isinstance(receipt, dict) or any(
        receipt.get(field) != corpus.get(field)
        for field in ("manifest_sha256", "train_sha256", "heldout_sha256",
                      "rights_review_id", "train_examples", "heldout_examples")
    ):
        raise ProductionCheckpointError("recovery dataset differs from the original trained corpus")
    if training.get("built_in_smoke_curriculum_only") is not False:
        raise ProductionCheckpointError("cannot recover production session from smoke curriculum")
    if not isinstance(candidate.get("own"), dict) or not isinstance(candidate.get("lms"), dict):
        raise ProductionCheckpointError("recovery candidate is not a full Jeeves state")
    # Always regenerate the original versus candidate design replies. If a
    # prior review was published, require its contents to match reproducible
    # fresh model generations. Do not trust a self-asserted review document.
    replay = compare(parent, names["candidate"], expected_parent_sha256=expected)
    if names["review"].exists():
        existing = _read(names["review"], maximum=32 * 1024 * 1024)
        if _canonical(existing) != _canonical(replay):
            raise ProductionCheckpointError("existing review is inconsistent with independently replayed model")
    else:
        publish_review(replay, names["review"])
    if _sha(parent) != expected:
        raise ProductionCheckpointError("serving weights changed during recovery; cannot finalize")
    outcome: dict[str, Any] = {
        "schema_version": SESSION_SCHEMA,
        "status": "candidate_trained_requires_independent_review",
        "run_id": run_id,
        "recovered_after_interruption": True,
        "source_checkpoint_sha256": expected,
        "parent_checkpoint_sha256": expected,
        "parent_backup_sha256": _sha(names["backup"]),
        "parent_backup_path": str(names["backup"].resolve()),
        "candidate_path": str(names["candidate"].resolve()),
        "candidate_sha256": _sha(names["candidate"]),
        "training_report_path": str(names["training"].resolve()),
        "training_report_sha256": _sha(names["training"]),
        "game_review_report_path": str(names["review"].resolve()),
        "game_review_report_sha256": _sha(names["review"]),
        "dataset_manifest": str(dataset_manifest.resolve()),
        "dataset_source": corpus,
        "benchmark_prompts": len(replay["results"]),
        "human_review_complete": False,
        "game_design_improvement_established": False,
        "production_weights_modified": False,
        "candidate_promoted": False,
    }
    _save_new_private(names["manifest"], _canonical(outcome) + b"\n")
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--expand-vocabulary", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = finalize(
            run_id=args.run_id, attestation=args.attestation,
            output_directory=args.output_directory,
            dataset_manifest=args.dataset_manifest,
            expand_vocabulary=args.expand_vocabulary,
        )
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, TypeError, ImportError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:500]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
