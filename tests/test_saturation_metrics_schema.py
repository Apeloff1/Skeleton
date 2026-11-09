from __future__ import annotations

import json
from pathlib import Path

from scripts.check_saturation_metrics_schema import (
    SCHEMA_VERSION,
    main,
    validate_saturation_metrics,
)


def _doc(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "window": "2026-09-18T09:00Z",
        "runnable_depth": 4,
        "blocked_depth": 2,
        "active_leases": 3,
        "capacity": 8,
        "queue_pressure": 12,
        "pr_pressure": 7,
        "completions": 5,
        "rejections": 1,
        "evidence_refs": ["issue:#969"],
    }
    payload.update(overrides)
    return payload


def test_valid_document_has_no_violations() -> None:
    assert validate_saturation_metrics(_doc()) == []


def test_negative_count_fails_closed() -> None:
    errors = validate_saturation_metrics(_doc(blocked_depth=-1))
    assert any("saturation-metrics unknown count" in item for item in errors)


def test_bool_is_not_an_integer() -> None:
    errors = validate_saturation_metrics(_doc(completions=True))
    assert any("saturation-metrics unknown count" in item for item in errors)


def test_unknown_fields_fail_closed() -> None:
    errors = validate_saturation_metrics(_doc(severity="high"))
    assert any("saturation-metrics unknown field" in item for item in errors)


def test_leases_above_capacity_fail_closed() -> None:
    errors = validate_saturation_metrics(_doc(active_leases=9, capacity=8))
    assert any("saturation-metrics unknown lease_overflow" in item for item in errors)


def test_missing_evidence_fails_closed() -> None:
    errors = validate_saturation_metrics(_doc(evidence_refs=[]))
    assert any("saturation-metrics missing_value evidence_refs" in item for item in errors)


def test_wrong_schema_version_fails_closed() -> None:
    errors = validate_saturation_metrics(_doc(schema_version=99))
    assert any("saturation-metrics unknown schema_version" in item for item in errors)


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "Saturation-metrics schema v1 accepted" in capsys.readouterr().out
