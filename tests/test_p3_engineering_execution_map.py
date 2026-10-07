from __future__ import annotations
import json, shutil
from pathlib import Path
import pytest
from scripts.check_p3_engineering_execution_map import P3EngineeringValidationError, validate
ROOT=Path(__file__).resolve().parents[1]
FILES=("machine/ai_master_plan.json","machine/ai_p3_execution_map.json","machine/ai_p3_expansion_closure.json","machine/ai_p3_engineering_execution_map.json","machine/ai_p3_engineering_task_backlog.json")

def _fixture(tmp_path:Path)->Path:
    for rel in FILES:
        dst=tmp_path/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/rel,dst)
    return tmp_path

def test_current_extension_is_valid():
    result=validate(ROOT); assert result["source_volume_count"]==234; assert result["scheduled_volume_count"]==37; assert result["queued_volume_count"]==197

def test_rejects_reownership(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_p3_engineering_execution_map.json"; payload=json.loads(path.read_text())
    payload["first_tranche"]["scheduled_volume_refs"].append("VOL-098")
    path.write_text(json.dumps(payload))
    with pytest.raises(P3EngineeringValidationError): validate(root)

def test_rejects_queue_loss(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_p3_engineering_execution_map.json"; payload=json.loads(path.read_text())
    payload["first_tranche"]["queued_volume_refs"].pop(); payload["first_tranche"]["queued_volume_count"]-=1; path.write_text(json.dumps(payload))
    with pytest.raises(P3EngineeringValidationError): validate(root)

def test_rejects_self_signoff(tmp_path:Path):
    root=_fixture(tmp_path); path=root/"machine/ai_p3_engineering_task_backlog.json"; payload=json.loads(path.read_text())
    payload["tasks"][0]["verification_signed"]=True; path.write_text(json.dumps(payload))
    with pytest.raises(P3EngineeringValidationError,match="self-complete or self-sign"): validate(root)
