from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_ai_p0_accountability_terminal import verify_terminal


HEAD = "a" * 40


def _write(root: Path, rel: str, payload: dict) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _fixture(root: Path) -> tuple[Path, Path]:
    groups = []
    tasks = []
    records = []
    results = []
    for group_index in range(14):
        key = f"G{group_index:02d}"
        prefix = f"AIQ-G{group_index:02d}-"
        gap_id = f"gap-{group_index:02d}"
        verifier_script = f"scripts/verify_{key.lower()}.py"
        verifier_digest = f"{group_index + 101:064x}"
        groups.append(
            {
                "key": key,
                "task_prefix": prefix,
                "gap_id": gap_id,
                "verifier_script": verifier_script,
                "expected_receipt_verifier": "fixture-verifier-v1",
                "expected_script_sha256": verifier_digest,
            }
        )
        results.append(
            {
                "key": key,
                "gap_id": gap_id,
                "passed": True,
                "receipt_verifier": "fixture-verifier-v1",
                "receipt_head_sha": HEAD,
                "receipt_digest": f"{group_index + 1:064x}",
                "script_digest": verifier_digest,
            }
        )
        for task_index in range(3):
            task_id = f"{prefix}{task_index + 1:02d}"
            accountability_id = f"ACC-{task_id}"
            tasks.append(
                {
                    "task_id": task_id,
                    "accountability_id": accountability_id,
                    "status": "done",
                    "completion_checkbox": True,
                    "completion_checkbox_mark": "[x]",
                    "implementation_signed": True,
                    "verification_signed": True,
                }
            )
            records.append(
                {
                    "id": accountability_id,
                    "type": "queue_task",
                    "status": "done",
                    "checkbox": True,
                    "checkbox_mark": "[x]",
                    "completed_at_utc": "2026-10-02T18:28:50Z",
                    "implementation_signoff": {
                        "signed": True,
                        "signer_id": "agent:builder",
                    },
                    "verification_signoff": {
                        "signed": True,
                        "signer_id": "github-actions:AI Accountability Closure Bridge",
                        "signature_ref": "https://github.com/example/repo/actions/runs/123",
                        "evidence_refs": [verifier_script],
                    },
                    "evidence": [verifier_script, "machine/ai_accountability_closure_map.json"],
                    "history": [
                        {
                            "event_type": "completed",
                            "to_status": "done",
                        }
                    ],
                }
            )

    _write(root, "machine/ai_build_queue.json", {"tasks": tasks})
    _write(root, "machine/ai_build_accountability.json", {"records": records})
    _write(
        root,
        "machine/ai_accountability_closure_map.json",
        {
            "rules": {"queue_task_count": 42, "tasks_per_group": 3},
            "groups": groups,
        },
    )
    runner = _write(
        root,
        "runner.json",
        {
            "verifier": "ai-accountability-verifier-runner-v1",
            "head_sha": HEAD,
            "valid": True,
            "failures": [],
            "verifier_count": 14,
            "passed_count": 14,
            "results": results,
        },
    )
    bridge = _write(
        root,
        "bridge.json",
        {
            "verifier": "ai-accountability-closure-map-v1",
            "head_sha": HEAD,
            "valid": True,
            "errors": [],
            "task_count": 42,
            "mapped_task_count": 42,
            "group_count": 14,
            "candidate_counts": {
                "implementation_ready": 0,
                "verification_ready": 0,
                "completion_ready": 0,
                "done": 42,
            },
        },
    )
    return runner, bridge


def test_terminal_verifier_accepts_strict_42_of_42_fixture(tmp_path: Path) -> None:
    runner, bridge = _fixture(tmp_path)

    receipt = verify_terminal(
        tmp_path,
        head_sha=HEAD,
        verifier_receipt=runner,
        closure_map_receipt=bridge,
    )

    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["terminal_task_count"] == 42
    assert receipt["fresh_verifier_pass_count"] == 14
    assert receipt["bridge_signed_task_count"] == 42


def test_terminal_verifier_rejects_queue_reopen(tmp_path: Path) -> None:
    runner, bridge = _fixture(tmp_path)
    path = tmp_path / "machine/ai_build_queue.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tasks"][0]["status"] = "pending"
    payload["tasks"][0]["completion_checkbox"] = False
    payload["tasks"][0]["completion_checkbox_mark"] = "[ ]"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_terminal(
        tmp_path,
        head_sha=HEAD,
        verifier_receipt=runner,
        closure_map_receipt=bridge,
    )

    assert receipt["valid"] is False
    assert any("queue status is not done" in error for error in receipt["errors"])
    assert receipt["terminal_task_count"] == 41


def test_terminal_verifier_rejects_stale_fresh_verifier_receipt(tmp_path: Path) -> None:
    runner, bridge = _fixture(tmp_path)
    payload = json.loads(runner.read_text(encoding="utf-8"))
    payload["head_sha"] = "b" * 40
    runner.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_terminal(
        tmp_path,
        head_sha=HEAD,
        verifier_receipt=runner,
        closure_map_receipt=bridge,
    )

    assert receipt["valid"] is False
    assert "verifier-runner receipt is not exact-head" in receipt["errors"]


def test_terminal_verifier_rejects_nonterminal_bridge_candidate_counts(
    tmp_path: Path,
) -> None:
    runner, bridge = _fixture(tmp_path)
    payload = json.loads(bridge.read_text(encoding="utf-8"))
    payload["candidate_counts"] = {
        "implementation_ready": 1,
        "verification_ready": 0,
        "completion_ready": 0,
        "done": 41,
    }
    bridge.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_terminal(
        tmp_path,
        head_sha=HEAD,
        verifier_receipt=runner,
        closure_map_receipt=bridge,
    )

    assert receipt["valid"] is False
    assert "closure-map receipt is not terminal 42/42 done" in receipt["errors"]


def test_terminal_verifier_rejects_bridge_signoff_without_mapped_verifier(
    tmp_path: Path,
) -> None:
    runner, bridge = _fixture(tmp_path)
    path = tmp_path / "machine/ai_build_accountability.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["records"][0]["verification_signoff"]["evidence_refs"] = []
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_terminal(
        tmp_path,
        head_sha=HEAD,
        verifier_receipt=runner,
        closure_map_receipt=bridge,
    )

    assert receipt["valid"] is False
    assert any(
        "bridge signoff does not bind mapped verifier" in error
        for error in receipt["errors"]
    )


def test_terminal_verifier_rejects_fresh_verifier_identity_drift(
    tmp_path: Path,
) -> None:
    runner, bridge = _fixture(tmp_path)
    payload = json.loads(runner.read_text(encoding="utf-8"))
    payload["results"][0]["receipt_verifier"] = "wrong-verifier-v1"
    runner.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_terminal(
        tmp_path,
        head_sha=HEAD,
        verifier_receipt=runner,
        closure_map_receipt=bridge,
    )

    assert receipt["valid"] is False
    assert any(
        "fresh verifier receipt identity mismatch" in error
        for error in receipt["errors"]
    )


def test_terminal_verifier_rejects_fresh_verifier_script_digest_drift(
    tmp_path: Path,
) -> None:
    runner, bridge = _fixture(tmp_path)
    payload = json.loads(runner.read_text(encoding="utf-8"))
    payload["results"][0]["script_digest"] = "f" * 64
    runner.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_terminal(
        tmp_path,
        head_sha=HEAD,
        verifier_receipt=runner,
        closure_map_receipt=bridge,
    )

    assert receipt["valid"] is False
    assert any(
        "fresh verifier script digest mismatch" in error
        for error in receipt["errors"]
    )
