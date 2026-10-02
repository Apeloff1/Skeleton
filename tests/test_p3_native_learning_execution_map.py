from __future__ import annotations
import json
import shutil
from pathlib import Path
import pytest
from scripts.check_p3_native_learning_execution_map import P3NativeLearningError, validate

ROOT=Path(__file__).resolve().parents[1]

def _fixture(tmp_path:Path)->Path:
    for rel in (
        "machine/ai_p3_native_learning_execution_map.json",
        "machine/ai_p3_native_learning_task_backlog.json",
        "machine/ai_p3_tranche2_plan.json",
        "machine/ai_p3_engineering_execution_map.json",
        "machine/ai_p3_engineering_closure.json",
        "machine/ai_master_plan.json",
    ):
        dst=tmp_path/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/rel,dst)
    return tmp_path

def test_current_native_learning_authority_is_valid()->None:
    result=validate(ROOT)
    assert result=={"status":"valid","source_volume_count":197,"scheduled_volume_count":52,"queued_volume_count":145,"task_count":7}

def test_rejects_scope_loss(tmp_path:Path)->None:
    root=_fixture(tmp_path); path=root/"machine/ai_p3_native_learning_execution_map.json"
    data=json.loads(path.read_text()); data["first_tranche"]["queued_volume_refs"].pop(); path.write_text(json.dumps(data))
    with pytest.raises(P3NativeLearningError,match="cover source exactly"): validate(root)

def test_rejects_double_ownership(tmp_path:Path)->None:
    root=_fixture(tmp_path); path=root/"machine/ai_p3_native_learning_task_backlog.json"
    data=json.loads(path.read_text()); data["tasks"][1]["primary_volume_refs"].append(data["tasks"][0]["primary_volume_refs"][0]); path.write_text(json.dumps(data))
    with pytest.raises(P3NativeLearningError,match="obligation ownership drift|exactly one task owner"): validate(root)

def test_rejects_masterplan_narrowing(tmp_path:Path)->None:
    root=_fixture(tmp_path); path=root/"machine/ai_p3_native_learning_task_backlog.json"
    data=json.loads(path.read_text()); data["tasks"][0]["masterplan_obligations"][0]["risks"]=[]; path.write_text(json.dumps(data))
    with pytest.raises(P3NativeLearningError,match="narrows/drifts"): validate(root)

def test_rejects_self_sign(tmp_path:Path)->None:
    root=_fixture(tmp_path); path=root/"machine/ai_p3_native_learning_task_backlog.json"
    data=json.loads(path.read_text()); data["tasks"][0]["verification_signed"]=True; path.write_text(json.dumps(data))
    with pytest.raises(P3NativeLearningError,match="may not self-complete/sign"): validate(root)
