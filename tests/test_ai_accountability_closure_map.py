from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts.verify_ai_accountability_closure_map import (
    MAP,
    QUEUE,
    LEDGER,
    CONSTRUCTION,
    HANDOFF,
    CLOSURE,
    verify_repository,
)


ROOT = Path(__file__).resolve().parents[1]


def _copy_file(root: Path, source: Path) -> None:
    rel = source.relative_to(ROOT)
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_bridge_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for source in (MAP, QUEUE, LEDGER, CONSTRUCTION, HANDOFF, CLOSURE):
        _copy_file(root, source)

    mapping = json.loads((root / MAP.relative_to(ROOT)).read_text(encoding="utf-8"))
    for group in mapping["groups"]:
        workflow = ROOT / group["workflow"]
        _copy_file(root, workflow)
        verifier = group.get("verifier_script")
        if verifier:
            _copy_file(root, ROOT / verifier)
    return root


def test_live_accountability_closure_map_is_complete_and_exact_head() -> None:
    receipt = verify_repository(ROOT)

    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["task_count"] == 42
    assert receipt["mapped_task_count"] == 42
    assert receipt["group_count"] == 14
    assert sum(receipt["candidate_counts"].values()) == 42
    assert receipt["candidate_counts"]["done"] >= 1


def test_bridge_rejects_unmapped_queue_tasks(tmp_path: Path) -> None:
    root = _copy_bridge_tree(tmp_path)
    path = root / MAP.relative_to(ROOT)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["groups"] = [
        group for group in payload["groups"] if group["key"] != "S7-E2E"
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("unmapped queue tasks" in error for error in receipt["errors"])


def test_bridge_rejects_reopened_mapped_gap(tmp_path: Path) -> None:
    root = _copy_bridge_tree(tmp_path)
    path = root / CONSTRUCTION.relative_to(ROOT)
    payload = json.loads(path.read_text(encoding="utf-8"))
    gap = next(
        item
        for item in payload["gap_register"]
        if item["id"] == "gap-tool-runtime-convergence"
    )
    gap["status"] = "open"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "gap-tool-runtime-convergence is not closed" in error
        for error in receipt["errors"]
    )


def test_bridge_rejects_merge_ref_only_verification_gate(tmp_path: Path) -> None:
    root = _copy_bridge_tree(tmp_path)
    workflow = root / ".github/workflows/engine-container-boundary.yml"
    source = workflow.read_text(encoding="utf-8")
    source = source.replace(
        "          ref: ${{ github.event.pull_request.head.sha || github.sha }}\n",
        "",
    )
    workflow.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "engine-container-boundary.yml" in error
        and "exact PR head" in error
        for error in receipt["errors"]
    )


def test_bridge_rejects_missing_queue_accountability_record(
    tmp_path: Path,
) -> None:
    root = _copy_bridge_tree(tmp_path)
    path = root / LEDGER.relative_to(ROOT)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["records"] = [
        record
        for record in payload["records"]
        if record["id"] != "ACC-AIQ-S2-CTX-01"
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "AIQ-S2-CTX-01: missing ledger record" in error
        for error in receipt["errors"]
    )


def test_bridge_rejects_same_signer_without_independence_exception(
    tmp_path: Path,
) -> None:
    root = _copy_bridge_tree(tmp_path)
    path = root / LEDGER.relative_to(ROOT)
    payload = json.loads(path.read_text(encoding="utf-8"))
    record = next(
        item
        for item in payload["records"]
        if item["id"] == "ACC-AIQ-S0-STATE-03"
    )
    record["verification_signoff"]["signer_id"] = record[
        "implementation_signoff"
    ]["signer_id"]
    record["independence_exception"] = None
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "same-signer verification lacks exception" in error
        for error in receipt["errors"]
    )
