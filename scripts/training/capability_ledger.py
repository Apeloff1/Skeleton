"""Offline model proficiency history without retaining validation examples.

Only hashed identity and per-mode aggregate counts enter SQLite. Never
write raw model predictions, truth labels, prompt text, or new train rows.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from skeleton.ai.training.capability_ledger import (
    CapabilityLedgerError, OfflineCapabilityLedger, make_capability_receipt,
)
from skeleton.ai.training.offline_foundations import validate_curriculum


DATASET = (
    Path(__file__).resolve().parents[2]
    / "skeleton/ai/training/datasets/offline_foundations_v1"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Store aggregate-only held-out validation trends, never training data."
    )
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--model-tag", required=True)
    operations = parser.add_mutually_exclusive_group(required=True)
    operations.add_argument("--record-predictions", type=Path,
                            help="score validation predictions and store only aggregate counts")
    operations.add_argument("--status", action="store_true",
                            help="show latest aggregate change without reading prediction text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        source = validate_curriculum(args.dataset)
        ledger = args.ledger.expanduser().absolute()
        if ledger.is_relative_to(args.dataset.resolve()):
            raise CapabilityLedgerError("ledger database cannot be inside the source dataset")
        receipt = (
            make_capability_receipt(
                args.dataset, args.record_predictions, model_tag=args.model_tag,
            ) if args.record_predictions else None
        )
        with OfflineCapabilityLedger(ledger) as history:
            identity = history.record(receipt) if receipt else None
            result = history.compare(
                args.model_tag,
                source_manifest_sha256=source["manifest_sha256"],
            )
        result.update({
            "source_dataset_id": source["dataset_id"],
            "source_manifest_sha256": source["manifest_sha256"],
            "added_receipt_digest": identity,
            "raw_predictions_stored": False,
            "training_corpus_mutated": False,
            "model_production_promotion_approved": False,
        })
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, TypeError, OSError, RuntimeError, KeyError) as exc:
        print(
            "offline capability history rejected: "
            + type(exc).__name__ + ": " + str(exc), file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
