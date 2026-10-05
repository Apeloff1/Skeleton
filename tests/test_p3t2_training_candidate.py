"""Candidate contract tests for unsigned P3T2-TRAINING-01."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_p3t2_training_candidate import validate


ROOT = Path(__file__).resolve().parents[1]


def test_training_candidate_contract_stays_unsigned() -> None:
    result = validate(ROOT)
    assert result["status"] == "valid"
    assert result["volume_count"] == 7
    assert result["promotion_authority"] is False
    payload = json.loads((ROOT / "machine/ai_p3t2_training_candidate.json").read_text(encoding="utf-8"))
    assert payload["promotion_state"]["may_self_close"] is False
    assert payload["status"] == "implementation_candidate"
