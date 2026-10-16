"""Regression tests for the read-only, file-presence-only FLGB batch audit."""
from copy import deepcopy

import pytest

from scripts.reconcile_flgb_backlog_batch import as_markdown, reconcile

SHA = "a" * 40


def _fixture():
    tasks = []
    for i in (1, 2):
        tasks.append({
            "id": f"FLGB-01-T0{i}",
            "plane_id": "FLGB-01",
            "subsystem": f"item {i}",
            "implementation_target": f"app/item{i}.py",
            "contract_target": f"app/contracts/item{i}.json",
            "test_target": f"tests/test_item{i}.py",
            "state": "implemented-pending-verification",
            "implementation_signed": False,
            "independent_verification_signed": False,
        })
    manifest = {
        "task_count": 2,
        "plane_count": 1,
        "tasks": tasks,
        "planes": [{"id": "FLGB-01", "task_ids": [t["id"] for t in tasks]}],
    }
    tracked = {task[field] for task in tasks for field in (
        "implementation_target", "contract_target", "test_target",
    )}
    return manifest, tracked


def test_all_targets_present_still_does_not_sign_completion():
    manifest, tracked = _fixture()
    result = reconcile(manifest, tracked, SHA, count=2)
    assert result["all_three_files_present"] == 2
    assert result["missing_any_declared_target"] == 0
    assert result["all_tasks_independently_verified"] is False
    assert result["completion_claim"] is False
    assert "FLGB-01-T01" in as_markdown(result)
    assert all(i["review_result"] == "files-present-not-verified" for i in result["items"])


def test_missing_test_target_is_reported_not_silently_completed():
    manifest, tracked = _fixture()
    tracked.remove("tests/test_item2.py")
    result = reconcile(manifest, tracked, SHA, count=2)
    assert result["missing_any_declared_target"] == 1
    assert result["items"][1]["missing_target_types"] == ["test_target"]
    assert result["items"][1]["review_result"] == "missing-declared-files"


@pytest.mark.parametrize("mutation", ["duplicate_id", "unsafe_path", "unmapped", "wrong_count"])
def test_inconsistent_backlog_fails_closed(mutation):
    manifest, tracked = _fixture()
    manifest = deepcopy(manifest)
    if mutation == "duplicate_id":
        manifest["tasks"][1]["id"] = manifest["tasks"][0]["id"]
    elif mutation == "unsafe_path":
        manifest["tasks"][0]["contract_target"] = "../../secrets"
    elif mutation == "unmapped":
        manifest["tasks"][0]["plane_id"] = "FLGB-99"
    else:
        manifest["task_count"] = 3
    with pytest.raises(ValueError):
        reconcile(manifest, tracked, SHA, count=2)


def test_slice_boundaries_enforced_and_order_preserved():
    manifest, tracked = _fixture()
    result = reconcile(manifest, tracked, SHA, start=1, count=1)
    assert [i["id"] for i in result["items"]] == ["FLGB-01-T02"]
    with pytest.raises(ValueError):
        reconcile(manifest, tracked, SHA, start=1, count=2)
