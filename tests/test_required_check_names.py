"""Fail-closed regressions for the check-name stability audit (#960 S007)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_required_check_names import (
    CLASSES,
    CONFLICT_DOMAIN,
    DOCUMENT_FIELDS,
    SCHEMA_VERSION,
    TASK_ID,
    classify_document,
    classify_required_check,
    main,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_required_check_names.py"


def _observed(*names: str) -> list[dict[str, object]]:
    return [{"name": name, "source": "check"} for name in names]


def _doc(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "conflict_domain": CONFLICT_DOMAIN,
        "required_checks": ["Merge Readiness", "Gitleaks"],
        "observed_checks": _observed("Merge Readiness", "Gitleaks"),
        "renames": [],
    }
    payload.update(overrides)
    return payload


def test_task_identity_and_closed_classes() -> None:
    assert TASK_ID == "reserve-S007-check-name-stability"
    assert CONFLICT_DOMAIN == "ci.readonly.check_name_stability"
    assert SCHEMA_VERSION == 1
    assert CLASSES == ("stable", "renamed", "missing", "unknown")
    assert DOCUMENT_FIELDS == {
        "schema_version",
        "task_id",
        "conflict_domain",
        "required_checks",
        "observed_checks",
        "renames",
    }
    source = SCRIPT.read_text(encoding="utf-8")
    assert "TASK_KEY" not in source
    assert 'TASK_ID = "reserve-S007-check-name-stability"' in source
    assert "reserve-S001" not in source
    assert "reserve-S002" not in source


def test_stable_required_checks_have_no_violations() -> None:
    rows, errors = classify_document(_doc())
    assert errors == []
    assert [row["class"] for row in rows] == ["stable", "stable"]
    assert [row["observed_as"] for row in rows] == ["Merge Readiness", "Gitleaks"]


def test_renamed_check_fails_closed_with_new_name() -> None:
    rows, errors = classify_document(
        _doc(
            required_checks=["Merge Readiness"],
            observed_checks=_observed("Merge Gate"),
            renames=[{"from": "Merge Readiness", "to": "Merge Gate", "kind": "check"}],
        )
    )
    assert rows[0]["class"] == "renamed"
    assert rows[0]["observed_as"] == "Merge Gate"
    assert any("check-name-stability renamed check" in item for item in errors)


def test_missing_check_fails_closed() -> None:
    rows, errors = classify_document(
        _doc(
            required_checks=["Merge Readiness", "Secret Scan"],
            observed_checks=_observed("Merge Readiness"),
        )
    )
    assert [row["class"] for row in rows] == ["stable", "missing"]
    assert any("check-name-stability missing check" in item for item in errors)


def test_rename_without_observed_target_is_unknown() -> None:
    rows, errors = classify_document(
        _doc(
            required_checks=["Merge Readiness"],
            observed_checks=_observed("Backend Tests"),
            renames=[{"from": "Merge Readiness", "to": "Merge Gate"}],
        )
    )
    assert rows[0]["class"] == "unknown"
    assert any("check-name-stability unknown unclassified" in item for item in errors)


def test_stable_and_rename_together_is_unknown() -> None:
    rows, errors = classify_document(
        _doc(
            required_checks=["Merge Readiness"],
            observed_checks=_observed("Merge Readiness"),
            renames=[{"from": "Merge Readiness", "to": "Merge Gate"}],
        )
    )
    assert rows[0]["class"] == "unknown"
    assert any("check-name-stability unknown unclassified" in item for item in errors)


def test_blank_and_non_string_required_names_are_unknown() -> None:
    rows, errors = classify_document(
        _doc(required_checks=["", "  ", 12, None])
    )
    assert all(row["class"] == "unknown" for row in rows)
    assert any("check-name-stability unknown unclassified" in item for item in errors)


def test_duplicate_required_names_fail_closed() -> None:
    rows, errors = classify_document(
        _doc(required_checks=["Merge Readiness", "Merge Readiness"])
    )
    assert rows[1]["class"] == "unknown"
    assert any("check-name-stability unknown duplicate_required" in item for item in errors)


def test_unknown_fields_fail_closed() -> None:
    rows, errors = classify_document(_doc(severity="high"))
    assert all(row["class"] == "unknown" for row in rows)
    assert any("check-name-stability unknown field" in item for item in errors)


def test_wrong_schema_and_ids_fail_closed() -> None:
    version = classify_document(_doc(schema_version=2))[1]
    assert any("check-name-stability unknown schema_version" in item for item in version)
    task = classify_document(_doc(task_id="reserve-S001-current-pr-blocker-map"))[1]
    assert any("check-name-stability unknown task_id" in item for item in task)
    domain = classify_document(_doc(conflict_domain="ci.readonly.blocker_map"))[1]
    assert any("check-name-stability unknown conflict_domain" in item for item in domain)


def test_non_object_root_fails_closed() -> None:
    rows, errors = classify_document(["not", "an", "object"])
    assert rows == []
    assert errors == ["check-name-stability unknown root_type: document must be an object"]


def test_empty_required_checks_fail_closed() -> None:
    _, errors = classify_document(_doc(required_checks=[]))
    assert any("check-name-stability unknown required_checks_empty" in item for item in errors)


def test_unknown_observed_and_rename_shapes_fail_closed() -> None:
    observed_type = classify_document(_doc(observed_checks={"name": "x"}))[1]
    assert any("check-name-stability unknown observed_checks_type" in item for item in observed_type)
    observed_row = classify_document(_doc(observed_checks=["Merge Readiness"]))[1]
    assert any("check-name-stability unknown observed_type" in item for item in observed_row)
    extra = classify_document(
        _doc(observed_checks=[{"name": "Merge Readiness", "owner": "night"}])
    )[1]
    assert any("check-name-stability unknown field" in item for item in extra)
    source = classify_document(
        _doc(observed_checks=[{"name": "Merge Readiness", "source": "actions"}])
    )[1]
    assert any("check-name-stability unknown source" in item for item in source)
    rename_type = classify_document(_doc(renames={"from": "a", "to": "b"}))[1]
    assert any("check-name-stability unknown renames_type" in item for item in rename_type)
    identity = classify_document(
        _doc(renames=[{"from": "Merge Readiness", "to": "Merge Readiness"}])
    )[1]
    assert any("check-name-stability unknown rename_identity" in item for item in identity)


def test_helper_unknown_without_evidence() -> None:
    assert classify_required_check("Merge Readiness", observed_names=None, rename_map={}) == "unknown"
    assert classify_required_check("Merge Readiness", observed_names=frozenset(), rename_map=None) == "unknown"
    assert classify_required_check(None, observed_names=frozenset(), rename_map={}) == "unknown"


def test_cli_accepts_stable_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "stable.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "Check-name stability: stable=2, renamed=0, missing=0, unknown=0" in out


def test_cli_rejects_missing_check(tmp_path: Path, capsys) -> None:
    path = tmp_path / "missing.json"
    path.write_text(
        json.dumps(_doc(required_checks=["Merge Readiness"], observed_checks=_observed("Gitleaks"))),
        encoding="utf-8",
    )
    assert main([str(path)]) == 1
    err = capsys.readouterr().err
    assert "Check-name stability failed:" in err
    assert "check-name-stability missing check" in err


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "check-name-stability unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_not_wired_into_quality_gates() -> None:
    quality_gates = (REPO_ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "check_required_check_names.py" not in quality_gates
    assert "test_required_check_names.py" not in quality_gates
