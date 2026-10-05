from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/check_ai_observability_governance_gapfill.py"
SPEC=importlib.util.spec_from_file_location("check_ai_observability_governance_gapfill",SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_candidate_validator_accepts_repository_state() -> None:
    result=module.validate(ROOT)
    assert result["status"]=="valid"
    assert result["volume_count"]==8
    assert result["queued_frontier_preserved"] is True
    assert result["completion_checkbox"] is False
    assert result["production_authority"] is False


def test_candidate_cannot_self_promote_or_self_sign() -> None:
    candidate=json.loads(
        (ROOT/"machine/ai_observability_governance_gapfill_candidate.json").read_text(
            encoding="utf-8"
        )
    )
    assert candidate["status"]=="implementation_candidate"
    assert candidate["source_queue_state"]=="queued_unmodified"
    assert set(candidate["promotion_state"].values())=={False}


def test_candidate_binds_all_expected_primary_tests() -> None:
    candidate=json.loads(
        (ROOT/"machine/ai_observability_governance_gapfill_candidate.json").read_text(
            encoding="utf-8"
        )
    )
    assert tuple(candidate["volume_refs"])==(
        "VOL-180","VOL-181","VOL-182","VOL-183",
        "VOL-184","VOL-185","VOL-186","VOL-187",
    )
    for path in candidate["primary_test_by_volume"].values():
        assert (ROOT/path).is_file()
