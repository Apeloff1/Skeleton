from __future__ import annotations
import json
import shutil
from pathlib import Path
import pytest
from scripts.check_p3_native_training_execution_map import ValidationError, validate

ROOT=Path(__file__).resolve().parents[1]

def test_current_native_training_map_is_valid() -> None:
    result=validate(ROOT)
    assert result["status"]=="valid"
    assert result["source_volume_count"]==197
    assert result["scheduled_volume_count"]==24
    assert result["queued_volume_count"]==173
    assert result["owned_volume_count"]==24

def _fixture(tmp_path: Path) -> Path:
    for rel in (
        "machine/ai_p3_native_training_execution_map.json",
        "machine/ai_p3_native_training_task_backlog.json",
        "machine/ai_p3_native_training_tranche.json",
        "machine/ai_p3_engineering_execution_map.json",
        "machine/ai_p3_engineering_closure.json",
        "machine/ai_master_plan.json",
    ):
        dst=tmp_path/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/rel,dst)
    return tmp_path

def test_rejects_scope_loss(tmp_path: Path) -> None:
    root=_fixture(tmp_path); path=root/"machine/ai_p3_native_training_execution_map.json"
    data=json.loads(path.read_text()); data["first_tranche"]["queued_volume_refs"].pop(); path.write_text(json.dumps(data))
    with pytest.raises(ValidationError,match="partition"):
        validate(root)

def test_rejects_duplicate_ownership(tmp_path: Path) -> None:
    root=_fixture(tmp_path); path=root/"machine/ai_p3_native_training_task_backlog.json"
    data=json.loads(path.read_text()); ref=data["tasks"][0]["primary_volume_refs"][0]
    data["tasks"][1]["primary_volume_refs"].append(ref); data["tasks"][1]["masterplan_obligations"].append(data["tasks"][0]["masterplan_obligations"][0]); path.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        validate(root)

def test_rejects_self_promotion(tmp_path: Path) -> None:
    root=_fixture(tmp_path); path=root/"machine/ai_p3_native_training_task_backlog.json"
    data=json.loads(path.read_text()); data["tasks"][0]["completion_checkbox"]=True; path.write_text(json.dumps(data))
    with pytest.raises(ValidationError,match="self-promote"):
        validate(root)
