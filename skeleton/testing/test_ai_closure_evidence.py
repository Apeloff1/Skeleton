from __future__ import annotations

import json

from scripts import check_ai_closure_evidence as checker


def _payloads():
    ledger = json.loads(checker.LEDGER.read_text(encoding="utf-8"))
    construction = json.loads(checker.CONSTRUCTION.read_text(encoding="utf-8"))
    return ledger, construction


def test_ai_closure_evidence_is_valid() -> None:
    assert checker.validate() == []


def test_all_p0_entries_use_declared_implementation_states() -> None:
    ledger, _ = _payloads()
    allowed = set(ledger["implementation_states"])
    assert all(entry["implementation_state"] in allowed for entry in ledger["entries"])


def test_closure_ledger_rejects_unknown_implementation_state() -> None:
    ledger, construction = _payloads()
    mutated = json.loads(json.dumps(ledger))
    mutated["entries"][0]["implementation_state"] = "closed"

    errors = checker.validate(mutated, construction)

    assert any("invalid implementation_state" in error for error in errors)


def test_closure_ledger_rejects_missing_p0_gap() -> None:
    ledger, construction = _payloads()
    mutated = json.loads(json.dumps(ledger))
    mutated["entries"].pop()

    errors = checker.validate(mutated, construction)

    assert "closure ledger must cover every P0 gap exactly once" in errors


def test_closed_gap_cannot_retain_outstanding_evidence() -> None:
    ledger, construction = _payloads()
    mutated = json.loads(json.dumps(ledger))
    item = mutated["entries"][0]
    item["outstanding_evidence"] = ["missing exact-head proof"]

    errors = checker.validate(mutated, construction)

    assert any("closed decision cannot retain outstanding evidence" in error for error in errors)


def test_closure_implementation_state_tracks_blueprint() -> None:
    ledger, construction = _payloads()
    mutated = json.loads(json.dumps(ledger))
    mutated["entries"][0]["implementation_state"] = "implemented"

    errors = checker.validate(mutated, construction)

    assert any("implementation_state disagrees with blueprint status" in error for error in errors)
