"""Cold-restore failure isolation for a completed consumer game.

A malformed portable backup must never create a destination slot or damage
an already earned ending. This exercises the public SlotStore boundary.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_acceptance import run_acceptance
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError
from skeleton.game.gameplay.ridge_rescue.consumer_backup import BackupError
from skeleton.game.gameplay.ridge_rescue.custody import canonical, digest


def test_tampered_terminal_backup_cannot_publish_restored_slot(tmp_path: Path):
    root = tmp_path / "saves"
    accepted = run_acceptance(root)
    store = SlotStore(root)
    original = store.load("interactive-acceptance")
    backup_path = store.backup("interactive-acceptance")
    valid = json.loads(backup_path.read_text(encoding="utf-8"))
    cases = []

    changed_head = json.loads(json.dumps(valid))
    changed_head["payload"]["history"][-1]["next_head"] = "0" * 64
    changed_head["sha256"] = digest(changed_head["payload"])
    cases.append(changed_head)

    truncated = json.loads(json.dumps(valid))
    truncated["payload"]["history"].pop()
    truncated["sha256"] = digest(truncated["payload"])
    cases.append(truncated)

    changed_source = json.loads(json.dumps(valid))
    changed_source["payload"]["source_sha256"] = "f" * 64
    changed_source["sha256"] = digest(changed_source["payload"])
    cases.append(changed_source)

    for index, tampered in enumerate(cases):
        destination = f"rejected-restore-{index}"
        with pytest.raises((BackupError, StoreError, ValueError)):
            store.restore_backup(destination, canonical(tampered))
        with pytest.raises(StoreError, match="does not exist"):
            store.load(destination)
        unchanged = store.load("interactive-acceptance")
        assert unchanged["head"] == original["head"] == accepted["head"]
        assert unchanged["revision"] == original["revision"]
        assert store.audit("interactive-acceptance")["verified"] is True


def test_valid_backup_replays_to_separate_slot_without_overwrite(tmp_path: Path):
    root = tmp_path / "saves"
    accepted = run_acceptance(root)
    store = SlotStore(root)
    backup = store.backup("interactive-acceptance").read_bytes()
    restored = store.restore_backup("independent-recovery", backup)
    assert restored["status"] == "completed"
    assert restored["head"] == accepted["head"]
    assert restored["revision"] == accepted["saved_revision"]
    assert store.audit("independent-recovery")["verified"] is True
    with pytest.raises(StoreError, match="already exists"):
        store.restore_backup("independent-recovery", backup)
    assert store.audit("independent-recovery")["verified"] is True
