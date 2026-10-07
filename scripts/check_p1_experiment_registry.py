#!/usr/bin/env python3
"""Validate the governed P1 experiment registry and immutable lineage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.eval.experiment_registry import (
    ExperimentBudget,
    ExperimentEligibility,
    ExperimentManifest,
    ExperimentMetric,
    ExperimentRegistry,
    ExperimentRegistryError,
    MetricDirection,
    TrafficMode,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path("machine/p1_experiment_registry.json")
EXPECTED_TASK = "P1-LEARN-01"
EXPECTED_ACCOUNTABILITY = "ACC-P1-LEARN-01"
EXPECTED_POLICY = {
    "production_authority": False,
    "external_side_effects": "forbid",
    "allowed_traffic_modes": ["offline", "shadow"],
    "max_shadow_traffic_fraction": 0.1,
    "allowed_data_classes": ["public", "internal"],
    "non_public_shadow_requires_tenant_scope": True,
    "independent_metrics_required": True,
    "exact_source_commit_required": True,
    "immutable_experiment_identity": True,
    "additive_lineage_only": True,
}


class ExperimentRegistryValidationError(RuntimeError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperimentRegistryValidationError(f"cannot read {path}") from exc


def _strict_keys(row: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(row) - allowed
    if unknown:
        raise ExperimentRegistryValidationError(
            f"{label}: unknown fields {sorted(unknown)}"
        )


def _manifest(row: object, *, policy: dict[str, Any]) -> ExperimentManifest:
    if not isinstance(row, dict):
        raise ExperimentRegistryValidationError("experiment entries must be objects")
    _strict_keys(
        row,
        {
            "experiment_id",
            "hypothesis",
            "owner",
            "source_commit",
            "environment_id",
            "candidate_ref",
            "eligibility",
            "budget",
            "metrics",
            "parent_experiment_id",
            "tags",
        },
        str(row.get("experiment_id", "?")),
    )
    eligibility_row = row.get("eligibility")
    budget_row = row.get("budget")
    metrics_row = row.get("metrics")
    if not isinstance(eligibility_row, dict):
        raise ExperimentRegistryValidationError("eligibility must be an object")
    if not isinstance(budget_row, dict):
        raise ExperimentRegistryValidationError("budget must be an object")
    if not isinstance(metrics_row, list) or not metrics_row:
        raise ExperimentRegistryValidationError("metrics must be a non-empty list")
    _strict_keys(
        eligibility_row,
        {
            "traffic_mode",
            "max_traffic_fraction",
            "allowed_data_classes",
            "tenant_ids",
            "external_side_effects_allowed",
        },
        "eligibility",
    )
    _strict_keys(
        budget_row,
        {"max_samples", "max_tokens", "max_cost_units", "max_wall_time_s"},
        "budget",
    )
    metrics: list[ExperimentMetric] = []
    for metric_row in metrics_row:
        if not isinstance(metric_row, dict):
            raise ExperimentRegistryValidationError("metric entries must be objects")
        _strict_keys(
            metric_row,
            {"metric_id", "direction", "minimum_samples", "source", "independent"},
            "metric",
        )
        metrics.append(
            ExperimentMetric(
                metric_id=metric_row["metric_id"],
                direction=MetricDirection(metric_row["direction"]),
                minimum_samples=metric_row["minimum_samples"],
                source=metric_row["source"],
                independent=metric_row.get("independent", True),
            )
        )

    eligibility = ExperimentEligibility(
        traffic_mode=TrafficMode(eligibility_row["traffic_mode"]),
        max_traffic_fraction=eligibility_row["max_traffic_fraction"],
        allowed_data_classes=tuple(eligibility_row["allowed_data_classes"]),
        tenant_ids=tuple(eligibility_row.get("tenant_ids", [])),
        external_side_effects_allowed=eligibility_row.get(
            "external_side_effects_allowed",
            False,
        ),
    )
    if (
        eligibility.traffic_mode is TrafficMode.SHADOW
        and eligibility.max_traffic_fraction > policy["max_shadow_traffic_fraction"]
    ):
        raise ExperimentRegistryValidationError(
            "shadow traffic fraction exceeds machine policy"
        )
    if not set(eligibility.allowed_data_classes).issubset(
        policy["allowed_data_classes"]
    ):
        raise ExperimentRegistryValidationError(
            "experiment data class exceeds machine policy"
        )
    if policy["independent_metrics_required"] and any(
        metric.independent is not True for metric in metrics
    ):
        raise ExperimentRegistryValidationError(
            "machine policy requires independent metrics"
        )

    return ExperimentManifest(
        experiment_id=row["experiment_id"],
        hypothesis=row["hypothesis"],
        owner=row["owner"],
        source_commit=row["source_commit"],
        environment_id=row["environment_id"],
        candidate_ref=row["candidate_ref"],
        eligibility=eligibility,
        budget=ExperimentBudget(
            max_samples=budget_row["max_samples"],
            max_tokens=budget_row["max_tokens"],
            max_cost_units=budget_row["max_cost_units"],
            max_wall_time_s=budget_row["max_wall_time_s"],
        ),
        metrics=tuple(metrics),
        parent_experiment_id=row.get("parent_experiment_id"),
        tags=tuple(row.get("tags", [])),
    )


def load_registry(
    root: Path = ROOT,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> tuple[dict[str, Any], ExperimentRegistry]:
    payload = _load(root / registry_path)
    if not isinstance(payload, dict):
        raise ExperimentRegistryValidationError("registry root must be an object")
    _strict_keys(
        payload,
        {
            "schema_version",
            "registry_version",
            "task_id",
            "accountability_ref",
            "authority",
            "policy",
            "experiments",
        },
        "registry",
    )
    if payload.get("schema_version") != 1:
        raise ExperimentRegistryValidationError("schema_version must equal 1")
    if payload.get("task_id") != EXPECTED_TASK:
        raise ExperimentRegistryValidationError("task_id drift")
    if payload.get("accountability_ref") != EXPECTED_ACCOUNTABILITY:
        raise ExperimentRegistryValidationError("accountability_ref drift")
    if payload.get("authority") != str(REGISTRY_PATH):
        raise ExperimentRegistryValidationError("authority path drift")
    policy = payload.get("policy")
    if policy != EXPECTED_POLICY:
        raise ExperimentRegistryValidationError("experiment policy drift")
    rows = payload.get("experiments")
    if not isinstance(rows, list):
        raise ExperimentRegistryValidationError("experiments must be a list")
    manifests = tuple(_manifest(row, policy=policy) for row in rows)
    return payload, ExperimentRegistry(manifests)


def validate_repository(
    root: Path = ROOT,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    payload, registry = load_registry(root, registry_path=registry_path)
    return {
        "schema_version": 1,
        "registry_version": payload.get("registry_version"),
        "task_id": EXPECTED_TASK,
        "accountability_ref": EXPECTED_ACCOUNTABILITY,
        "experiment_count": len(registry.manifests),
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
    before = {item.experiment_id: item for item in baseline.manifests}
    after = {item.experiment_id: item for item in candidate.manifests}

    removed = sorted(set(before) - set(after))
    mutated = sorted(
        experiment_id
        for experiment_id in set(before) & set(after)
        if before[experiment_id].manifest_digest
        != after[experiment_id].manifest_digest
    )
    added = sorted(set(after) - set(before))
    accepted = not removed and not mutated
    return {
        "accepted": accepted,
        "baseline_digest": baseline.registry_digest,
        "candidate_digest": candidate.registry_digest,
        "removed": removed,
        "mutated": mutated,
        "added": added,
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
            "registry": validate_repository(ROOT, registry_path=args.registry)
        }
        if args.baseline is not None:
            comparison = compare_registries(
                ROOT,
                baseline_path=args.baseline,
                candidate_path=args.registry,
            )
            payload["lineage"] = comparison
            if comparison["accepted"] is not True:
                raise ExperimentRegistryValidationError(
                    "candidate registry rewrites immutable experiment history"
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
        ExperimentRegistryValidationError,
        ExperimentRegistryError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"P1 experiment registry: rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
