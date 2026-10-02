from __future__ import annotations
import json
import shutil
from pathlib import Path
import pytest
from scripts.check_p3_native_training_closure import ClosureError, validate

ROOT=Path(__file__).resolve().parents[1]

def test_current_native_training_closure_is_valid() -> None:
    result=validate(ROOT)
    assert result=={
        "status":"closed","scheduled_volume_count":24,"queued_volume_count":173,
        "task_count":5,"provider_independent":True,
    }

def _fixture(tmp_path: Path) -> Path:
    for rel in (
        "machine/ai_p3_native_training_closure.json",
        "machine/ai_p3_native_training_execution_map.json",
        "machine/ai_p3_native_training_task_backlog.json",
        "machine/ai_p3_engineering_closure.json",
        "skeleton/ai/runtime/training/data.py",
        "skeleton/ai/runtime/training/native.py",
        "skeleton/ai/runtime/training/post_training.py",
        "skeleton/ai/runtime/training/lifecycle.py",
    ):
        dst=tmp_path/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/rel,dst)
    return tmp_path

def test_rejects_queue_erasure(tmp_path: Path) -> None:
    root=_fixture(tmp_path); path=root/"machine/ai_p3_native_training_closure.json"
    data=json.loads(path.read_text()); data["deferred_scope"]["queued_volume_refs"].pop(); path.write_text(json.dumps(data))
    with pytest.raises(ClosureError,match="deferred scope"):
        validate(root)

def test_rejects_task_self_sign(tmp_path: Path) -> None:
    root=_fixture(tmp_path); path=root/"machine/ai_p3_native_training_task_backlog.json"
    data=json.loads(path.read_text()); data["tasks"][0]["verification_signed"]=True; path.write_text(json.dumps(data))
    with pytest.raises(ClosureError,match="self-signed"):
        validate(root)
