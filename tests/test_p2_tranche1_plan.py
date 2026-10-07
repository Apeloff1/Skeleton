from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_p2_tranche1_plan import validate


ROOT = Path(__file__).resolve().parents[1]


def test_current_tranche_state_is_activated() -> None:
    result = validate(ROOT)
    assert result["status"] == "valid"
    assert result["tranche_state"] == "activated"
    assert result["selected_volume_count"] == 15
    assert result["workstream_count"] == 5
    assert result["scheduled_volume_count"] == 57
    assert result["queued_volume_count"] == 257


def test_plan_machine_state_is_not_prepared_anymore() -> None:
    payload = json.loads(
        (ROOT / "machine/ai_p2_tranche1_plan.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "activated"
    assert payload["activation"]["mode"] == "applied"
