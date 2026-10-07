#!/usr/bin/env python3
"""Validate P1 benchmark identity, contamination policy, and immutable lineage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.contracts.canonical import EvidenceRef
from skeleton.eval.benchmark_registry import (
    BenchmarkDataset,
    BenchmarkEnvironment,
    BenchmarkManifest,
    BenchmarkMetric,
    BenchmarkRegistry,
    BenchmarkRegistryError,
    BenchmarkSplit,
    BenchmarkSplitRole,
    ContaminationStatus,
)
from skeleton.eval.experiment_registry import MetricDirection


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path("machine/p1_benchmark_registry.json")
EXPECTED_TASK = "P1-LEARN-02"
EXPECTED_ACCOUNTABILITY = "ACC-P1-LEARN-02"
EXPECTED_POLICY = {
    "production_authority": False,
    "clean_status_required_for_promotion": True,
    "contamination_evidence_required": True,
    "unknown_contamination_blocks": True,
    "independent_evaluator_required": True,
    "exact_environment_binding": True,
    "reproducibility_bundle_required": True,
    "offline_experiment_required": True,
    "immutable_benchmark_identity": True,
    "additive_lineage_only": True,
    "allowed_split_roles": ["train", "validation", "test", "holdout"],
    "evaluation_split_roles": ["test", "holdout"],
}


class BenchmarkRegistryValidationError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkRegistryValidationError(f"cannot read {path}") from exc


def _strict_keys(row: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(row) - allowed
    if unknown:
        raise BenchmarkRegistryValidationError(
            f"{label}: unknown fields {sorted(unknown)}"
        )


def _evidence(row: object) -> EvidenceRef:
    if not isinstance(row, dict):
        raise BenchmarkRegistryValidationError(
            "contamination evidence entries must be objects"
        )
    _strict_keys(row, {"source", "digest", "category"}, "evidence")
    return EvidenceRef(
        source=row["source"],
        digest=row["digest"],
        category=row["category"],
    )


def _manifest(row: object, *, policy: dict[str, Any]) -> BenchmarkManifest:
    if not isinstance(row, dict):
        raise BenchmarkRegistryValidationError(
            "benchmark entries must be objects"
        )
    _strict_keys(
        row,
        {
            "benchmark_id",
            "version",
            "datasets",
            "splits",
            "metrics",
            "primary_metric_id",
            "environment",
            "experiment_manifest_digest",
            "reproducibility_bundle_digest",
            "tags",
        },
        str(row.get("benchmark_id", "?")),
    )
    datasets_row = row.get("datasets")
    splits_row = row.get("splits")
    metrics_row = row.get("metrics")
    environment_row = row.get("environment")
    if not isinstance(datasets_row, list) or not datasets_row:
        raise BenchmarkRegistryValidationError(
            "datasets must be a non-empty list"
        )
    if not isinstance(splits_row, list) or not splits_row:
        raise BenchmarkRegistryValidationError(
            "splits must be a non-empty list"
        )
    if not isinstance(metrics_row, list) or not metrics_row:
        raise BenchmarkRegistryValidationError(
            "metrics must be a non-empty list"
        )
    if not isinstance(environment_row, dict):
        raise BenchmarkRegistryValidationError(
            "environment must be an object"
        )

    datasets: list[BenchmarkDataset] = []
    for item in datasets_row:
        if not isinstance(item, dict):
            raise BenchmarkRegistryValidationError(
                "dataset entries must be objects"
            )
        _strict_keys(
            item,
            {
                "dataset_id",
                "version",
                "source_ref",
                "source_digest",
                "content_digest",
                "license_id",
                "parent_dataset_digest",
            },
            "dataset",
        )
        datasets.append(
            BenchmarkDataset(
                dataset_id=item["dataset_id"],
                version=item["version"],
                source_ref=item["source_ref"],
                source_digest=item["source_digest"],
                content_digest=item["content_digest"],
                license_id=item["license_id"],
                parent_dataset_digest=item.get("parent_dataset_digest"),
            )
        )

    dataset_by_key = {
        (item["dataset_id"], item["version"]): dataset
        for item, dataset in zip(datasets_row, datasets, strict=True)
    }
    splits: list[BenchmarkSplit] = []
    for item in splits_row:
        if not isinstance(item, dict):
            raise BenchmarkRegistryValidationError(
                "split entries must be objects"
            )
        _strict_keys(
            item,
            {
                "split_id",
                "role",
                "dataset_id",
                "dataset_version",
                "content_digest",
                "sample_count",
                "contamination_status",
                "contamination_evidence",
                "contamination_sources",
            },
            "split",
        )
        dataset = dataset_by_key.get(
            (item["dataset_id"], item["dataset_version"])
        )
        if dataset is None:
            raise BenchmarkRegistryValidationError(
                f"{item.get('split_id', '?')}: unknown dataset id/version"
            )
        evidence_rows = item.get("contamination_evidence")
        if not isinstance(evidence_rows, list):
            raise BenchmarkRegistryValidationError(
                "contamination_evidence must be a list"
            )
        split = BenchmarkSplit(
            split_id=item["split_id"],
            role=BenchmarkSplitRole(item["role"]),
            dataset_digest=dataset.digest,
            content_digest=item["content_digest"],
            sample_count=item["sample_count"],
            contamination_status=ContaminationStatus(
                item["contamination_status"]
            ),
            contamination_evidence=tuple(
                _evidence(value) for value in evidence_rows
            ),
            contamination_sources=tuple(
                item.get("contamination_sources", [])
            ),
        )
        if split.role.value not in policy["allowed_split_roles"]:
            raise BenchmarkRegistryValidationError(
                f"{split.split_id}: split role is not allowed"
            )
        if (
            split.role.value in policy["evaluation_split_roles"]
            and policy["clean_status_required_for_promotion"]
            and split.contamination_status is not ContaminationStatus.CLEAN
        ):
            raise BenchmarkRegistryValidationError(
                f"{split.split_id}: evaluation contamination must be clean"
            )
        if (
            policy["unknown_contamination_blocks"]
            and split.contamination_status is ContaminationStatus.UNKNOWN
        ):
            raise BenchmarkRegistryValidationError(
                f"{split.split_id}: unknown contamination is blocking"
            )
        if (
            policy["contamination_evidence_required"]
            and not split.contamination_evidence
        ):
            raise BenchmarkRegistryValidationError(
                f"{split.split_id}: contamination evidence is required"
            )
        splits.append(split)

    metrics: list[BenchmarkMetric] = []
    for item in metrics_row:
        if not isinstance(item, dict):
            raise BenchmarkRegistryValidationError(
                "metric entries must be objects"
            )
        _strict_keys(
            item,
            {
                "metric_id",
                "direction",
                "minimum_samples",
                "evaluator_id",
                "evaluator_digest",
                "independent",
            },
            "metric",
        )
        metric = BenchmarkMetric(
            metric_id=item["metric_id"],
            direction=MetricDirection(item["direction"]),
            minimum_samples=item["minimum_samples"],
            evaluator_id=item["evaluator_id"],
            evaluator_digest=item["evaluator_digest"],
            independent=item.get("independent", True),
        )
        if (
            policy["independent_evaluator_required"]
            and metric.independent is not True
        ):
            raise BenchmarkRegistryValidationError(
                f"{metric.metric_id}: evaluator must be independent"
            )
        metrics.append(metric)

    _strict_keys(
        environment_row,
        {
            "environment_id",
            "environment_digest",
            "runner_digest",
            "dependency_lock_digest",
            "source_date_epoch",
        },
        "environment",
    )
    return BenchmarkManifest(
        benchmark_id=row["benchmark_id"],
        version=row["version"],
        datasets=tuple(datasets),
        splits=tuple(splits),
        metrics=tuple(metrics),
        primary_metric_id=row["primary_metric_id"],
        environment=BenchmarkEnvironment(
            environment_id=environment_row["environment_id"],
            environment_digest=environment_row["environment_digest"],
            runner_digest=environment_row["runner_digest"],
            dependency_lock_digest=environment_row[
                "dependency_lock_digest"
            ],
            source_date_epoch=environment_row["source_date_epoch"],
        ),
        experiment_manifest_digest=row["experiment_manifest_digest"],
        reproducibility_bundle_digest=row[
            "reproducibility_bundle_digest"
        ],
        tags=tuple(row.get("tags", [])),
    )


def load_registry(
    root: Path = ROOT,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> tuple[dict[str, Any], BenchmarkRegistry]:
    payload = _load(root / registry_path)
    if not isinstance(payload, dict):
        raise BenchmarkRegistryValidationError(
            "registry root must be an object"
        )
    _strict_keys(
        payload,
        {
            "schema_version",
            "registry_version",
            "task_id",
            "accountability_ref",
            "authority",
            "policy",
            "benchmarks",
        },
        "registry",
    )
    if payload.get("schema_version") != 1:
        raise BenchmarkRegistryValidationError(
            "schema_version must equal 1"
        )
    if payload.get("task_id") != EXPECTED_TASK:
        raise BenchmarkRegistryValidationError("task_id drift")
    if payload.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise BenchmarkRegistryValidationError("accountability_ref drift")
    if payload.get("authority") != str(REGISTRY_PATH):
        raise BenchmarkRegistryValidationError("authority path drift")
    policy = payload.get("policy")
    if policy != EXPECTED_POLICY:
        raise BenchmarkRegistryValidationError(
            "benchmark policy drift"
        )
    rows = payload.get("benchmarks")
    if not isinstance(rows, list):
        raise BenchmarkRegistryValidationError(
            "benchmarks must be a list"
        )
    manifests = tuple(_manifest(row, policy=policy) for row in rows)
    return payload, BenchmarkRegistry(manifests)


def validate_repository(
    root: Path = ROOT,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    payload, registry = load_registry(
        root,
        registry_path=registry_path,
    )
    return {
        "schema_version": 1,
        "registry_version": payload.get("registry_version"),
        "task_id": EXPECTED_TASK,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "benchmark_count": len(registry.manifests),
        "registry_digest": registry.registry_digest,
        "production_authority": False,
        "valid": True,
    }


def compare_registries(
    root: Path,
    *,
    baseline_path: Path,
    candidate_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    _, baseline = load_registry(root, registry_path=baseline_path)
    _, candidate = load_registry(root, registry_path=candidate_path)
    before = {
        (item.benchmark_id, item.version): item
        for item in baseline.manifests
    }
    after = {
        (item.benchmark_id, item.version): item
        for item in candidate.manifests
    }
    removed = sorted(set(before) - set(after))
    mutated = sorted(
        key
        for key in set(before) & set(after)
        if before[key].manifest_digest != after[key].manifest_digest
    )
    added = sorted(set(after) - set(before))
    accepted = not removed and not mutated
    return {
        "accepted": accepted,
        "baseline_digest": baseline.registry_digest,
        "candidate_digest": candidate.registry_digest,
        "removed": [list(key) for key in removed],
        "mutated": [list(key) for key in mutated],
        "added": [list(key) for key in added],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload: dict[str, Any] = {
            "registry": validate_repository(
                ROOT,
                registry_path=args.registry,
            )
        }
        if args.baseline is not None:
            comparison = compare_registries(
                ROOT,
                baseline_path=args.baseline,
                candidate_path=args.registry,
            )
            payload["lineage"] = comparison
            if comparison["accepted"] is not True:
                raise BenchmarkRegistryValidationError(
                    "candidate registry rewrites immutable benchmark history"
                )
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if args.print_summary:
            print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (
        BenchmarkRegistryValidationError,
        BenchmarkRegistryError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"P1 benchmark registry: rejected: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
