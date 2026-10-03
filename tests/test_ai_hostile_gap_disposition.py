from __future__ import annotations

import copy
import json
from pathlib import Path

import scripts.verify_ai_hostile_gap_disposition as verifier


ROOT = Path(__file__).resolve().parents[1]


def _ledger() -> dict:
    return json.loads(
        (ROOT / "machine/ai_hostile_gap_disposition.json").read_text(encoding="utf-8")
    )


def _validate_mutation(monkeypatch, mutate):
    original = verifier._load_json
    value = copy.deepcopy(_ledger())
    mutate(value)

    def fake_load(root):
        return copy.deepcopy(value)

    monkeypatch.setattr(verifier, "_load_json", fake_load)
    try:
        return verifier.validate(ROOT)
    finally:
        monkeypatch.setattr(verifier, "_load_json", original)


def test_current_hostile_gap_ledger_is_complete_and_valid() -> None:
    result = verifier.validate(ROOT)
    assert result["valid"] is True, result["errors"]
    assert result["audit_gap_count"] == 200
    assert sum(result["severity_counts"].values()) == 200
    assert result["status_counts"]["implementation_pr_open"] == 10


def test_missing_gap_fails_closed(monkeypatch) -> None:
    result = _validate_mutation(
        monkeypatch,
        lambda value: value["gaps"].pop(),
    )
    assert result["valid"] is False
    assert any("ledger missing audit gaps" in error for error in result["errors"])


def test_severity_drift_fails_closed(monkeypatch) -> None:
    def mutate(value):
        value["gaps"][0]["severity"] = "P2"

    result = _validate_mutation(monkeypatch, mutate)
    assert result["valid"] is False
    assert "G001 severity drift" in result["errors"]


def test_open_implementation_pr_requires_canonical_pr_ref(monkeypatch) -> None:
    def mutate(value):
        item = next(g for g in value["gaps"] if g["id"] == "G001")
        item["implementation_refs"] = ["branch:maybe"]

    result = _validate_mutation(monkeypatch, mutate)
    assert result["valid"] is False
    assert any("noncanonical implementation PR ref" in error for error in result["errors"])


def test_verified_closed_cannot_exist_without_evidence(monkeypatch) -> None:
    def mutate(value):
        item = next(g for g in value["gaps"] if g["id"] == "G006")
        item["status"] = "verified_closed"
        item["implementation_refs"] = ["github:pr#9999"]
        item["evidence_refs"] = []
        item["closure_note"] = None
        value["summary"]["verified_closed"] = 1

    result = _validate_mutation(monkeypatch, mutate)
    assert result["valid"] is False
    assert "G006 verified_closed requires evidence" in result["errors"]
    assert "G006 verified_closed requires closure_note" in result["errors"]


def test_summary_is_derived_not_manual(monkeypatch) -> None:
    def mutate(value):
        value["summary"]["implementation_pr_open"] = 999

    result = _validate_mutation(monkeypatch, mutate)
    assert result["valid"] is False
    assert any(
        "summary implementation_pr_open drift" in error
        for error in result["errors"]
    )
