from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_p1_experiment_registry.py"
REGISTRY = ROOT / "machine/p1_experiment_registry.json"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_p1_experiment_registry",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo(tmp_path: Path) -> Path:
    target = tmp_path / "machine/p1_experiment_registry.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REGISTRY, target)
    return tmp_path


def _mutate(path: Path, fn) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fn(payload)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _experiment(experiment_id: str = "exp.test.v1") -> dict:
    return {
        "experiment_id": experiment_id,
        "hypothesis": "A bounded candidate improves independent quality.",
        "owner": "p1-learning",
        "source_commit": "a" * 40,
        "environment_id": "staging.eval",
        "candidate_ref": "candidate:test.v1",
        "eligibility": {
            "traffic_mode": "shadow",
            "max_traffic_fraction": 0.05,
            "allowed_data_classes": ["public"],
            "tenant_ids": [],
            "external_side_effects_allowed": False,
        },
        "budget": {
            "max_samples": 100,
            "max_tokens": 100000,
            "max_cost_units": 5.0,
            "max_wall_time_s": 600.0,
        },
        "metrics": [
            {
                "metric_id": "quality.acceptance",
                "direction": "maximize",
                "minimum_samples": 25,
                "source": "independent-eval",
                "independent": True,
            }
        ],
        "parent_experiment_id": None,
        "tags": ["quality"],
    }


def test_canonical_machine_registry_starts_empty_and_valid() -> None:
    module = _module()
    summary = module.validate_repository(ROOT)

    assert summary["valid"] is True
    assert summary["experiment_count"] == 0
    assert summary["production_authority"] is False
    assert len(summary["registry_digest"]) == 64


def test_policy_weakening_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = root / "machine/p1_experiment_registry.json"

    def mutate(payload: dict) -> None:
        payload["policy"]["external_side_effects"] = "allow"

    _mutate(registry, mutate)
    module = _module()
    try:
        module.validate_repository(root)
    except module.ExperimentRegistryValidationError as exc:
        assert "policy drift" in str(exc)
    else:
        raise AssertionError("weakened policy unexpectedly validated")


def test_shadow_fraction_above_policy_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = root / "machine/p1_experiment_registry.json"

    def mutate(payload: dict) -> None:
        row = _experiment()
        row["eligibility"]["max_traffic_fraction"] = 0.2
        payload["experiments"] = [row]

    _mutate(registry, mutate)
    module = _module()
    try:
        module.validate_repository(root)
    except module.ExperimentRegistryValidationError as exc:
        assert "exceeds machine policy" in str(exc)
    else:
        raise AssertionError("oversized shadow experiment unexpectedly validated")


def test_non_public_shadow_without_tenant_scope_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = root / "machine/p1_experiment_registry.json"

    def mutate(payload: dict) -> None:
        row = _experiment()
        row["eligibility"]["allowed_data_classes"] = ["internal"]
        row["eligibility"]["tenant_ids"] = []
        payload["experiments"] = [row]

    _mutate(registry, mutate)
    module = _module()
    try:
        module.validate_repository(root)
    except Exception as exc:
        assert "tenant scope" in str(exc)
    else:
        raise AssertionError("unscoped internal shadow experiment unexpectedly validated")


def test_existing_experiment_identity_is_immutable(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    candidate = root / "machine/p1_experiment_registry.json"
    baseline = root / "baseline.json"

    payload = json.loads(candidate.read_text(encoding="utf-8"))
    payload["experiments"] = [_experiment()]
    baseline.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    changed = json.loads(json.dumps(payload))
    changed["experiments"][0]["hypothesis"] = "Changed hypothesis under same ID."
    candidate.write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")

    module = _module()
    result = module.compare_registries(
        root,
        baseline_path=Path("baseline.json"),
    )

    assert result["accepted"] is False
    assert result["mutated"] == ["exp.test.v1"]


def test_existing_experiment_cannot_be_deleted(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    candidate = root / "machine/p1_experiment_registry.json"
    baseline = root / "baseline.json"

    payload = json.loads(candidate.read_text(encoding="utf-8"))
    payload["experiments"] = [_experiment()]
    baseline.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    module = _module()
    result = module.compare_registries(
        root,
        baseline_path=Path("baseline.json"),
    )

    assert result["accepted"] is False
    assert result["removed"] == ["exp.test.v1"]


def test_new_experiment_is_additive(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    candidate = root / "machine/p1_experiment_registry.json"
    baseline = root / "baseline.json"
    shutil.copyfile(candidate, baseline)

    payload = json.loads(candidate.read_text(encoding="utf-8"))
    payload["experiments"] = [_experiment()]
    candidate.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    module = _module()
    result = module.compare_registries(
        root,
        baseline_path=Path("baseline.json"),
    )

    assert result["accepted"] is True
    assert result["added"] == ["exp.test.v1"]


def test_unknown_registry_fields_fail_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    registry = root / "machine/p1_experiment_registry.json"

    def mutate(payload: dict) -> None:
        payload["production_override"] = True

    _mutate(registry, mutate)
    module = _module()
    try:
        module.validate_repository(root)
    except module.ExperimentRegistryValidationError as exc:
        assert "unknown fields" in str(exc)
    else:
        raise AssertionError("unknown authority field unexpectedly validated")
