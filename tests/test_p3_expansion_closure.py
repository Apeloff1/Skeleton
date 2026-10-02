from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.check_p3_expansion_closure import P3ClosureError, validate


ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "machine/ai_p3_expansion_closure.json",
    "machine/ai_p2_functional_ai_closure.json",
    "machine/ai_p3_execution_map.json",
    "machine/ai_p3_task_backlog.json",
)


def _fixture(tmp_path: Path) -> Path:
    for rel in FILES:
        src = ROOT / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return tmp_path


def test_current_p3_expansion_is_closure_ready() -> None:
    result = validate(ROOT)
    assert result["status"] == "valid"
    assert result["scheduled_volume_count"] == 23
    assert result["queued_volume_count"] == 234
    assert result["landed_task_count"] == 6


def test_rejects_false_full_scope_completion(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_p3_expansion_closure.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["deferred_scope"]["queued_volume_count"] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(P3ClosureError, match="preserve 234"):
        validate(root)


def test_rejects_task_self_signoff(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_p3_task_backlog.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tasks"][0]["verification_signed"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(P3ClosureError, match="self-complete or self-sign"):
        validate(root)


def test_closed_state_requires_closure_workflow_evidence(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_p3_expansion_closure.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "closed"
    payload["closure_evidence"] = ["github:pr#2347"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(P3ClosureError, match="exact-head closure evidence"):
        validate(root)
