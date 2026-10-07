from __future__ import annotations

import json
import shutil
from pathlib import Path

import scripts.check_p2_functional_ai_closure as verifier
from scripts.check_p2_functional_ai_closure import validate


ROOT = Path(__file__).resolve().parents[1]


def test_current_functional_ai_frontier_is_closed_and_structurally_valid() -> None:
    result = validate(ROOT)
    assert result["valid"] is True
    assert result["closure_status"] == "closed"
    assert result["source_volume_count"] == 314
    assert result["scheduled_volume_count"] == 57
    assert result["queued_volume_count"] == 257
    assert result["provider_independent"] is True
    assert result["claim_limits"]["provider_independent_execution_proven"] is True
    assert result["claim_limits"]["advanced_model_capability_proven"] is False
    assert result["claim_limits"]["general_intelligence_proven"] is False
    assert result["claim_limits"]["superintelligence_proven"] is False
    assert result["production_local_weights_runtime"] is True
    assert result["exact_head_receipt_policy"] is True


def test_closed_mode_accepts_closed_frontier() -> None:
    result = validate(ROOT, require_closed=True)
    assert result["valid"] is True
    assert result["closure_status"] == "closed"


def test_unsupported_advanced_claim_fails_closed(monkeypatch) -> None:
    original_load = verifier._load

    def mutated_load(root, rel):
        value = original_load(root, rel)
        if rel == verifier.MANIFEST:
            value["claim_limits"] = dict(value["claim_limits"])
            value["claim_limits"]["advanced_model_capability_proven"] = True
        return value

    monkeypatch.setattr(verifier, "_load", mutated_load)
    result = verifier.validate(ROOT)
    assert result["valid"] is False
    assert "claim limit advanced_model_capability_proven must be false" in result["errors"]


def test_reference_model_cannot_be_declared_quality_target(monkeypatch) -> None:
    original_load = verifier._load

    def mutated_load(root, rel):
        value = original_load(root, rel)
        if rel == verifier.MANIFEST:
            value["claim_limits"] = dict(value["claim_limits"])
            value["claim_limits"]["reference_model_is_quality_target"] = True
        return value

    monkeypatch.setattr(verifier, "_load", mutated_load)
    result = verifier.validate(ROOT)
    assert result["valid"] is False
    assert "claim limit reference_model_is_quality_target must be false" in result["errors"]
