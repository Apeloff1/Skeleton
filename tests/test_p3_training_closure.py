from __future__ import annotations
import json, shutil
from pathlib import Path
import pytest
from scripts.check_p3_training_closure import P3TrainingClosureError, validate

ROOT=Path(__file__).resolve().parents[1]
FILES=(
    "machine/ai_p3_engineering_closure.json",
    "machine/ai_p3_training_execution_map.json",
    "machine/ai_p3_training_task_backlog.json",
    "machine/ai_p3_training_closure.json",
)
SURFACES=(
    "skeleton/ai/runtime/training/data.py",
    "skeleton/ai/runtime/training/control.py",
    "skeleton/ai/runtime/training/trainer.py",
    "skeleton/ai/runtime/training/evaluation.py",
    "skeleton/ai/runtime/training/post_training.py",
)

def _fixture(tmp_path:Path)->Path:
    for rel in FILES+SURFACES:
        dst=tmp_path/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,dst)
    return tmp_path

def test_current_training_closure_candidate_is_valid():
    result=validate(ROOT)
    assert result["closure_status"]=="candidate"
    assert result["scheduled_volume_count"]==19
    assert result["queued_volume_count"]==178
    assert result["landed_task_count"]==4
    assert result["production_promotion_authorized"] is False

def test_rejects_fabricated_signoff(tmp_path:Path):
    root=_fixture(tmp_path);path=root/"machine/ai_p3_training_task_backlog.json";data=json.loads(path.read_text())
    data["tasks"][0]["implementation_signed"]=True;path.write_text(json.dumps(data))
    with pytest.raises(P3TrainingClosureError,match="self-complete or self-sign"):validate(root)

def test_rejects_deferred_scope_loss(tmp_path:Path):
    root=_fixture(tmp_path);path=root/"machine/ai_p3_training_closure.json";data=json.loads(path.read_text())
    data["deferred_scope"]["queued_volume_refs"].pop();path.write_text(json.dumps(data))
    with pytest.raises(P3TrainingClosureError,match="deferred queue"):validate(root)

def test_closed_mode_requires_closure_workflow_evidence(tmp_path:Path):
    root=_fixture(tmp_path);path=root/"machine/ai_p3_training_closure.json";data=json.loads(path.read_text())
    data["status"]="closed";data["closure_evidence"]=["github:pr#2352","git-head:"+"a"*40,"workflow:other:success"];path.write_text(json.dumps(data))
    with pytest.raises(P3TrainingClosureError,match="closure workflow evidence"):validate(root)
