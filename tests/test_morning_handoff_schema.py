from __future__ import annotations

import json
from pathlib import Path

from scripts.check_morning_handoff_schema import (
    SCHEMA_VERSION,
    SECTIONS,
    main,
    validate_morning_handoff,
)


def _doc(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "window": "2026-09-18",
        "sections": {
            "shipped": [
                {
                    "title": "trigger-fanout audit mergeable",
                    "evidence_refs": ["https://github.com/Apeloff1/Skeleton/pull/1028"],
                }
            ],
            "validated": [],
            "failed_closed": [],
            "ready_next": [
                {
                    "title": "retrieval surface inventory",
                    "evidence_refs": ["issue:#969"],
                }
            ],
        },
    }
    payload.update(overrides)
    return payload


def test_closed_section_set() -> None:
    assert SECTIONS == ("shipped", "validated", "failed_closed", "ready_next")
    assert SCHEMA_VERSION == 1


def test_valid_document_has_no_violations() -> None:
    assert validate_morning_handoff(_doc()) == []


def test_unknown_section_fails_closed() -> None:
    document = _doc()
    document["sections"] = dict(document["sections"])
    document["sections"]["vibes"] = []
    errors = validate_morning_handoff(document)
    assert any("morning-handoff unknown section" in item for item in errors)
    assert any("vibes" in item for item in errors)


def test_missing_section_fails_closed() -> None:
    document = _doc()
    sections = dict(document["sections"])
    del sections["ready_next"]
    document["sections"] = sections
    errors = validate_morning_handoff(document)
    assert any("morning-handoff missing_value section" in item for item in errors)


def test_missing_evidence_fails_closed() -> None:
    document = _doc()
    document["sections"] = dict(document["sections"])
    document["sections"]["shipped"] = [{"title": "no proof", "evidence_refs": []}]
    errors = validate_morning_handoff(document)
    assert any("morning-handoff missing_value evidence_refs" in item for item in errors)


def test_unknown_fields_fail_closed() -> None:
    errors = validate_morning_handoff(_doc(owner="night"))
    assert any("morning-handoff unknown field" in item for item in errors)


def test_wrong_schema_version_fails_closed() -> None:
    errors = validate_morning_handoff(_doc(schema_version=2))
    assert any("morning-handoff unknown schema_version" in item for item in errors)


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "Morning-handoff schema v1 accepted" in capsys.readouterr().out


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{nope", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "morning-handoff unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")
