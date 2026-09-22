from __future__ import annotations

import json

from scripts import check_ai_engineering_pass as checker


def test_engineering_pass_is_complete() -> None:
    assert checker.validate() == []
    data = json.loads(checker.ENGINEERING.read_text(encoding="utf-8"))
    assert len(data["engineering_dimensions"]) == 15
    assert [p["id"] for p in data["work_package_profiles"]] == checker.EXPECTED_WPS


def test_every_work_package_has_failure_recovery_and_budget_obligations() -> None:
    data = json.loads(checker.ENGINEERING.read_text(encoding="utf-8"))
    for profile in data["work_package_profiles"]:
        assert profile["principal_failure_modes"], profile["id"]
        assert profile["recovery_requirements"], profile["id"]
        assert profile["nfr_budget_classes"], profile["id"]
        assert profile["evidence_modes"], profile["id"]


def test_engineering_pass_preserves_breadth_freeze() -> None:
    data = json.loads(checker.ENGINEERING.read_text(encoding="utf-8"))
    assert data["breadth_policy"] == {
        "adds_top_level_volumes": False,
        "last_top_level_volume": 420,
    }


def test_budget_policy_requires_measurement_context() -> None:
    data = json.loads(checker.ENGINEERING.read_text(encoding="utf-8"))
    required = set(data["budget_binding_policy"]["required_fields"])
    assert {
        "metric", "threshold", "unit", "workload", "environment",
        "measurement_method", "owner", "exception_or_waiver_ref",
    }.issubset(required)


def test_required_dimensions_are_unique_and_canonical() -> None:
    data = json.loads(checker.ENGINEERING.read_text(encoding="utf-8"))
    ids = [d["id"] for d in data["engineering_dimensions"]]
    assert len(ids) == len(set(ids))
    assert set(ids) == checker.REQUIRED_DIMENSIONS
