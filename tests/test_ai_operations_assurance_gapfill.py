from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/check_ai_operations_assurance_gapfill.py"
SPEC=importlib.util.spec_from_file_location("check_ai_operations_assurance_gapfill",SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_candidate_validator_accepts_repository_state() -> None:
    result=module.validate(ROOT)
    assert result["status"]=="valid"
    assert result["volume_count"]==12
    assert result["blocked_volume"]=="VOL-195"
    assert result["blocked_artifact"]=="uv.lock"
    assert result["queued_frontier_preserved"] is True
    assert result["completion_checkbox"] is False
    assert result["production_authority"] is False


def test_candidate_excludes_vol195_and_cannot_self_promote() -> None:
    candidate=json.loads(
        (ROOT/"machine/ai_operations_assurance_gapfill_candidate.json").read_text(
            encoding="utf-8"
        )
    )
    assert "VOL-195" not in candidate["volume_refs"]
    assert candidate["excluded_blocker"]["volume_ref"]=="VOL-195"
    assert set(candidate["promotion_state"].values())=={False}


def test_vol195_blocker_is_explicit_and_fail_closed() -> None:
    blocker=json.loads(
        (ROOT/"machine/ai_vol195_local_development_blocker.json").read_text(
            encoding="utf-8"
        )
    )
    assert blocker["status"]=="blocked"
    assert blocker["blocking_artifact"]=="uv.lock"
    assert not (ROOT/"uv.lock").exists()
    fail_closed=blocker["fail_closed_behavior"]
    assert fail_closed["bootstrap_refuses_missing_lock"] is True
    assert fail_closed["unlocked_resolution_allowed"] is False
    assert fail_closed["completion_checkbox"] is False
    assert fail_closed["production_authority"] is False


def test_candidate_binds_shared_gapfill_and_primary_regressions() -> None:
    candidate=json.loads(
        (ROOT/"machine/ai_operations_assurance_gapfill_candidate.json").read_text(
            encoding="utf-8"
        )
    )
    assert (ROOT/candidate["gapfill_implementation"]).is_file()
    assert (ROOT/candidate["gapfill_test"]).is_file()
    for path in candidate["primary_implementation_by_volume"].values():
        assert (ROOT/path).is_file()
    for path in candidate["primary_test_by_volume"].values():
        assert (ROOT/path).is_file()
