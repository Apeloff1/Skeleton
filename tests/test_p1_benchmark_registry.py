from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_p1_benchmark_registry import (
    BenchmarkRegistryValidationError,
    compare_registries,
    validate_repository,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("machine/p1_benchmark_registry.json")


def _payload() -> dict:
    return json.loads((ROOT / REGISTRY).read_text(encoding="utf-8"))


def _write(root: Path, payload: dict, name: str) -> Path:
    path = Path(name)
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _benchmark() -> dict:
    return {
        "benchmark_id": "qa-core",
        "version": "v1",
        "datasets": [
            {
                "dataset_id": "qa",
                "version": "v1",
                "source_ref": "dataset://qa/v1",
                "source_digest": "1" * 64,
                "content_digest": "2" * 64,
                "license_id": "internal-eval",
                "parent_dataset_digest": None,
            }
        ],
        "splits": [
            {
                "split_id": "test",
                "role": "test",
                "dataset_id": "qa",
                "dataset_version": "v1",
                "content_digest": "3" * 64,
                "sample_count": 500,
                "contamination_status": "clean",
                "contamination_evidence": [
                    {
                        "source": "scan://qa/v1/test",
                        "digest": "4" * 64,
                        "category": "contamination_scan",
                    }
                ],
                "contamination_sources": [],
            }
        ],
        "metrics": [
            {
                "metric_id": "exact-match",
                "direction": "maximize",
                "minimum_samples": 100,
                "evaluator_id": "independent-evaluator",
                "evaluator_digest": "5" * 64,
                "independent": True,
            }
        ],
        "primary_metric_id": "exact-match",
        "environment": {
            "environment_id": "env-ci",
            "environment_digest": "6" * 64,
            "runner_digest": "7" * 64,
            "dependency_lock_digest": "8" * 64,
            "source_date_epoch": 1800000000,
        },
        "experiment_manifest_digest": "9" * 64,
        "reproducibility_bundle_digest": "a" * 64,
        "tags": ["core"],
    }


def test_repository_registry_is_valid_and_non_authoritative() -> None:
    report = validate_repository(ROOT)
    assert report["valid"] is True
    assert report["task_id"] == "P1-LEARN-02"
    assert report["accountability_ref"] == "ACC-P1-LEARN-02"
    assert report["production_authority"] is False
    assert len(report["registry_digest"]) == 64


def test_clean_benchmark_entry_is_accepted(tmp_path: Path) -> None:
    payload = _payload()
    payload["benchmarks"] = [_benchmark()]
    path = _write(tmp_path, payload, "machine/p1_benchmark_registry.json")

    report = validate_repository(tmp_path, registry_path=path)
    assert report["benchmark_count"] == 1


@pytest.mark.parametrize(
    "status",
    ("unknown", "suspected", "confirmed"),
)
def test_nonclean_evaluation_contamination_is_rejected(
    tmp_path: Path,
    status: str,
) -> None:
    payload = _payload()
    benchmark = _benchmark()
    split = benchmark["splits"][0]
    split["contamination_status"] = status
    if status in {"suspected", "confirmed"}:
        split["contamination_sources"] = ["training-corpus"]
    payload["benchmarks"] = [benchmark]
    path = _write(tmp_path, payload, "machine/p1_benchmark_registry.json")

    with pytest.raises(
        BenchmarkRegistryValidationError,
        match="evaluation contamination must be clean",
    ):
        validate_repository(tmp_path, registry_path=path)


def test_missing_contamination_evidence_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _payload()
    benchmark = _benchmark()
    benchmark["splits"][0]["contamination_evidence"] = []
    payload["benchmarks"] = [benchmark]
    path = _write(tmp_path, payload, "machine/p1_benchmark_registry.json")

    with pytest.raises(Exception, match="contamination_evidence"):
        validate_repository(tmp_path, registry_path=path)


def test_registry_policy_drift_fails_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["policy"]["unknown_contamination_blocks"] = False
    path = _write(tmp_path, payload, "machine/p1_benchmark_registry.json")

    with pytest.raises(
        BenchmarkRegistryValidationError,
        match="benchmark policy drift",
    ):
        validate_repository(tmp_path, registry_path=path)


def test_existing_benchmark_identity_cannot_mutate(
    tmp_path: Path,
) -> None:
    baseline = _payload()
    baseline["benchmarks"] = [_benchmark()]
    candidate = json.loads(json.dumps(baseline))
    candidate["benchmarks"][0]["metrics"][0]["minimum_samples"] = 101
    baseline_path = _write(
        tmp_path,
        baseline,
        "machine/baseline.json",
    )
    candidate_path = _write(
        tmp_path,
        candidate,
        "machine/candidate.json",
    )

    report = compare_registries(
        tmp_path,
        baseline_path=baseline_path,
        candidate_path=candidate_path,
    )
    assert report["accepted"] is False
    assert report["mutated"] == [["qa-core", "v1"]]


def test_additive_benchmark_version_is_allowed(tmp_path: Path) -> None:
    baseline = _payload()
    baseline["benchmarks"] = [_benchmark()]
    candidate = json.loads(json.dumps(baseline))
    next_version = _benchmark()
    next_version["version"] = "v2"
    next_version["datasets"][0]["version"] = "v2"
    next_version["datasets"][0]["content_digest"] = "b" * 64
    next_version["datasets"][0]["source_ref"] = "dataset://qa/v2"
    next_version["splits"][0]["dataset_version"] = "v2"
    next_version["splits"][0]["content_digest"] = "c" * 64
    next_version["splits"][0]["contamination_evidence"][0][
        "digest"
    ] = "d" * 64
    candidate["benchmarks"].append(next_version)
    baseline_path = _write(
        tmp_path,
        baseline,
        "machine/baseline.json",
    )
    candidate_path = _write(
        tmp_path,
        candidate,
        "machine/candidate.json",
    )

    report = compare_registries(
        tmp_path,
        baseline_path=baseline_path,
        candidate_path=candidate_path,
    )
    assert report["accepted"] is True
    assert report["added"] == [["qa-core", "v2"]]


def test_unknown_fields_fail_closed(tmp_path: Path) -> None:
    payload = _payload()
    benchmark = _benchmark()
    benchmark["silent_override"] = True
    payload["benchmarks"] = [benchmark]
    path = _write(tmp_path, payload, "machine/p1_benchmark_registry.json")

    with pytest.raises(
        BenchmarkRegistryValidationError,
        match="unknown fields",
    ):
        validate_repository(tmp_path, registry_path=path)
