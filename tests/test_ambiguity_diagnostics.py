from __future__ import annotations

import json
from pathlib import Path

from scripts.check_ambiguity_diagnostics import (
    CATEGORIES,
    CATEGORY_INDEX,
    CATEGORY_RULES,
    CONFLICT_DOMAIN,
    DISPOSITION_CLARIFY,
    DISPOSITION_FAIL,
    DOCUMENT_FIELDS,
    KIND_AMBIGUITY,
    KIND_MISSING_CONSTRAINT,
    SCHEMA_VERSION,
    TASK_KEY,
    aggregate_disposition,
    catalog_integrity_errors,
    main,
    resolve_behavior,
    validate_ambiguity_diagnostics,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _diagnostic(category: str, **overrides):
    rule = CATEGORY_INDEX[category]
    payload = {
        "category": category,
        "kind": rule.kind,
        "disposition": rule.disposition,
        "subject": f"subject:{category}",
        "evidence_refs": [f"creator.spec.ambiguity:{category}"],
    }
    payload.update(overrides)
    return payload


def _doc(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "request_id": "harbor_heist_v1",
        "diagnostics": [_diagnostic("underspecified_scope")],
    }
    payload.update(overrides)
    return payload


def test_closed_catalog_is_versioned_and_unique() -> None:
    assert SCHEMA_VERSION == 1
    assert TASK_KEY == "reserve-S035-ambiguity-diagnostics-spec"
    assert CONFLICT_DOMAIN == "creator.spec.ambiguity"
    assert DOCUMENT_FIELDS == {"schema_version", "request_id", "diagnostics"}
    assert len(CATEGORIES) == len(set(CATEGORIES)) == 15
    assert catalog_integrity_errors() == []
    kinds = {rule.kind for rule in CATEGORY_RULES}
    dispositions = {rule.disposition for rule in CATEGORY_RULES}
    assert kinds == {KIND_AMBIGUITY, KIND_MISSING_CONSTRAINT}
    assert dispositions == {DISPOSITION_FAIL, DISPOSITION_CLARIFY}
    assert "unknown" not in CATEGORIES


def test_fail_and_clarify_mappings_are_deterministic() -> None:
    fail_categories = (
        "conflicting_constraints",
        "duplicate_identity",
        "ambiguous_reference",
        "missing_safety_boundary",
        "missing_constraint_value",
    )
    clarify_categories = (
        "competing_goals",
        "underspecified_scope",
        "ambiguous_platform",
        "conflicting_style",
        "missing_player_count",
        "missing_win_condition",
        "missing_platform",
        "missing_success_criteria",
        "missing_input_surface",
        "missing_output_artifact",
    )
    for category in fail_categories:
        disposition, error = resolve_behavior(category)
        assert error is None
        assert disposition == DISPOSITION_FAIL
        assert CATEGORY_INDEX[category].disposition == DISPOSITION_FAIL
    for category in clarify_categories:
        disposition, error = resolve_behavior(category)
        assert error is None
        assert disposition == DISPOSITION_CLARIFY
    assert set(fail_categories) | set(clarify_categories) == set(CATEGORIES)


def test_unknown_category_fails_closed_and_is_never_clarify() -> None:
    disposition, error = resolve_behavior("nice-to-have")
    assert disposition is None
    assert error is not None
    assert "ambiguity-diagnostics unknown category" in error
    assert "nice-to-have" in error
    assert DISPOSITION_CLARIFY not in error.split(":", 1)[0]


def test_valid_document_has_no_violations() -> None:
    items = [_diagnostic(category) for category in CATEGORIES]
    assert validate_ambiguity_diagnostics(_doc(diagnostics=items)) == []


def test_unknown_category_in_document_fails_closed() -> None:
    document = _doc(
        diagnostics=[
            {
                "category": "guessed_vibe",
                "kind": KIND_AMBIGUITY,
                "disposition": DISPOSITION_CLARIFY,
                "subject": "style",
                "evidence_refs": ["issue:#969"],
            }
        ]
    )
    errors = validate_ambiguity_diagnostics(document)
    assert any("ambiguity-diagnostics unknown category" in item for item in errors)
    assert any("guessed_vibe" in item for item in errors)


def test_claiming_clarify_for_a_fail_category_fails_closed() -> None:
    document = _doc(
        diagnostics=[
            _diagnostic("conflicting_constraints", disposition=DISPOSITION_CLARIFY)
        ]
    )
    errors = validate_ambiguity_diagnostics(document)
    assert any("ambiguity-diagnostics unknown disposition" in item for item in errors)
    assert any("conflicting_constraints" in item for item in errors)


def test_kind_drift_fails_closed() -> None:
    document = _doc(
        diagnostics=[_diagnostic("missing_platform", kind=KIND_AMBIGUITY)]
    )
    errors = validate_ambiguity_diagnostics(document)
    assert any("ambiguity-diagnostics unknown kind" in item for item in errors)


def test_unknown_fields_fail_closed() -> None:
    errors = validate_ambiguity_diagnostics(_doc(severity="high"))
    assert any("ambiguity-diagnostics unknown field" in item for item in errors)
    assert any("severity" in item for item in errors)


def test_missing_fields_and_evidence_fail_closed() -> None:
    document = _doc()
    del document["request_id"]
    document["diagnostics"] = [
        {"category": "underspecified_scope", "kind": KIND_AMBIGUITY, "disposition": DISPOSITION_CLARIFY}
    ]
    errors = validate_ambiguity_diagnostics(document)
    assert any("ambiguity-diagnostics missing_value field" in item for item in errors)
    assert any("request_id" in item for item in errors)
    assert any("ambiguity-diagnostics missing_value evidence_refs" in item for item in errors)
    assert any("ambiguity-diagnostics missing_value subject" in item for item in errors)


def test_wrong_schema_version_and_bool_version_fail_closed() -> None:
    assert any(
        "ambiguity-diagnostics unknown schema_version" in item
        for item in validate_ambiguity_diagnostics(_doc(schema_version=2))
    )
    assert any(
        "ambiguity-diagnostics unknown schema_version" in item
        for item in validate_ambiguity_diagnostics(_doc(schema_version=True))
    )


def test_non_object_root_fails_closed() -> None:
    errors = validate_ambiguity_diagnostics(["not", "an", "object"])
    assert errors == [
        "ambiguity-diagnostics unknown root_type: ambiguity diagnostics document must be an object"
    ]


def test_blank_request_id_fails_closed() -> None:
    errors = validate_ambiguity_diagnostics(_doc(request_id="   "))
    assert any("ambiguity-diagnostics missing_value request_id" in item for item in errors)


def test_aggregate_disposition_is_fail_closed_and_fail_wins() -> None:
    disposition, errors = aggregate_disposition(
        ["underspecified_scope", "conflicting_constraints"]
    )
    assert errors == []
    assert disposition == DISPOSITION_FAIL
    disposition, errors = aggregate_disposition(
        ["missing_platform", "competing_goals"]
    )
    assert errors == []
    assert disposition == DISPOSITION_CLARIFY
    disposition, errors = aggregate_disposition([])
    assert errors == []
    assert disposition is None
    disposition, errors = aggregate_disposition(["invented"])
    assert disposition is None
    assert any("ambiguity-diagnostics unknown category" in item for item in errors)


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "ambiguity.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "Ambiguity-diagnostics schema v1 accepted" in capsys.readouterr().out


def test_cli_rejects_invalid_document(tmp_path: Path, capsys) -> None:
    path = tmp_path / "ambiguity.json"
    path.write_text(
        json.dumps(_doc(diagnostics=[_diagnostic("duplicate_identity", extra=True)])),
        encoding="utf-8",
    )
    assert main([str(path)]) == 1
    stderr = capsys.readouterr().err
    assert "Ambiguity-diagnostics schema validation failed:" in stderr
    assert "ambiguity-diagnostics unknown field" in stderr


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "ambiguity-diagnostics unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_not_wired_into_quality_gates() -> None:
    quality_gates = (REPO_ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "check_ambiguity_diagnostics.py" not in quality_gates
    assert "test_ambiguity_diagnostics.py" not in quality_gates


def test_finding_prefix_and_script_name_are_unique() -> None:
    scripts_dir = REPO_ROOT / "scripts"
    peers = [
        path
        for path in scripts_dir.glob("check_*.py")
        if path.name != "check_ambiguity_diagnostics.py"
    ]
    assert (scripts_dir / "check_ambiguity_diagnostics.py").is_file()
    for path in peers:
        text = path.read_text(encoding="utf-8")
        assert "ambiguity-diagnostics" not in text
        assert "reserve-S035-ambiguity-diagnostics-spec" not in text
