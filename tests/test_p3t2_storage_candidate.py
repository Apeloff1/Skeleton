from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts.check_p3t2_storage_candidate import StorageCandidateError, validate

ROOT=Path(__file__).resolve().parents[1]
FILES=(
    "machine/ai_masterplan_continuation_frontier.json",
    "machine/ai_master_plan.json",
    "machine/ai_file_tree.json",
    "machine/ai_p3t2_storage_candidate.json",
    "skeleton/storage/__init__.py",
    "skeleton/storage/cas/__init__.py",
    "skeleton/ai/runtime/storage/__init__.py",
    "skeleton/ai/runtime/storage/cas/__init__.py",
    "skeleton/testing/test_distributed_transactions.py",
    "skeleton/testing/test_cache_architecture.py",
    "skeleton/testing/test_content_addressing.py",
)

def _fixture(tmp_path:Path)->Path:
    for rel in FILES:
        dst=tmp_path/rel
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/rel,dst)
    return tmp_path

def _load(path:Path)->dict:
    return json.loads(path.read_text(encoding="utf-8"))

def _store(path:Path,payload:dict)->None:
    path.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")

def test_current_storage_candidate_is_valid():
    result=validate(ROOT,head="a"*40)
    assert result["volume_refs"]==["VOL-133","VOL-135","VOL-136"]
    assert result["executable_test_count"]==3
    assert result["completion_checkbox"] is False

def test_rejects_storage_self_closure(tmp_path:Path):
    root=_fixture(tmp_path)
    path=root/"machine/ai_p3t2_storage_candidate.json"
    payload=_load(path)
    payload["promotion_state"]["completion_checkbox"]=True
    _store(path,payload)
    with pytest.raises(StorageCandidateError,match="illegally promoted completion_checkbox"):
        validate(root)

def test_rejects_owner_volume_escape(tmp_path:Path):
    root=_fixture(tmp_path)
    path=root/"machine/ai_p3t2_storage_candidate.json"
    payload=_load(path)
    payload["volume_refs"][-1]="VOL-137"
    _store(path,payload)
    with pytest.raises(StorageCandidateError,match="candidate volume ownership drift"):
        validate(root)

def test_rejects_planned_label_on_executable_test(tmp_path:Path):
    root=_fixture(tmp_path)
    path=root/"machine/ai_master_plan.json"
    payload=_load(path)
    volume=next(v for v in payload["volumes"] if v["key"]=="VOL-133")
    actual="skeleton/testing/test_distributed_transactions.py"
    volume["tests"]=[f"planned:{actual}" if x==actual else x for x in volume["tests"]]
    _store(path,payload)
    with pytest.raises(StorageCandidateError,match="missing executable storage regression|still labels executable regression"):
        validate(root)

def test_rejects_mirror_drift(tmp_path:Path):
    root=_fixture(tmp_path)
    path=root/"skeleton/ai/runtime/storage/cas/__init__.py"
    path.write_text(path.read_text(encoding="utf-8")+"\n# drift\n",encoding="utf-8")
    with pytest.raises(StorageCandidateError,match="storage mirror parity drift"):
        validate(root)

def test_rejects_invalid_reported_head():
    with pytest.raises(StorageCandidateError,match="reported exact head"):
        validate(ROOT,head="not-a-sha")
