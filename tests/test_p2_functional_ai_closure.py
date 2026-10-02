from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.check_p2_functional_ai_closure import validate


ROOT = Path(__file__).resolve().parents[1]


def test_current_functional_ai_candidate_is_structurally_valid() -> None:
    result = validate(ROOT)
    assert result["valid"] is True
    assert result["closure_status"] == "candidate"
    assert result["source_volume_count"] == 314
    assert result["scheduled_volume_count"] == 57
    assert result["queued_volume_count"] == 257
    assert result["provider_independent"] is True


def test_closed_mode_refuses_candidate() -> None:
    result = validate(ROOT, require_closed=True)
    assert result["valid"] is False
    assert "functional closure is not closed" in result["errors"]
