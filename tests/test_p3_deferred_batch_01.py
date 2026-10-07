from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts.check_p3_deferred_batch_01 import (
    BATCH,
    MASTER,
    ROOT,
    SOURCE,
    DeferredBatchValidationError,
    validate,
)


def _repo(tmp_path: Path) -> Path:
    for relative in (BATCH, SOURCE, MASTER):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in (
        "skeleton/ai/runtime/extensions/multimodal.py",
        "skeleton/ai/runtime/extensions/ecosystem.py",
        "skeleton/testing/test_p3_deferred_multimodal_tools.py",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return tmp_path


def _mutate(root: Path, mutate) -> None:
    path = root / BATCH
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_p3_deferred_batch_01_is_consistent_with_frozen_source_queue() -> None:
    result = validate()
    assert result == {
        "status": "valid",
        "batch_id": "P3-DEFERRED-BATCH-01",
        "selected_volume_count": 11,
        "projected_remaining_volume_count": 167,
        "task_count": 4,
        "contract_count": 33,
    }


def test_deferred_batch_rejects_source_authority_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        lambda payload: payload["source"].__setitem__(
            "source_is_frozen",
            False,
        ),
    )

    with pytest.raises(
        DeferredBatchValidationError,
        match="source authority drift: source_is_frozen",
    ):
        validate(root)


def test_deferred_batch_rejects_duplicate_task_identity(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def duplicate(payload: dict) -> None:
        payload["tasks"].append(dict(payload["tasks"][0]))

    _mutate(root, duplicate)

    with pytest.raises(
        DeferredBatchValidationError,
        match="task IDs must be unique and non-empty",
    ):
        validate(root)


def test_deferred_batch_rejects_arbitrary_nonterminal_status(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)

    def drift(payload: dict) -> None:
        payload["tasks"][0]["status"] = "almost_done"

    _mutate(root, drift)

    with pytest.raises(
        DeferredBatchValidationError,
        match="status must remain implemented_pending_validation",
    ):
        validate(root)
