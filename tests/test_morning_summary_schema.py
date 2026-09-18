from __future__ import annotations

import json
from pathlib import Path

from scripts.check_morning_summary_schema import (
    CATEGORIES,
    SCHEMA_VERSION,
    main,
    validate_morning_summary,
)


def _doc(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "window": "2026-09-18",
        "items": [
            {
                "category": "accepted",
                "title": "trigger-fanout audit merged onto main lineage",
                "evidence_refs": ["https://github.com/Apeloff1/Skeleton/pull/1028"],
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_closed_category_set() -> None:
    assert CATEGORIES == (
        "accepted",
        "rejected",
        "blocked",
        "deferred",
        "flaky",
        "unlocked",
    )
    assert len(CATEGORIES) == len(set(CATEGORIES))
    assert SCHEMA_VERSION == 1


def test_valid_document_has_no_violations() -> None:
    assert validate_morning_summary(_doc()) == []


def test_unknown_category_fails_closed() -> None:
    document = _doc(
        items=[
            {
                "category": "nice-to-have",
                "title": "guessed win",
                "evidence_refs": ["issue:#1"],
            }
        ]
    )
    errors = validate_morning_summary(document)
    assert any("morning-summary unknown category" in item for item in errors)
    assert any("nice-to-have" in item for item in errors)


def test_missing_evidence_fails_closed() -> None:
    document = _doc(
        items=[{"category": "blocked", "title": "no proof", "evidence_refs": []}]
    )
    errors = validate_morning_summary(document)
    assert any("morning-summary missing_value evidence_refs" in item for item in errors)


def test_unknown_fields_fail_closed() -> None:
    document = _doc(severity="high")
    errors = validate_morning_summary(document)
    assert any("morning-summary unknown field" in item for item in errors)
    assert any("severity" in item for item in errors)


def test_wrong_schema_version_fails_closed() -> None:
    errors = validate_morning_summary(_doc(schema_version=2))
    assert any("morning-summary unknown schema_version" in item for item in errors)


def test_all_closed_categories_are_accepted() -> None:
    items = [
        {
            "category": category,
            "title": f"{category} row",
            "evidence_refs": [f"evidence:{category}"],
        }
        for category in CATEGORIES
    ]
    assert validate_morning_summary(_doc(items=items)) == []


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "morning.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "Morning-summary schema v1 accepted" in capsys.readouterr().out


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "morning-summary unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")
