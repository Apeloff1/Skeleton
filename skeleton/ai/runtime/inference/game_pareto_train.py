"""Bounded, auditable game-domain 80/20 fine-tuning for Skeleton's local RNN.

This does not train GGUF/transformer models, use remote providers, or promote
weights. The output is a separate candidate, never a replacement checkpoint.
A lower byte-level held-out loss is NOT proof of better game-design reasoning.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .game_pareto_curriculum import CURRICULUM, CURRICULUM_VERSION

SCHEMA = "skeleton.game_pareto_training.v2"
MAX_RETENTION_BYTES = 256 * 1024


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _priority(row: tuple[int, int, int, int, str]) -> float:
    impact, reuse, effort, risk, _ = row
    return impact * reuse / (1 + effort + risk)


def plan() -> tuple[dict[str, object], tuple[str, ...], tuple[str, ...]]:
    """Deterministic, exactly 80/20 exposure scheduler for curated examples.

    Twenty percent of *distinct* examples receive 80% of scheduled exposures.
    The interleaved tail preserves coverage across all eight competency families.
    The category shares allocate exposure count, not guaranteed learning outcomes.
    """
    families = tuple(CURRICULUM)
    if len(families) != 8:
        raise ValueError("Pareto curriculum requires eight competency families")
    if sum(CURRICULUM[family]["share"] for family in families) != 100:
        raise ValueError("category exposure shares must total exactly 100")

    core: dict[str, str] = {}
    tails: dict[str, list[str]] = {}
    all_training: list[str] = []
    heldout: list[str] = []
    for family in families:
        group = CURRICULUM[family]
        rows = group["train"]
        heldout_group = group["holdout"]
        if len(rows) != 5 or len(heldout_group) != 2:
            raise ValueError("each family requires five training and two held-out cases")
        if not all(
            isinstance(row, tuple)
            and len(row) == 5
            and all(type(score) is int and 1 <= score <= 5 for score in row[:4])
            and isinstance(row[4], str)
            and bool(row[4].strip())
            for row in rows
        ):
            raise ValueError("invalid Pareto case or priority score")
        if any(not isinstance(case, str) or not case.strip() for case in heldout_group):
            raise ValueError("held-out cases must be non-empty strings")
        ranked = sorted(rows, key=lambda row: (-_priority(row), row[4]))
        core[family] = ranked[0][4]
        tails[family] = [row[4] for row in ranked[1:]]
        all_training.extend(row[4] for row in rows)
        heldout.extend(heldout_group)

    if len(set(all_training)) != len(all_training):
        raise ValueError("duplicate authored training example")
    if len(set(heldout)) != len(heldout):
        raise ValueError("duplicate held-out example")
    if set(all_training).intersection(heldout):
        raise ValueError("train/evaluation data contamination")

    tail_order = [tails[family][index] for index in range(4) for family in families]
    exposures = 5 * len(tail_order)
    targets: dict[str, int] = {}
    for family in families:
        product = exposures * CURRICULUM[family]["share"]
        if product % 100:
            raise ValueError("fractional category exposure allocation")
        targets[family] = product // 100
    quotas = {family: targets[family] - len(tails[family]) for family in families}
    if min(quotas.values()) < 0:
        raise ValueError("category share too small for tail coverage")
    total_core = sum(quotas.values())
    if total_core != exposures * 4 // 5:
        raise ValueError("80/20 allocation violated")

    # Smooth weighted round-robin, with a deterministic family tie-break.
    credit = dict.fromkeys(families, 0)
    remaining = quotas.copy()
    core_order: list[str] = []
    for _ in range(total_core):
        for family in families:
            credit[family] += quotas[family]
        chosen = max(
            (family for family in families if remaining[family]),
            key=lambda family: (credit[family], -families.index(family)),
        )
        core_order.append(core[chosen])
        remaining[chosen] -= 1
        credit[chosen] -= total_core

    documents: list[str] = []
    for index, tail_case in enumerate(tail_order):
        documents.extend(core_order[index * 4 : (index + 1) * 4])
        documents.append(tail_case)

    counts = Counter(documents)
    family_counts = {family: sum(counts[row[4]] for row in CURRICULUM[family]["train"]) for family in families}
    if len(documents) != exposures or family_counts != targets:
        raise ValueError("scheduled training exposures differ from category budgets")
    if sum(counts[case] for case in core.values()) != total_core:
        raise ValueError("scheduled Pareto core budget violated")
    report: dict[str, object] = {
        "schema_version": SCHEMA,
        "curriculum_version": CURRICULUM_VERSION,
        "source": "original_synthetic_in_repo",
        "curriculum_digest": _digest(CURRICULUM),
        "train_schedule_digest": _digest(documents),
        "heldout_digest": _digest(heldout),
        "distinct_training_cases": len(all_training),
        "distinct_core_cases": len(core),
        "heldout_cases": len(heldout),
        "scheduled_exposures": exposures,
        "core_exposures": total_core,
        "tail_exposures": len(tail_order),
        "family_exposures": family_counts,
        "family_shares_percent": {family: CURRICULUM[family]["share"] for family in families},
        "epochs_are_full_schedule_passes": True,
        "training_is_not_production_promotion": True,
    }
    return report, tuple(documents), tuple(heldout)


def _retention_documents(paths: list[Path]) -> tuple[str, ...]:
    """Optional external, operator-provided text used only for retention evaluation."""
    results: list[str] = []
    known: set[Path] = set()
    total = 0
    for path in paths:
        if path.is_symlink():
            raise ValueError("retention corpus symlink forbidden")
        location = path.expanduser().resolve(strict=True)
        if location in known or not location.is_file():
            raise ValueError("duplicate or non-regular retention corpus")
        known.add(location)
        size = location.stat().st_size
        total += size
        if size < 1 or total > MAX_RETENTION_BYTES:
            raise ValueError("retention corpus exceeds 256 KiB combined limit")
        text = location.read_text(encoding="utf-8", errors="strict").strip()
        if not text:
            raise ValueError("retention corpus may not be empty")
        results.append(text)
    return tuple(results)


def _valid_number(value: object, label: str, *, upper: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= upper:
        raise ValueError(f"{label} must be finite and in [0, {upper}]")
    return float(value)


def _losses(model: Any) -> dict[str, float]:
    return {
        family: model.loss(tuple(CURRICULUM[family]["holdout"]))
        for family in CURRICULUM
    }


def _publish_new_candidate(model: Any, destination: Path, writer: Any) -> Any:
    """Stage, validate, then exclusively hard-link without overwriting a race winner.

    The underlying local artifact writer uses os.replace(), suitable for an
    operator-chosen staging pathname but not an absent-only candidate target.
    """
    with tempfile.TemporaryDirectory(prefix=".game-pareto-", dir=str(destination.parent)) as stage:
        staged = Path(stage) / "candidate.json"
        receipt = writer(model, staged)
        os.link(staged, destination)  # atomic no-clobber even if another writer wins
        return receipt


def train(args: argparse.Namespace) -> dict[str, object]:
    """Return evidence on success or rejection; rejects never publish a candidate."""
    from .artifact import load_local_model_artifact, write_local_model_artifact
    from .neural import NeuralLMConfig, NumpyRecurrentLM

    if args.output is None:
        raise ValueError("--output is required for training")
    if args.bootstrap == (args.base_artifact is not None):
        raise ValueError("choose exactly one of --base-artifact or --bootstrap")
    if type(args.epochs) is not int or not 1 <= args.epochs <= 10:
        raise ValueError("epochs must be between 1 and 10")
    learning_rate = _valid_number(args.learning_rate, "learning rate", upper=0.1)
    if learning_rate <= 0:
        raise ValueError("learning rate must be positive")
    family_limit = _valid_number(args.max_family_regression, "family regression", upper=1)
    retention_limit = _valid_number(args.max_retention_regression, "retention regression", upper=1)
    gain = _valid_number(args.min_relative_gain, "required gain", upper=1)

    destination: Path = args.output.expanduser()
    if destination.is_symlink() or destination.exists():
        raise ValueError("refusing to replace an existing candidate")
    if not destination.parent.is_dir():
        raise ValueError("candidate directory does not exist")
    if args.base_artifact is not None:
        source = args.base_artifact.expanduser()
        if source.is_symlink() or source.resolve() == destination.resolve():
            raise ValueError("parent model cannot be a symlink or candidate destination")
        loaded = load_local_model_artifact(source)
        model = loaded.model
        if not isinstance(model, NumpyRecurrentLM):
            raise ValueError("only NumPy recurrent checkpoints are supported; GGUF and transformers are untouched")
        source_mode = "existing_checkpoint"
    else:
        if type(args.seed) is not int or type(args.hidden_size) is not int:
            raise ValueError("bootstrap seed and hidden size must be integers")
        model = NumpyRecurrentLM(
            model_id=args.model_id, config=NeuralLMConfig(hidden_size=args.hidden_size, seed=args.seed)
        )
        source_mode = "new_scratch_baseline_not_existing_model"

    summary, documents, heldout = plan()
    retention = _retention_documents(args.retention_corpus)
    retention_before = model.loss(retention) if retention else None
    parent_digest = model.model_digest
    family_before = _losses(model)
    heldout_before = model.loss(heldout)

    trained = model.train(
        documents,
        epochs=args.epochs,
        learning_rate=learning_rate,
        gradient_clip=1.0,
    )
    heldout_after = model.loss(heldout)
    family_after = _losses(model)
    retention_after = model.loss(retention) if retention else None

    report: dict[str, object] = {
        **summary,
        "status": "rejected",
        "artifact_written": False,
        "candidate_promoted": False,
        "source_mode": source_mode,
        "parent_model_digest": parent_digest,
        "candidate_model_digest": model.model_digest,
        "model_id": model.model_id,
        "epochs": args.epochs,
        "learning_rate": learning_rate,
        "train_loss_before": trained.initial_loss,
        "train_loss_after": trained.final_loss,
        "heldout_loss_before": heldout_before,
        "heldout_loss_after": heldout_after,
        "family_heldout_before": family_before,
        "family_heldout_after": family_after,
        "retention_loss_before": retention_before,
        "retention_loss_after": retention_after,
        "retention_documents": len(retention),
        "training_receipt_digest": trained.digest,
        "loss_is_byte_level_not_gameplay_quality": True,
    }

    reasons: list[str] = []
    if heldout_after >= heldout_before * (1 - gain):
        reasons.append("no_required_heldout_gain")
    for family in CURRICULUM:
        if family_after[family] > family_before[family] * (1 + family_limit):
            reasons.append("domain_regression:" + family)
    if retention:
        if retention_after is None or retention_before is None:
            raise ValueError("retention evidence absent")
        if retention_after > retention_before * (1 + retention_limit):
            reasons.append("general_retention_regression")
    if model.model_digest == parent_digest:
        reasons.append("unchanged_weights")
    if reasons:
        report["status"] = "rejected_evaluation_gate"
        report["rejection_reasons"] = reasons
        return report

    artifact = _publish_new_candidate(model, destination, write_local_model_artifact)
    report.update({
        "status": "candidate_trained",
        "artifact_written": True,
        "candidate_path": str(destination.resolve()),
        "artifact_sha256": artifact.artifact_sha256,
        "artifact_bytes": artifact.artifact_bytes,
        "artifact_reference": artifact.reference,
    })
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", help="Inspect original curriculum; no model access")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--base-artifact", type=Path, help="existing NumPy RNN artifact")
    source.add_argument("--bootstrap", action="store_true", help="explicitly initialize a new scratch baseline")
    parser.add_argument("--output", type=Path, help="new candidate artifact path; never overwrites")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=0.005)
    parser.add_argument("--max-family-regression", type=float, default=0.10)
    parser.add_argument("--max-retention-regression", type=float, default=0.05)
    parser.add_argument("--min-relative-gain", type=float, default=0.0)
    parser.add_argument("--retention-corpus", type=Path, action="append", default=[])
    parser.add_argument("--model-id", default="game-pareto-scratch-baseline")
    parser.add_argument("--hidden-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        outcome = plan()[0] if args.plan else train(args)
        print(json.dumps(outcome, sort_keys=True, ensure_ascii=False, allow_nan=False))
        return 0 if outcome.get("status", "curriculum_ready") != "rejected_evaluation_gate" else 3
    except (OSError, ValueError, TypeError, RuntimeError, UnicodeError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)[:500]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
