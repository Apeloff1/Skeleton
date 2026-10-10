from __future__ import annotations
import json, shutil
from pathlib import Path
import pytest
from scripts.check_p3_training_execution_map import P3TrainingValidationError, validate

ROOT=Path(__file__).resolve().parents[1]
FILES=(
    "machine/ai_master_plan.json",
    "machine/ai_p3_engineering_execution_map.json",
    "machine/ai_p3_engineering_closure.json",
    "machine/ai_p3_training_execution_map.json",
    "machine/ai_p3_training_task_backlog.json",
)

def _fixture(tmp_path:Path)->Path:
    for rel in FILES:
        dst=tmp_path/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/rel,dst)
    return tmp_path

def test_current_training_frontier_is_valid():
    result=validate(ROOT)
    assert result["source_volume_count"]==197
    assert result["scheduled_volume_count"]==19
    assert result["queued_volume_count"]==178
    assert result["task_count"]==4

def test_rejects_queue_loss(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_p3_training_execution_map.json"; data=json.loads(path.read_text())
    data["first_tranche"]["queued_volume_refs"].pop(); data["first_tranche"]["queued_volume_count"]-=1; path.write_text(json.dumps(data))
    with pytest.raises(P3TrainingValidationError): validate(root)

def test_rejects_double_ownership(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_p3_training_task_backlog.json"; data=json.loads(path.read_text())
    data["tasks"][1]["primary_volume_refs"].append("VOL-133"); path.write_text(json.dumps(data))
    with pytest.raises(P3TrainingValidationError): validate(root)

def test_rejects_premature_ready_dependency(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_p3_training_task_backlog.json"; data=json.loads(path.read_text())
    data["tasks"][1]["status"]="ready"; data["summary"]["ready_count"]=2; data["summary"]["blocked_count"]=2; path.write_text(json.dumps(data))
    with pytest.raises(P3TrainingValidationError,match="unresolved dependencies"): validate(root)

def test_rejects_self_signoff(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_p3_training_task_backlog.json"; data=json.loads(path.read_text())
    data["tasks"][0]["verification_signed"]=True; path.write_text(json.dumps(data))
    with pytest.raises(P3TrainingValidationError,match="self-complete or self-sign"): validate(root)
