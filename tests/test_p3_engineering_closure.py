from __future__ import annotations
import json,shutil
from pathlib import Path
import pytest
from scripts.check_p3_engineering_closure import P3EngineeringClosureError,validate
ROOT=Path(__file__).resolve().parents[1]
FILES=("machine/ai_p3_engineering_closure.json","machine/ai_p3_engineering_execution_map.json","machine/ai_p3_engineering_task_backlog.json","machine/ai_p3_expansion_closure.json")
def _fixture(tmp_path:Path)->Path:
    for rel in FILES:
        dst=tmp_path/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/rel,dst)
    return tmp_path
def test_current_candidate_is_valid():
    r=validate(ROOT); assert r["scheduled_volume_count"]==37; assert r["queued_volume_count"]==197; assert r["landed_task_count"]==6
def test_rejects_false_full_completion(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_p3_engineering_closure.json"; p=json.loads(path.read_text()); p["deferred_scope"]["queued_volume_count"]=0; path.write_text(json.dumps(p))
    with pytest.raises(P3EngineeringClosureError,match="preserve 197"): validate(root)
def test_rejects_self_signoff(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_p3_engineering_task_backlog.json"; p=json.loads(path.read_text()); p["tasks"][0]["verification_signed"]=True; path.write_text(json.dumps(p))
    with pytest.raises(P3EngineeringClosureError,match="self-complete or self-sign"): validate(root)
def test_closed_requires_closure_evidence(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_p3_engineering_closure.json"; p=json.loads(path.read_text()); p["status"]="closed"; p["closure_evidence"]=["github:pr#2348"]; path.write_text(json.dumps(p))
    with pytest.raises(P3EngineeringClosureError,match="exact-head closure evidence"): validate(root)
