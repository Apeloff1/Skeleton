"""Train a real *candidate* from the live Jeeves weights and admitted book data.

The source MUST be a separately pinned, rights-reviewed full-book intake.
The independent game-corpus loader supplies train/holdout isolation; book
segments must ALL be in TRAIN (never heldout or silently dropped). This command
then calls the existing production checkpoint optimizer. The resulting weights
are a candidate, not automatically installed in the speaking Jeeves cortex.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .book_learning_bridge import BookIntakeError, _encode, _regular, _sha
from .jeeves_game_corpus import load_approved_corpus
from .jeeves_production_game_train import ProductionCheckpointError, train


def _receipt(path: Path) -> dict[str, Any]:
    raw = _regular(path, max_bytes=1024 * 1024)
    try:
        item = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise BookIntakeError("invalid book admission receipt") from exc
    if not isinstance(item, dict) or item.get("schema_version") != (
        "skeleton.jeeves.book_admission_receipt.v1"
    ):
        raise BookIntakeError("unknown book admission schema")
    parent = dict(item)
    stated = parent.pop("digest", None)
    if _sha(_encode(parent)) != stated:
        raise BookIntakeError("book admission receipt was changed after review")
    if (item.get("source_coverage_complete") is not True
            or item.get("training_started") is not False
            or item.get("production_weights_modified") is not False):
        raise BookIntakeError("book admission claims a fabricated training effect")
    return item


def _all_rows(receipt: dict[str, Any], root: Path) -> dict[str, dict[str, Any]]:
    shards = receipt.get("shards")
    if not isinstance(shards, list) or not shards:
        raise BookIntakeError("book admission has no content shards")
    prev: str | None = None
    compiled: dict[str, dict[str, Any]] = {}
    for i, item in enumerate(shards):
        if (not isinstance(item, dict) or set(item) != {
            "index", "file", "rows", "sha256", "previous_receipt", "receipt_sha256"
        } or item["index"] != i or item["previous_receipt"] != prev):
            raise BookIntakeError("book shard receipt ancestry mismatch")
        stem = item["file"]
        if (not isinstance(stem, str) or not stem.startswith("jeeves-books-")
                or not stem.endswith(".jsonl") or Path(stem).name != stem):
            raise BookIntakeError("invalid shard basename")
        raw = _regular(root / stem, max_bytes=64 * 1024 * 1024)
        if _sha(raw) != item["sha256"]:
            raise BookIntakeError("book shard differs from human-reviewed source")
        rows = raw.splitlines()
        if item["rows"] != len(rows):
            raise BookIntakeError("shard has lost reviewed examples")
        for line in rows:
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError) as exc:
                raise BookIntakeError("invalid book training segment") from exc
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise BookIntakeError("book segment identity missing")
            if row["id"] in compiled:
                raise BookIntakeError("duplicate book segment")
            compiled[row["id"]] = row
        without = dict(item)
        prev = without.pop("receipt_sha256")
        if _sha(_encode(without)) != prev:
            raise BookIntakeError("admission segment chain changed")
    if len(compiled) != receipt.get("training_examples"):
        raise BookIntakeError("admission total does not match source segments")
    return compiled


def train_admitted_books(
    *, admission_receipt: Path, data_directory: Path,
    dataset_manifest: Path, expected_checkpoint_sha256: str,
    candidate: Path, report: Path, epochs: int = 1,
    max_training_seconds: int = 1200,
    max_optimizer_steps: int = 25000,
) -> dict[str, Any]:
    """Use only rows proven present in an independent, rights-reviewed TRAIN split.

    A single candidate uses the original production trainer's size/word limits.
    Larger libraries need multiple independently validated checkpoint rounds:
    NEVER silently skip chapters or append unreviewed work to a model.
    """
    if (not isinstance(expected_checkpoint_sha256, str)
            or len(expected_checkpoint_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_checkpoint_sha256)):
        raise BookIntakeError("independently pinned live checkpoint SHA256 required")
    admitted = _receipt(Path(admission_receipt))
    data_directory = Path(data_directory)
    if data_directory.is_symlink() or not data_directory.is_dir():
        raise BookIntakeError("admission source directory must exist")
    segments = _all_rows(admitted, data_directory)
    # The canonical loader independently checks rights, contamination, project
    # split membership, holdout family balance and byte-bound manifest digests.
    _train, _heldout, _proof = load_approved_corpus(Path(dataset_manifest))
    raw_manifest = _regular(Path(dataset_manifest), max_bytes=64 * 1024)
    meta = json.loads(raw_manifest)
    root = Path(dataset_manifest).resolve().parent
    train_bytes = _regular(root / meta["train_file"], max_bytes=64 * 1024 * 1024)
    heldout_bytes = _regular(root / meta["heldout_file"], max_bytes=64 * 1024 * 1024)
    train_rows = [json.loads(line) for line in train_bytes.splitlines()]
    heldout_rows = [json.loads(line) for line in heldout_bytes.splitlines()]
    indexed = {row["id"]: row for row in train_rows}
    if len(indexed) != len(train_rows):
        raise BookIntakeError("duplicated segment IDs in final training split")
    heldout_ids = {row["id"] for row in heldout_rows}
    if set(segments).intersection(heldout_ids):
        raise BookIntakeError("admitted book was diverted to a held-out split")
    if not set(segments) <= set(indexed):
        raise BookIntakeError("not all admitted book content enters this candidate round")
    for key, admitted_row in segments.items():
        train_row = indexed[key]
        for field in ("id", "source_project_id", "family", "prompt", "answer", "rights"):
            source = admitted_row[field]
            selected = train_row.get(field)
            if field in ("prompt", "answer"):
                source = source.strip()
            if source != selected:
                raise BookIntakeError("book content or rights differ from training partition")
    # Evidence establishes *admission* and optimizer inputs, not effective
    # knowledge transfer. Separate held-out generation must verify usefulness.
    trained = train(
        None, expected=expected_checkpoint_sha256,
        candidate=Path(candidate), report=Path(report),
        epochs=epochs, lr=0.005, min_coverage=0.80,
        max_domain_regression=0.0,
        dataset_manifest=Path(dataset_manifest),
        max_training_seconds=max_training_seconds,
        max_optimizer_steps=max_optimizer_steps,
    )
    return {
        "schema_version": "skeleton.jeeves.book_weight_candidate_run.v1",
        "admission_receipt_sha256": admitted["digest"],
        "admitted_book_count": admitted["source_books"],
        "all_book_segments_admitted": len(segments),
        "candidate_trainer_report": trained,
        "production_model_auto_promoted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission-receipt", required=True, type=Path)
    parser.add_argument("--data-directory", required=True, type=Path)
    parser.add_argument("--dataset-manifest", required=True, type=Path)
    parser.add_argument("--expected-checkpoint-sha256", required=True)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--max-training-seconds", type=int, default=1200)
    parser.add_argument("--max-optimizer-steps", type=int, default=25000)
    args = parser.parse_args(argv)
    result = train_admitted_books(
        admission_receipt=args.admission_receipt, data_directory=args.data_directory,
        dataset_manifest=args.dataset_manifest,
        expected_checkpoint_sha256=args.expected_checkpoint_sha256,
        candidate=args.candidate, report=args.report, epochs=args.epochs,
        max_training_seconds=args.max_training_seconds,
        max_optimizer_steps=args.max_optimizer_steps,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
