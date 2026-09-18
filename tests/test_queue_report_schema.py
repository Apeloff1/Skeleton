from __future__ import annotations

import json
from pathlib import Path

from scripts.check_queue_report_schema import (
    COUNT_FIELDS,
    DOCUMENT_FIELDS,
    SCHEMA_VERSION,
    main,
    validate_queue_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _doc(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "window": "2026-09-18T00:00:00Z/2026-09-18T12:00:00Z",
        "depth": 4,
        "age_seconds": 90,
        "cancellations": 1,
        "reruns": 2,
        "blockers": 0,
        "avoided_fanout": 3,
        "evidence_refs": ["ops.queue_report:shift-969-s010"],
    }
    payload.update(overrides)
    return payload


def test_schema_contract_is_queue_trends_not_morning_categories() -> None:
    assert SCHEMA_VERSION == 1
    assert DOCUMENT_FIELDS == {
        "schema_version",
        "window",
        "depth",
        "age_seconds",
        "cancellations",
        "reruns",
        "blockers",
        "avoided_fanout",
        "evidence_refs",
    }
    assert COUNT_FIELDS == (
        "depth",
        "cancellations",
        "reruns",
        "blockers",
        "avoided_fanout",
    )
    source = (REPO_ROOT / "scripts" / "check_queue_report_schema.py").read_text(encoding="utf-8")
    for category in ("accepted", "rejected", "deferred", "flaky", "unlocked"):
        assert category not in source


def test_valid_document_has_no_violations() -> None:
    assert validate_queue_report(_doc()) == []
    assert validate_queue_report(
        _doc(
            depth=0,
            age_seconds=0,
            cancellations=0,
            reruns=0,
            blockers=0,
            avoided_fanout=0,
        )
    ) == []


def test_unknown_fields_fail_closed() -> None:
    errors = validate_queue_report(_doc(severity="high", items=[]))
    assert any("queue-report unknown field" in item for item in errors)
    assert any("severity" in item for item in errors)
    assert any("items" in item for item in errors)


def test_missing_fields_fail_closed() -> None:
    document = _doc()
    del document["blockers"]
    del document["evidence_refs"]
    errors = validate_queue_report(document)
    assert any("queue-report missing_value field" in item for item in errors)
    assert any("blockers" in item for item in errors)
    assert any("queue-report missing_value evidence_refs" in item for item in errors)


def test_wrong_types_fail_closed() -> None:
    errors = validate_queue_report(
        _doc(
            schema_version=True,
            depth="4",
            age_seconds=90.5,
            cancellations=False,
            reruns=None,
            blockers=1.0,
            avoided_fanout=True,
        )
    )
    assert any("queue-report unknown schema_version" in item for item in errors)
    type_errors = [item for item in errors if "queue-report unknown type" in item]
    assert len(type_errors) >= 6
    for field in (*COUNT_FIELDS, "age_seconds"):
        assert any(field in item for item in type_errors)


def test_negative_counts_and_age_fail_closed() -> None:
    errors = validate_queue_report(
        _doc(depth=-1, age_seconds=-2, cancellations=-3, reruns=-4, blockers=-5, avoided_fanout=-6)
    )
    negatives = [item for item in errors if "queue-report unknown negative" in item]
    assert len(negatives) == 6
    for field in (*COUNT_FIELDS, "age_seconds"):
        assert any(field in item for item in negatives)


def test_missing_and_blank_evidence_fail_closed() -> None:
    empty = validate_queue_report(_doc(evidence_refs=[]))
    assert any("queue-report missing_value evidence_refs" in item for item in empty)
    blank = validate_queue_report(_doc(evidence_refs=["", "  "]))
    assert any("queue-report unknown evidence_ref" in item for item in blank)
    not_list = validate_queue_report(_doc(evidence_refs="ops.queue_report"))
    assert any("queue-report missing_value evidence_refs" in item for item in not_list)


def test_wrong_schema_version_fails_closed() -> None:
    errors = validate_queue_report(_doc(schema_version=2))
    assert any("queue-report unknown schema_version" in item for item in errors)


def test_non_object_root_fails_closed() -> None:
    errors = validate_queue_report(["not", "an", "object"])
    assert errors == ["queue-report unknown root_type: queue report document must be an object"]


def test_blank_window_fails_closed() -> None:
    errors = validate_queue_report(_doc(window="   "))
    assert any("queue-report missing_value window" in item for item in errors)


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "queue-report.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "Queue-report schema v1 accepted" in capsys.readouterr().out


def test_cli_rejects_invalid_document(tmp_path: Path, capsys) -> None:
    path = tmp_path / "queue-report.json"
    path.write_text(json.dumps(_doc(depth=-1, extra=True)), encoding="utf-8")
    assert main([str(path)]) == 1
    stderr = capsys.readouterr().err
    assert "Queue-report schema validation failed:" in stderr
    assert "queue-report unknown negative" in stderr
    assert "queue-report unknown field" in stderr


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "queue-report unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_not_wired_into_quality_gates() -> None:
    quality_gates = (REPO_ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "check_queue_report_schema.py" not in quality_gates
    assert "test_queue_report_schema.py" not in quality_gates
