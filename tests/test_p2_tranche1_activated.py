from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.check_p2_tranche1_activated import P2T1ActivationError, validate


ROOT = Path(__file__).resolve().parents[1]


def test_current_t1_activation_is_canonical() -> None:
    result = validate(ROOT)
    assert result["status"] == "valid"
    assert result["scheduled_volume_count"] == 57
    assert result["queued_volume_count"] == 257
    assert result["functional_ai_task"] == "P2-T1-FUNCTIONAL-01"


def _fixture(tmp_path: Path) -> Path:
    for rel in (
        "machine/ai_p2_tranche1_plan.json",
        "machine/ai_p2_execution_map.json",
        "machine/ai_p2_task_backlog.json",
        "machine/ai_master_plan.json",
        "machine/ai_master_build_sequence.json",
        "machine/ai_p1_execution_map.json",
        "scripts/check_p2_execution_map.py",
    ):
        src = ROOT / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return tmp_path


def test_rejects_functional_ai_ownership_loss(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_p2_task_backlog.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    task = next(x for x in payload["tasks"] if x["task_id"] == "P2-T1-FUNCTIONAL-01")
    task["primary_volume_refs"].remove("VOL-104")
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(Exception):
        validate(root)


def test_rejects_native_evidence_regression(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_p2_task_backlog.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    task = next(x for x in payload["tasks"] if x["task_id"] == "P2-NATIVE-01")
    task["evidence_refs"] = ["github:pr#2332"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(Exception, match="requires at least three evidence refs|missing evidence prefix"):
        validate(root)
