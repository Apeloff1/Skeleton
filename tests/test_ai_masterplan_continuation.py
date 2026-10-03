from __future__ import annotations
import json,shutil
from pathlib import Path
import pytest
from scripts.check_ai_masterplan_continuation import MasterplanContinuationError,validate

ROOT=Path(__file__).resolve().parents[1]
FILES=("machine/ai_masterplan_continuation_frontier.json","machine/ai_app_construction.json","machine/ai_p1_terminal_closure.json","machine/ai_p2_functional_ai_closure.json","machine/ai_p3_expansion_closure.json","machine/ai_p3_engineering_closure.json","machine/ai_p3_engineering_execution_map.json","machine/ai_p3_execution_map.json","machine/ai_master_plan.json")
def _fixture(tmp_path:Path)->Path:
    for rel in FILES:
        dst=tmp_path/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/rel,dst)
    return tmp_path
def _load(path:Path)->dict: return json.loads(path.read_text(encoding="utf-8"))
def _store(path:Path,payload:dict)->None: path.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")

def test_current_continuation_frontier_is_valid():
    r=validate(ROOT); assert r["canonical_gap_count"]==17; assert r["p1_terminal_closed_volume_count"]==107; assert r["p3_t1_deferred_volume_count"]==197; assert r["p3_t2_planned_volume_count"]==32; assert r["p3_t2_queued_volume_count"]==165; assert r["native_training_core_volume_count"]==19
def test_rejects_reopened_p0_gap(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_app_construction.json"; p=_load(path); p["gap_register"][0]["status"]="open"; _store(path,p)
    with pytest.raises(MasterplanContinuationError,match="canonical gap reopened"): validate(root)
def test_rejects_p1_terminal_partition_drift(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_p1_terminal_closure.json"; p=_load(path); p["frontier"]["deferred_to_p2_volume_count"]=313; _store(path,p)
    with pytest.raises(MasterplanContinuationError,match="421/107/314"): validate(root)
def test_rejects_lost_t2_volume(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_masterplan_continuation_frontier.json"; p=_load(path); p["next_tranche"]["queued_volume_refs"].pop(); p["next_tranche"]["queued_volume_count"]=164; _store(path,p)
    with pytest.raises(MasterplanContinuationError,match="32/165"): validate(root)
def test_rejects_double_owned_t2_volume(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_masterplan_continuation_frontier.json"; p=_load(path); p["next_tranche"]["queued_volume_refs"][0]=p["next_tranche"]["scheduled_volume_refs"][0]; _store(path,p)
    with pytest.raises(MasterplanContinuationError,match="ownership overlaps"): validate(root)
def test_rejects_false_t2_completion(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_masterplan_continuation_frontier.json"; p=_load(path); p["next_tranche"]["status"]="closed"; _store(path,p)
    with pytest.raises(MasterplanContinuationError,match="must remain planned"): validate(root)
def test_rejects_native_training_escape(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_masterplan_continuation_frontier.json"; p=_load(path); escaped=p["reconciliation"]["native_training_core_volume_refs"][0]; p["next_tranche"]["scheduled_volume_refs"].remove(escaped); repl=p["next_tranche"]["queued_volume_refs"].pop(); p["next_tranche"]["scheduled_volume_refs"].append(repl); p["next_tranche"]["queued_volume_refs"].append(escaped); _store(path,p)
    with pytest.raises(MasterplanContinuationError,match="scheduled identity drift|escaped consolidated"): validate(root)
