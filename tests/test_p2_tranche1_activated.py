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
    with pytest.raises(Exception, match="lacks an Actions acceptance run"):
        validate(root)


def _task_fixture(tmp_path: Path, task_id: str) -> tuple[Path, dict, dict]:
    root = _fixture(tmp_path)
    path = root / "machine/ai_p2_task_backlog.json"
    backlog = json.loads(path.read_text(encoding="utf-8"))
    task = next(x for x in backlog["tasks"] if x["task_id"] == task_id)
    return root, backlog, task


def test_signed_native_and_functional_tasks_have_independent_evidence() -> None:
    receipt = validate(ROOT)
    assert receipt["status"] == "valid"


def test_pending_unsigned_t1_may_be_activated_without_completion(tmp_path: Path) -> None:
    root, backlog, task = _task_fixture(tmp_path, "P2-T1-FUNCTIONAL-01")
    task.update(
        status="landed_unpromoted",
        completion_checkbox=False,
        completion_checkbox_mark="[ ]",
        implementation_signed=False,
        verification_signed=False,
    )
    (root / "machine/ai_p2_task_backlog.json").write_text(json.dumps(backlog), encoding="utf-8")
    assert validate(root)["status"] == "valid"


@pytest.mark.parametrize("field", ["completion_checkbox", "implementation_signed", "verification_signed"])
def test_closed_t1_rejects_missing_required_signoff(tmp_path: Path, field: str) -> None:
    root, backlog, task = _task_fixture(tmp_path, "P2-T1-FUNCTIONAL-01")
    task[field] = False
    (root / "machine/ai_p2_task_backlog.json").write_text(json.dumps(backlog), encoding="utf-8")
    with pytest.raises(P2T1ActivationError, match="signoff is incomplete"):
        validate(root)


def test_closed_native_rejects_missing_merge_evidence(tmp_path: Path) -> None:
    root, backlog, task = _task_fixture(tmp_path, "P2-NATIVE-01")
    task["evidence_refs"] = [r for r in task["evidence_refs"] if not r.startswith("git:merge:")]
    (root / "machine/ai_p2_task_backlog.json").write_text(json.dumps(backlog), encoding="utf-8")
    with pytest.raises(P2T1ActivationError, match="immutable merge evidence"):
        validate(root)


def test_closed_t1_rejects_mismatched_acceptance_head(tmp_path: Path) -> None:
    root, backlog, task = _task_fixture(tmp_path, "P2-T1-FUNCTIONAL-01")
    task["evidence_refs"] = [
        r.replace("git-head:c6e966454b6ecb1b2a8d8fe51ce3f752c507f29f", "git-head:" + "0" * 40)
        for r in task["evidence_refs"]
    ]
    (root / "machine/ai_p2_task_backlog.json").write_text(json.dumps(backlog), encoding="utf-8")
    with pytest.raises(P2T1ActivationError, match="workflow head does not match"):
        validate(root)


def test_closed_t1_rejects_missing_action_run(tmp_path: Path) -> None:
    root, backlog, task = _task_fixture(tmp_path, "P2-T1-FUNCTIONAL-01")
    task["evidence_refs"] = [r for r in task["evidence_refs"] if not r.startswith("github-actions-run:")]
    (root / "machine/ai_p2_task_backlog.json").write_text(json.dumps(backlog), encoding="utf-8")
    with pytest.raises(P2T1ActivationError, match="Actions acceptance run"):
        validate(root)


def test_unpromoted_native_may_not_self_sign(tmp_path: Path) -> None:
    root, backlog, task = _task_fixture(tmp_path, "P2-NATIVE-01")
    task.update(status="landed_unpromoted", completion_checkbox=False, completion_checkbox_mark="[ ]",
                implementation_signed=False, verification_signed=True)
    (root / "machine/ai_p2_task_backlog.json").write_text(json.dumps(backlog), encoding="utf-8")
    with pytest.raises(P2T1ActivationError, match="may not self-sign"):
        validate(root)
