"""Host-operated full-book intake -> dataset -> REAL Jeeves candidate weights.

One-shot, rights-pinned train pipeline over existing canonical modules. It
does not own a new store/model/provider. Files are exclusive new outputs;
interrupted operations are never automatically rerun or promoted.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

from .jeeves_book_curriculum import publish
from .jeeves_game_corpus_builder import build
from .jeeves_production_game_train import train, ProductionCheckpointError

SCHEMA = "skeleton.jeeves.book_training_operation.v1"


def _sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ProductionCheckpointError("Missing or symlinked training evidence: " + path.name)
    return sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _check_outputs(*targets: Path) -> None:
    if len(set(path.resolve() for path in targets)) != len(targets):
        raise ProductionCheckpointError("Training output paths must not alias")
    for path in targets:
        if path.is_symlink() or path.exists() or not path.parent.is_dir():
            raise ProductionCheckpointError("Outputs must be absent, non-symlinked, with existing parents")


def run_book_candidate(*, source: Path, source_sha256: str, intake: Path,
                       coverage: Path, dataset_directory: Path, prefix: str,
                       partition_seed: str, rights_review_id: str,
                       checkpoint: Path, checkpoint_sha256: str,
                       candidate: Path, report: Path, operation_receipt: Path,
                       epochs: int = 1, learning_rate: float = 0.005,
                       max_optimizer_steps: int = 25000,
                       max_training_seconds: int = 1200) -> dict[str, Any]:
    """Run native candidate training from real host checkpoint, never promote.

    Receipt written only after the actual candidate trainer has completed and
    its report/candidate file identities can be checked. Interim artifacts
    remain immutable for external reconciliation if a step fails.
    """
    if not checkpoint.is_absolute() or not checkpoint.is_file() or checkpoint.is_symlink():
        raise ProductionCheckpointError("Training needs an actual regular checkpoint file")
    if checkpoint_sha256 != _sha(checkpoint):
        raise ProductionCheckpointError("Serving checkpoint digest differs from independently pinned digest")
    _check_outputs(intake, coverage, candidate, report, operation_receipt)
    if not dataset_directory.is_dir() or dataset_directory.is_symlink():
        raise ProductionCheckpointError("Training dataset destination must be an existing directory")
    if dataset_directory.resolve() in (
        source.parent.resolve(), checkpoint.parent.resolve()
    ):
        raise ProductionCheckpointError("Training dataset outputs must be isolated from sources")
    if type(epochs) is not int or not 1 <= epochs <= 3:
        raise ProductionCheckpointError("Epoch count must be 1..3")
    if type(learning_rate) is not float or not 0 < learning_rate <= 0.03:
        raise ProductionCheckpointError("Learning rate must be 0..0.03")
    # Book source pinning, rights, chapter coverage and atomically sealed rows.
    intake_receipt = publish(source=source, expected_source_sha256=source_sha256,
                             intake=intake, coverage=coverage)
    # Existing domain/project-split approved dataset owner.
    dataset = build(intake=intake, destination=dataset_directory, prefix=prefix,
                    partition_seed=partition_seed, rights_review_id=rights_review_id)
    manifest = Path(dataset["paths"]["manifest"])
    if not manifest.is_file() or manifest.is_symlink():
        raise ProductionCheckpointError("Canonical production dataset manifest missing")
    # Actual checkpoint-derived neural training; this only writes a candidate.
    training = train(checkpoint, expected=checkpoint_sha256, candidate=candidate,
                     report=report, epochs=epochs, lr=learning_rate,
                     min_coverage=0.80, max_domain_regression=0.0,
                     max_optimizer_steps=max_optimizer_steps,
                     max_training_seconds=max_training_seconds,
                     dataset_manifest=manifest)
    if not isinstance(training, dict) or not report.is_file():
        raise ProductionCheckpointError("No actual model-candidate evaluation receipt")
    candidate_digest = _sha(candidate) if candidate.is_file() else None
    status = str(training.get("status", "unverified"))
    event0 = {"phase": "full_book_coverage", "source": source_sha256,
              "intake_sha256": intake_receipt["intake_sha256"],
              "coverage_sha256": intake_receipt["coverage_sha256"]}
    event1 = {"phase": "dataset_validation", "manifest_sha256": _sha(manifest),
              "train_sha256": dataset["train_sha256"],
              "heldout_sha256": dataset["heldout_sha256"]}
    event2 = {"phase": "checkpoint_candidate_training", "source_checkpoint_sha256": checkpoint_sha256,
              "candidate_sha256": candidate_digest, "evaluation_report_sha256": _sha(report),
              "training_status": status}
    events = [event0, event1, event2]
    prev = "0" * 64
    chain: list[dict[str, Any]] = []
    for event in events:
        prev = sha256(_canonical({"previous": prev, "event": event})).hexdigest()
        chain.append({"event": event, "chain_sha256": prev})
    operation = {"schema_version": SCHEMA, "status": status, "source_books_sha256": source_sha256,
                 "model_source_sha256": checkpoint_sha256, "events": chain,
                 "receipt_chain_sha256": prev, "production_weights_modified": False,
                 "training_executed": True, "candidate_promotion_performed": False,
                 "candidate_evaluation": "See actual candidate report; never infer grade from file existence"}
    # Only publish the final chain after all three stages have real receipts.
    with operation_receipt.open("xb") as output:
        output.write(_canonical(operation) + b"\n")
        output.flush()
    return {"schema_version": SCHEMA, "status": status,
            "candidate_sha256": candidate_digest, "receipt_sha256": _sha(operation_receipt),
            "receipt_chain_sha256": prev, "candidate_promotion_performed": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--dataset-directory", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--partition-seed", required=True)
    parser.add_argument("--rights-review-id", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--operation-receipt", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=0.005)
    parser.add_argument("--max-optimizer-steps", type=int, default=25000)
    parser.add_argument("--max-training-seconds", type=int, default=1200)
    args = parser.parse_args(argv)
    try:
        result = run_book_candidate(source=args.source, source_sha256=args.source_sha256,
            intake=args.intake, coverage=args.coverage,
            dataset_directory=args.dataset_directory, prefix=args.prefix,
            partition_seed=args.partition_seed, rights_review_id=args.rights_review_id,
            checkpoint=args.checkpoint, checkpoint_sha256=args.checkpoint_sha256,
            candidate=args.candidate, report=args.report,
            operation_receipt=args.operation_receipt,
            epochs=args.epochs, learning_rate=float(args.learning_rate),
            max_optimizer_steps=args.max_optimizer_steps,
            max_training_seconds=args.max_training_seconds)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] != "rejected_evaluation_gate" else 3
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:500]}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
