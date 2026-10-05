#!/usr/bin/env python3
"""Independent repository verifier for VOL-070 Quality Vector."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine/ai_quality_vector.json"
RUNTIME = ROOT / "skeleton/eval/quality_vector.py"
MIRROR = ROOT / "skeleton/ai/evaluation/quality_vector.py"
PACKAGE = ROOT / "skeleton/eval/__init__.py"
AI_PACKAGE = ROOT / "skeleton/ai/evaluation/__init__.py"
TESTS = ROOT / "tests/test_vol070_quality_vector.py"
WORKFLOW = ROOT / ".github/workflows/vol070-quality-vector.yml"


def _load():
    spec = importlib.util.spec_from_file_location("vol070_quality_verify", RUNTIME)
    if not spec or not spec.loader:
        raise RuntimeError("unable to load VOL-070 runtime")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate() -> list[str]:
    errors: list[str] = []
    for path in (MANIFEST, RUNTIME, MIRROR, PACKAGE, AI_PACKAGE, TESTS, WORKFLOW):
        if not path.is_file():
            errors.append(f"required VOL-070 surface missing: {path.relative_to(ROOT)}")
    if errors:
        return errors

    if RUNTIME.read_bytes() != MIRROR.read_bytes():
        errors.append("canonical and governed AI quality-vector runtime drift")
    if PACKAGE.read_bytes() != AI_PACKAGE.read_bytes():
        errors.append("canonical and governed AI evaluation package export drift")

    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        errors.append("quality-vector schema_version must be 1")
    if payload.get("volume") != "VOL-070":
        errors.append("quality-vector contract must bind VOL-070")
    if payload.get("status") != "implementation_contract":
        errors.append("quality-vector status must remain implementation_contract before promotion")

    policy = payload.get("policy")
    if not isinstance(policy, dict):
        errors.append("quality-vector policy must be an object")
    else:
        for key in ("measurement_rule", "threshold_rule", "hard_failure_rule"):
            if not isinstance(policy.get(key), str) or not policy[key].strip():
                errors.append(f"quality-vector policy missing {key}")

    dimensions = payload.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        return errors + ["quality-vector dimensions must be a non-empty list"]
    hard_count = 0
    dimension_ids: set[str] = set()
    for item in dimensions:
        if not isinstance(item, dict):
            errors.append("quality dimension must be an object")
            continue
        dimension_id = item.get("dimension_id")
        if dimension_id in dimension_ids:
            errors.append(f"duplicate machine quality dimension {dimension_id}")
        dimension_ids.add(dimension_id)
        if not item.get("evaluation_owner_id") or not item.get("evaluation_suite_id"):
            errors.append(f"{dimension_id} lacks explicit evaluation ownership")
        if item.get("hard_failure") is True:
            hard_count += 1
    if hard_count < 1:
        errors.append("quality policy must define non-compensable hard dimensions")

    module = _load()
    required_exports = {
        "QUALITY_VECTOR_SCHEMA",
        "QualityContractError",
        "QualityDimensionPolicy",
        "QualityDimensionResult",
        "QualityDirection",
        "QualityMeasurement",
        "QualityPolicy",
        "QualityVector",
    }
    if set(module.__all__) != required_exports:
        errors.append("VOL-070 public export contract drift")

    try:
        policies = []
        for item in dimensions:
            row = dict(item)
            row["direction"] = module.QualityDirection(row["direction"])
            policies.append(module.QualityDimensionPolicy(**row))
        runtime_policy = module.QualityPolicy(
            policies,
            minimum_aggregate_score=payload["minimum_aggregate_score"],
            max_future_skew_seconds=payload["max_future_skew_seconds"],
        )
        now = datetime(2026, 10, 5, tzinfo=timezone.utc)
        # Missing measurements are an intentional fail-closed smoke test.
        vector = runtime_policy.evaluate((), now=now)
        runtime_policy.verify(vector)
        hard_ids = {
            item.dimension_id for item in policies if item.hard_failure
        }
        if not hard_ids.issubset(set(vector.hard_failures)):
            errors.append("missing hard measurements did not remain non-compensable")
        if vector.promotion_eligible:
            errors.append("empty quality evidence unexpectedly became promotion eligible")
        if runtime_policy.dimension_ids != tuple(sorted(dimension_ids)):
            errors.append("runtime quality dimensions disagree with machine registry")
    except Exception as exc:
        errors.append(f"quality-vector smoke contract failed: {exc}")

    implementation = payload.get("implementation", {})
    expected = {
        "runtime": "skeleton/eval/quality_vector.py",
        "mirror": "skeleton/ai/evaluation/quality_vector.py",
        "package": "skeleton/eval/__init__.py",
        "mirror_package": "skeleton/ai/evaluation/__init__.py",
        "tests": "tests/test_vol070_quality_vector.py",
        "verifier": "scripts/check_vol070_quality_vector.py",
        "workflow": ".github/workflows/vol070-quality-vector.yml",
    }
    if implementation != expected:
        errors.append("quality-vector implementation path binding drift")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"VOL-070 ERROR: {error}")
        return 1
    print(
        "VOL-070 OK: eval-suite ownership, raw measurement/uncertainty visibility, "
        "conservative thresholds, and non-compensable hard failures verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
