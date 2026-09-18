from __future__ import annotations

import json
from pathlib import Path

from scripts.check_memory_budget_schema import (
    BUDGET_KINDS,
    BUDGET_UNITS,
    CONFLICT_DOMAIN,
    DOCUMENT_FIELDS,
    FALLBACK_POLICIES,
    SCHEMA_VERSION,
    TASK_ID,
    TRUNCATION_POLICIES,
    main,
    validate_memory_budget,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _budgets(**overrides):
    payload = {
        "item": {"limit": 5, "unit": "items"},
        "token": {"limit": 2048, "unit": "tokens"},
        "byte": {"limit": 65536, "unit": "bytes"},
    }
    payload.update(overrides)
    return payload


def _provenance(**overrides):
    payload = {
        "source_repository": "required",
        "source_revision": "optional",
        "source_path": "optional",
        "content_in_audit": False,
    }
    payload.update(overrides)
    return payload


def _doc(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "budgets": _budgets(),
        "provenance": _provenance(),
        "truncation": "reject_overflow",
        "fallback": "fail_closed",
        "evidence_refs": ["docs/MEMORY_RETRIEVAL.md:guardrails"],
    }
    payload.update(overrides)
    return payload


def test_schema_contract_is_budgets_not_retrieval_surfaces() -> None:
    assert SCHEMA_VERSION == 1
    assert TASK_ID == "reserve-S057-memory-budget-review"
    assert CONFLICT_DOMAIN == "rag.spec.bounded_retrieval"
    assert DOCUMENT_FIELDS == {
        "schema_version",
        "budgets",
        "provenance",
        "truncation",
        "fallback",
        "evidence_refs",
    }
    assert BUDGET_KINDS == ("item", "token", "byte")
    assert BUDGET_UNITS == {"item": "items", "token": "tokens", "byte": "bytes"}
    assert TRUNCATION_POLICIES == (
        "reject_overflow",
        "drop_lowest_relevance",
        "truncate_content",
    )
    assert FALLBACK_POLICIES == ("fail_closed", "empty_context")
    source = (REPO_ROOT / "scripts" / "check_memory_budget_schema.py").read_text(
        encoding="utf-8"
    )
    assert "check_retrieval_surface_inventory" not in source
    assert "rag.readonly.surface_inventory" not in source
    assert "reserve-S121" not in source
    assert "REQUIRED_SCAN_ROOTS" not in source
    assert "legacy_adapter" not in source
    for capability in ('"ingestion"', '"retrieve"', '"rank"', '"storage"'):
        assert capability not in source
    errors = validate_memory_budget(["bad"])
    assert errors and errors[0].startswith("memory-budget ")


def test_valid_document_has_no_violations() -> None:
    assert validate_memory_budget(_doc()) == []
    for truncation in TRUNCATION_POLICIES:
        for fallback in FALLBACK_POLICIES:
            assert (
                validate_memory_budget(_doc(truncation=truncation, fallback=fallback))
                == []
            )


def test_unknown_document_fields_fail_closed() -> None:
    errors = validate_memory_budget(_doc(surface="canonical", severity="high"))
    assert any("memory-budget unknown field" in item for item in errors)
    assert any("surface" in item for item in errors)
    assert any("severity" in item for item in errors)


def test_unknown_budget_kinds_fail_closed() -> None:
    budgets = _budgets(approx={"limit": 3, "unit": "items"}, gpu={"limit": 1, "unit": "bytes"})
    errors = validate_memory_budget(_doc(budgets=budgets))
    unknown = [item for item in errors if "memory-budget unknown budget_field" in item]
    assert unknown
    assert any("approx" in item for item in unknown)
    assert any("gpu" in item for item in unknown)


def test_unknown_budget_object_fields_fail_closed() -> None:
    budgets = _budgets(
        item={"limit": 5, "unit": "items", "soft_limit": 8, "warning": True}
    )
    errors = validate_memory_budget(_doc(budgets=budgets))
    unknown = [item for item in errors if "memory-budget unknown budget_field" in item]
    assert unknown
    assert any("soft_limit" in item for item in unknown)
    assert any("warning" in item for item in unknown)


def test_missing_budget_kinds_fail_closed() -> None:
    budgets = _budgets()
    del budgets["token"]
    del budgets["byte"]
    errors = validate_memory_budget(_doc(budgets=budgets))
    assert any("memory-budget missing_value budget_field" in item for item in errors)
    assert any("token" in item for item in errors)
    assert any("byte" in item for item in errors)


def test_missing_fields_fail_closed() -> None:
    document = _doc()
    del document["truncation"]
    del document["evidence_refs"]
    errors = validate_memory_budget(document)
    assert any("memory-budget missing_value field" in item for item in errors)
    assert any("truncation" in item for item in errors)
    assert any("memory-budget missing_value evidence_refs" in item for item in errors)


def test_wrong_units_fail_closed() -> None:
    errors = validate_memory_budget(
        _doc(
            budgets=_budgets(
                item={"limit": 5, "unit": "tokens"},
                token={"limit": 8, "unit": "bytes"},
                byte={"limit": 16, "unit": "items"},
            )
        )
    )
    unit_errors = [item for item in errors if "memory-budget unknown unit" in item]
    assert len(unit_errors) == 3


def test_non_positive_and_bool_limits_fail_closed() -> None:
    errors = validate_memory_budget(
        _doc(
            budgets=_budgets(
                item={"limit": 0, "unit": "items"},
                token={"limit": -1, "unit": "tokens"},
                byte={"limit": True, "unit": "bytes"},
            )
        )
    )
    limit_errors = [item for item in errors if "memory-budget unknown limit" in item]
    assert len(limit_errors) == 3


def test_unknown_truncation_and_fallback_fail_closed() -> None:
    errors = validate_memory_budget(
        _doc(truncation="best_effort", fallback="guess_prior")
    )
    assert any("memory-budget unknown truncation" in item for item in errors)
    assert any("best_effort" in item for item in errors)
    assert any("memory-budget unknown fallback" in item for item in errors)
    assert any("guess_prior" in item for item in errors)


def test_unknown_provenance_fields_fail_closed() -> None:
    errors = validate_memory_budget(
        _doc(provenance=_provenance(owner="night", guessed_source=True))
    )
    assert any("memory-budget unknown field" in item for item in errors)
    assert any("owner" in item for item in errors)
    assert any("guessed_source" in item for item in errors)


def test_source_repository_must_be_required() -> None:
    optional = validate_memory_budget(
        _doc(provenance=_provenance(source_repository="optional"))
    )
    assert any("memory-budget unknown provenance" in item for item in optional)
    forbidden = validate_memory_budget(
        _doc(provenance=_provenance(source_repository="forbidden"))
    )
    assert any("memory-budget unknown provenance" in item for item in forbidden)


def test_content_in_audit_must_be_false() -> None:
    errors = validate_memory_budget(
        _doc(provenance=_provenance(content_in_audit=True))
    )
    assert any("memory-budget unknown provenance" in item for item in errors)
    stringed = validate_memory_budget(
        _doc(provenance=_provenance(content_in_audit="false"))
    )
    assert any("memory-budget unknown provenance" in item for item in stringed)


def test_unknown_revision_presence_fails_closed() -> None:
    errors = validate_memory_budget(
        _doc(provenance=_provenance(source_revision="when-available"))
    )
    assert any("memory-budget unknown provenance" in item for item in errors)


def test_missing_and_blank_evidence_fail_closed() -> None:
    empty = validate_memory_budget(_doc(evidence_refs=[]))
    assert any("memory-budget missing_value evidence_refs" in item for item in empty)
    blank = validate_memory_budget(_doc(evidence_refs=["", "  "]))
    assert any("memory-budget unknown evidence_ref" in item for item in blank)
    not_list = validate_memory_budget(_doc(evidence_refs="docs/MEMORY_RETRIEVAL.md"))
    assert any("memory-budget missing_value evidence_refs" in item for item in not_list)


def test_wrong_schema_version_fails_closed() -> None:
    errors = validate_memory_budget(_doc(schema_version=2))
    assert any("memory-budget unknown schema_version" in item for item in errors)
    bool_version = validate_memory_budget(_doc(schema_version=True))
    assert any("memory-budget unknown schema_version" in item for item in bool_version)


def test_non_object_root_fails_closed() -> None:
    errors = validate_memory_budget(["not", "an", "object"])
    assert errors == ["memory-budget unknown root_type: memory budget document must be an object"]


def test_budget_and_provenance_must_be_objects() -> None:
    budgets = validate_memory_budget(_doc(budgets=["item", "token", "byte"]))
    assert any("memory-budget unknown budgets_type" in item for item in budgets)
    provenance = validate_memory_budget(_doc(provenance="required"))
    assert any("memory-budget unknown provenance_type" in item for item in provenance)
    nested = validate_memory_budget(
        _doc(budgets=_budgets(item=5, token="2048", byte=["65536"]))
    )
    type_errors = [item for item in nested if "memory-budget unknown budget_type" in item]
    assert len(type_errors) == 3


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "memory-budget.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "Memory-budget schema v1 accepted" in capsys.readouterr().out


def test_cli_rejects_invalid_document(tmp_path: Path, capsys) -> None:
    path = tmp_path / "memory-budget.json"
    path.write_text(
        json.dumps(_doc(truncation="maybe", budgets=_budgets(approx={"limit": 1, "unit": "items"}))),
        encoding="utf-8",
    )
    assert main([str(path)]) == 1
    stderr = capsys.readouterr().err
    assert "Memory-budget schema validation failed:" in stderr
    assert "memory-budget unknown truncation" in stderr
    assert "memory-budget unknown budget_field" in stderr


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "memory-budget unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_not_wired_into_quality_gates() -> None:
    quality_gates = (REPO_ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "check_memory_budget_schema.py" not in quality_gates
    assert "test_memory_budget_schema.py" not in quality_gates
    assert (REPO_ROOT / "scripts" / "check_memory_budget_schema.py").is_file()
    assert (REPO_ROOT / "tests" / "test_memory_budget_schema.py").is_file()
    assert not (REPO_ROOT / "scripts" / "check_retrieval_surface_inventory.py").exists()
