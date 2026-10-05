from __future__ import annotations
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/check_ai_research_evaluation_gapfill.py"
SPEC=importlib.util.spec_from_file_location("check_ai_research_evaluation_gapfill",SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

def test_candidate_validator_accepts_repository_state()->None:
    result=module.validate(ROOT)
    assert result["status"]=="valid"
    assert result["volume_count"]==11
    assert result["queued_frontier_preserved"] is True
    assert result["completion_checkbox"] is False
    assert result["production_authority"] is False

def test_candidate_cannot_self_promote()->None:
    candidate=json.loads((ROOT/"machine/ai_research_evaluation_gapfill_candidate.json").read_text(encoding="utf-8"))
    assert tuple(candidate["volume_refs"])==tuple(f"VOL-{value}" for value in range(210,221))
    assert set(candidate["promotion_state"].values())=={False}

def test_candidate_materializes_every_planned_regression()->None:
    candidate=json.loads((ROOT/"machine/ai_research_evaluation_gapfill_candidate.json").read_text(encoding="utf-8"))
    for path in candidate["primary_test_by_volume"].values():
        assert (ROOT/path).is_file()
    assert (ROOT/candidate["shared_implementation"]).is_file()
    assert (ROOT/candidate["assurance_implementation"]).is_file()
