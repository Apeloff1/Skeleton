from __future__ import annotations
import json,subprocess
from pathlib import Path
import pytest
from scripts.check_ai_oct2026_engineering_standards import Oct2026StandardsCandidateError,validate

ROOT=Path(__file__).resolve().parents[1]
def head(): return subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
def test_current_candidate_is_exact_head_valid():
    result=validate(ROOT,head=head())
    assert result["volume_count"]==14 and result["security_mirror_pair_count"]==2
    assert result["queued_frontier_preserved"] is True and result["completion_checkbox"] is False and result["production_authority"] is False
def test_malformed_head_rejected():
    with pytest.raises(Oct2026StandardsCandidateError,match="reported exact head malformed"): validate(ROOT,head="bad")
def test_other_exact_head_rejected():
    other="a"*40 if head()!="a"*40 else "b"*40
    with pytest.raises(Oct2026StandardsCandidateError,match="does not match checkout"): validate(ROOT,head=other)
def test_all_fourteen_volumes_remain_deferred():
    frontier=json.loads((ROOT/"machine/ai_masterplan_continuation_frontier.json").read_text())
    candidate=json.loads((ROOT/"machine/ai_oct2026_engineering_standards_candidate.json").read_text())
    refs=set(candidate["volume_refs"])
    assert refs.issubset(set(frontier["next_tranche"]["queued_volume_refs"]))
    assert refs.isdisjoint(set(frontier["next_tranche"]["scheduled_volume_refs"]))
