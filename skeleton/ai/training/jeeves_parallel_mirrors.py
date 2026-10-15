"""Two isolated Jeeves production-derived candidate models train concurrently.

Only an explicitly attested, persisted serving checkpoint is accepted. Two
separate worker processes clone it, use distinct optimizer schedules, and keep
candidate-only outputs. A result is neither independent judgement nor promotion.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import ctypes
import json
from multiprocessing import get_context
import os
from pathlib import Path
import shutil
import sys
from typing import Any

from .jeeves_multidomain import CATALOG, digest_with_mirrors, load_multidomain_corpus, validate_catalog
from .jeeves_production_game_train import ProductionCheckpointError, _production_source
from .jeeves_production_readiness import _load_attestation, _save_new_private

def available_memory_bytes() -> int:
    """Read host available RAM without assuming an unbundled third-party package."""
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_uint32),
                ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]
        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ProductionCheckpointError("Windows RAM admission probe failed")
        return int(status.ullAvailPhys)
    try:
        return int(os.sysconf("SC_AVPHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError) as exc:
        raise ProductionCheckpointError("platform cannot prove free RAM for parallel training") from exc


SCHEMA = "skeleton.jeeves.parallel_training_receipt.v1"
ARMS = (("constructive", 0.005, 1), ("adversarial", 0.003, 2))


def _source(attestation_path: Path) -> tuple[Path, str]:
    attestation = _load_attestation(attestation_path, maximum_age_seconds=900)
    configured = os.environ.get("SKELETON_OWN", "").strip()
    if not configured:
        raise ProductionCheckpointError("SKELETON_OWN is not configured")
    source = Path(configured).expanduser()
    if source.resolve() != Path(str(attestation.get("checkpoint_path", ""))).resolve():
        raise ProductionCheckpointError("attestation does not bind the configured serving checkpoint")
    digest = attestation.get("checkpoint_sha256")
    if not isinstance(digest, str):
        raise ProductionCheckpointError("missing serving checkpoint digest")
    pinned, _blob, observed = _production_source(source, digest)
    if observed != digest:
        raise ProductionCheckpointError("serving checkpoint digest mismatch")
    return pinned, observed


def _candidate_worker(
    name: str, lr: float, epochs: int, source: Path, parent_sha: str,
    manifest: Path, candidate: Path, report: Path,
    expand_vocabulary: bool, capacity_growth: str, max_added_parameters: int,
    adaptive_replay: bool, replay_examples: int, max_scored_examples: int,
    max_optimizer_steps: int, max_training_seconds: int,
) -> dict[str, Any]:
    """A spawned child does real candidate SGD through the existing optimizer."""
    from .jeeves_production_game_train import train
    result = train(
        source, expected=parent_sha, candidate=candidate, report=report,
        epochs=epochs, lr=lr, min_coverage=.80, max_domain_regression=0.0,
        expand_vocabulary=expand_vocabulary, dataset_manifest=manifest,
        training_view=name, capacity_growth=capacity_growth,
        max_added_parameters=max_added_parameters,
        adaptive_replay=adaptive_replay, replay_examples=replay_examples,
        max_scored_examples=max_scored_examples,
        max_optimizer_steps=max_optimizer_steps,
        max_training_seconds=max_training_seconds)
    return {
        "arm": name, "training_view": name,
        "learning_rate": lr, "epochs": epochs,
        "status": result["status"],
        "real_optimizer_updates": result["observed_optimizer_updates"],
        "capacity_growth_profile": capacity_growth,
        "capacity_growth": result.get("capacity_growth"),
        "candidate_trainable_parameters": result.get("candidate_trainable_parameters"),
        "new_trainable_parameters": result.get("trainable_parameters_added_by_growth", 0),
        "capability_replay": result.get("capability_replay"),
        "candidate_sha256": result.get("candidate_sha256"),
        "candidate_file": candidate.name if candidate.is_file() else None,
        "report_file": report.name,
        "report_sha256": sha256(report.read_bytes()).hexdigest(),
        "independent_human_review_complete": False,
        "production_promoted": False,
    }


def run_parallel_candidates(
    *, catalog_path: Path, manifest_path: Path, attestation_path: Path,
    output_directory: Path, receipt_path: Path,
    max_optimizer_steps: int = 10000, max_training_seconds: int = 1200,
    expand_vocabulary: bool = False,
    constructive_capacity: str = "none", adversarial_capacity: str = "none",
    max_added_parameters: int = 500000,
    adaptive_replay: bool = False, replay_examples: int = 64,
    max_scored_examples: int = 128,
) -> dict[str, Any]:
    if type(max_optimizer_steps) is not int or not 1 <= max_optimizer_steps <= 25000:
        raise ProductionCheckpointError("optimizer step budget outside 1..25000")
    if type(max_training_seconds) is not int or not 1 <= max_training_seconds <= 3600:
        raise ProductionCheckpointError("optimizer wall-clock budget outside 1..3600")
    if type(expand_vocabulary) is not bool:
        raise ProductionCheckpointError("vocabulary expansion must be explicitly boolean")
    from .jeeves_capacity_growth import PROFILE_FACTORS
    if (constructive_capacity not in PROFILE_FACTORS or
            adversarial_capacity not in PROFILE_FACTORS):
        raise ProductionCheckpointError("mirror growth profiles must be supported")
    if type(max_added_parameters) is not int or not 1 <= max_added_parameters <= 2000000:
        raise ProductionCheckpointError("mirror FFN new-parameter budget outside 1..2,000,000")
    if type(adaptive_replay) is not bool or (
            adaptive_replay and (type(replay_examples) is not int or
            type(max_scored_examples) is not int or
            not 6 <= replay_examples <= max_scored_examples <= 256)):
        raise ProductionCheckpointError("mirror hard-example replay budget invalid")
    if (os.cpu_count() or 1) < 2:
        raise ProductionCheckpointError("two training arms require at least two CPU cores")
    if output_directory.is_symlink() or not output_directory.is_dir():
        raise ProductionCheckpointError("existing regular candidate output directory required")
    if receipt_path.exists() or receipt_path.is_symlink() or receipt_path.parent != output_directory:
        raise ProductionCheckpointError("receipt must be a new file under candidate output directory")
    catalog = validate_catalog(catalog_path)
    _train, _heldout, corpus = load_multidomain_corpus(manifest_path)
    # Fail BEFORE starting either real optimizer if either perspective lacks
    # rights-reviewed data. Both use the same untouched held-out split.
    view_receipts: dict[str, dict[str, Any]] = {}
    for name, _lr, _epochs in ARMS:
        _view_train, _view_heldout, view_receipts[name] = load_multidomain_corpus(
            manifest_path, training_view=name)
    constructive = set(view_receipts["constructive"]["active_modules"])
    adversarial = set(view_receipts["adversarial"]["active_modules"])
    if not constructive or not adversarial or constructive == adversarial:
        raise ProductionCheckpointError("parallel optimizer mirrors require distinct reviewed specialist modules")
    source, parent_sha = _source(attestation_path)
    if shutil.disk_usage(output_directory).free < 1024 ** 3:
        raise ProductionCheckpointError("at least 1 GiB free disk is required")
    if available_memory_bytes() < max(2 * 1024 ** 3, 16 * source.stat().st_size):
        raise ProductionCheckpointError("insufficient available RAM for two isolated model copies")
    names: dict[str, tuple[Path, Path]] = {}
    for name, _lr, _epochs in ARMS:
        stem = f"jeeves-{parent_sha[:16]}-{name}"
        candidate = output_directory / (stem + "-candidate.json")
        report = output_directory / (stem + "-report.json")
        if candidate.exists() or candidate.is_symlink() or report.exists() or report.is_symlink():
            raise ProductionCheckpointError("refusing candidate or report overwrite")
        names[name] = candidate, report
    if any(receipt_path == path for files in names.values() for path in files):
        raise ProductionCheckpointError("receipt cannot alias candidate or report")
    results: list[dict[str, Any]] = []
    capacity_by_arm = {"constructive": constructive_capacity,
                       "adversarial": adversarial_capacity}
    # Spawned independent CPU processes, not Python threads sharing a mutable LM.
    with ProcessPoolExecutor(max_workers=2, mp_context=get_context("spawn")) as pool:
        jobs = [
            (name, pool.submit(_candidate_worker, name, lr, epochs,
                               source, parent_sha, manifest_path, *names[name],
                               expand_vocabulary, capacity_by_arm[name],
                               max_added_parameters, adaptive_replay,
                               replay_examples, max_scored_examples,
                               max_optimizer_steps, max_training_seconds))
            for name, lr, epochs in ARMS
        ]
        # Await both even on failure; do not leave unobserved live optimizers.
        for name, future in jobs:
            try:
                results.append(future.result())
            except (OSError, RuntimeError, ValueError, TypeError, OverflowError) as exc:
                results.append({
                    "arm": name, "status": "blocked", "error": str(exc)[:300],
                    "real_optimizer_updates": None,
                    "independent_human_review_complete": False,
                    "production_promoted": False})
    mirrors = digest_with_mirrors(manifest_path, workers=4)
    if sha256(source.read_bytes()).hexdigest() != parent_sha:
        raise ProductionCheckpointError("serving parent modified during mirror candidate training")
    completed = all(
        item.get("status") == "candidate_trained_needs_game_design_review"
        for item in results
    )
    report = {
        "schema_version": SCHEMA,
        "status": "two_candidates_pending_independent_review" if completed else "mirror_candidate_training_blocked",
        "parent_checkpoint_sha256": parent_sha,
        "dataset_manifest_sha256": corpus["manifest_sha256"],
        "catalog_sha256": catalog["catalog_sha256"],
        "registered_modules": catalog["modules"],
        "active_modules": len(corpus["active_modules"]),
        "candidate_arms": results,
        "capacity_growth_profiles": capacity_by_arm,
        "new_parameter_admission_per_arm": max_added_parameters,
        "adaptive_capability_replay": adaptive_replay,
        "capability_replay_examples": replay_examples if adaptive_replay else 0,
        "real_model_parameter_growth_ran": any(
            item.get("new_trainable_parameters", 0) > 0
            and item.get("real_optimizer_updates", 0) > 0 for item in results
            if item.get("real_optimizer_updates") is not None),
        "optimizer_views": {
            name: {"train_examples": receipt["train_examples"],
                   "training_view": receipt["training_view"]}
            for name, receipt in sorted(view_receipts.items())
        },
        "separate_training_processes": 2,
        "data_mirror_evidence": mirrors["mirrors"],
        "independent_quality_review_complete": False,
        "serving_weights_modified": False,
        "automatic_promotion": False,
        "allowed_to_promote": False,
    }
    _save_new_private(receipt_path, json.dumps(report, sort_keys=True, indent=2,
                     ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--dataset-manifest", type=Path)
    parser.add_argument("--attestation", type=Path)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--train-mirrors", action="store_true")
    parser.add_argument("--expand-vocabulary", action="store_true")
    parser.add_argument("--constructive-capacity",
                        choices=("none", "micro", "balanced", "large", "xlarge"),
                        default="none")
    parser.add_argument("--adversarial-capacity",
                        choices=("none", "micro", "balanced", "large", "xlarge"),
                        default="none")
    parser.add_argument("--max-added-parameters", type=int, default=500000)
    parser.add_argument("--adaptive-replay", action="store_true",
                        help="each mirror scores only its own approved TRAIN specialist documents")
    parser.add_argument("--replay-examples", type=int, default=64)
    parser.add_argument("--max-scored-examples", type=int, default=128)
    parser.add_argument("--max-optimizer-steps", type=int, default=10000)
    parser.add_argument("--max-training-seconds", type=int, default=1200)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        if not args.train_mirrors:
            data = (digest_with_mirrors(args.dataset_manifest, workers=args.workers)
                    if args.dataset_manifest is not None else validate_catalog(args.catalog))
            print(json.dumps(data, sort_keys=True, indent=2))
            return 0
        if any(value is None for value in (args.dataset_manifest, args.attestation,
                                          args.output_directory, args.receipt)):
            raise ProductionCheckpointError(
                "candidate mirrors need approved dataset, runtime attestation, output directory and receipt")
        result = run_parallel_candidates(
            catalog_path=args.catalog, manifest_path=args.dataset_manifest,
            attestation_path=args.attestation, output_directory=args.output_directory,
            receipt_path=args.receipt,
            max_optimizer_steps=args.max_optimizer_steps,
            max_training_seconds=args.max_training_seconds,
            expand_vocabulary=args.expand_vocabulary,
            constructive_capacity=args.constructive_capacity,
            adversarial_capacity=args.adversarial_capacity,
            max_added_parameters=args.max_added_parameters,
            adaptive_replay=args.adaptive_replay,
            replay_examples=args.replay_examples,
            max_scored_examples=args.max_scored_examples)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result["status"] == "two_candidates_pending_independent_review" else 3
    except (OSError, RuntimeError, ValueError, TypeError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)[:400],
                          "production_promoted": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
