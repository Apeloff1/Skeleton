from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from skeleton.persistence.spine_bind_checkpoint import (
    SpineBindCheckpoint,
    SpineBindCheckpointError,
)
from skeleton.persistence.spine_bind_checkpoint_chain import (
    SpineBindCheckpointChain,
    SpineBindCheckpointChainError,
)
from skeleton.persistence.spine_bind_checkpoint_replay import (
    SpineBindCheckpointReplay,
)
from skeleton.persistence.spine_bind_checkpoint_tenant import (
    SpineBindCheckpointTenant,
)


BASE = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
TENANT = "tenant-checkpoint"
SNAPSHOT = "d" * 64


def _recovery() -> dict[str, object]:
    import hashlib
    import json

    card: dict[str, object] = {
        "kind": "spine_bind_recovery",
        "hit": False,
        "law": "recovery-plan-does-not-activate",
        "citation": "VOL-134",
        "tenant_id": TENANT,
        "snapshot_digest": SNAPSHOT,
        "ready": False,
        "activated": False,
        "blockers": [
            "apply-not-landed",
            "provider-surface-unclaimed",
            "pr-automation-unclaimed",
            "ci-green-unread",
            "merge-unread",
            "motor-unwired",
            "dispatcher-unwired",
        ],
        "apply_landed": False,
        "live_motor": False,
        "dispatcher_running": False,
        "provider_surface_green": False,
        "pr_automation_green": False,
        "ci_green": False,
        "merged": False,
        "stored_prose": 0,
        "completion_checkbox": False,
        "implementation_signature": False,
        "verification_signature": False,
    }
    card["digest"] = hashlib.sha256(
        json.dumps(card, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return card


def test_checkpoint_is_idempotent_tenant_isolated_and_replay_safe(
    tmp_path: Path,
) -> None:
    path = tmp_path / "checkpoint.sqlite"
    journal = SpineBindCheckpoint(path)
    first = journal.append(_recovery(), now=BASE)
    second = journal.append(_recovery(), now=BASE)

    assert first["inserted"] is True
    assert second["inserted"] is False
    assert journal.count(TENANT) == 1
    assert first["recovery_digest"] == second["recovery_digest"]
    assert first["activated"] is False

    replay = SpineBindCheckpointReplay(path).replay(first)
    assert replay["rows_before"] == 1
    assert replay["rows_after"] == 1
    assert replay["inserted"] is False

    own = SpineBindCheckpointTenant(path).card(TENANT)
    foreign = SpineBindCheckpointTenant(path).card("tenant-foreign")
    assert own["count"] == 1
    assert own["foreign"] == 0
    assert foreign["count"] == 0
    assert foreign["digests"] == []

    chain = SpineBindCheckpointChain(path).seal(TENANT)
    assert chain["rows"] == 1
    assert len(chain["digest"]) == 64
    assert chain["activated"] is False

    journal.close()


def test_checkpoint_refuses_rewrite(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.sqlite"
    journal = SpineBindCheckpoint(path)
    journal.append(_recovery(), now=BASE)

    changed = _recovery()
    changed["blockers"] = ["different"]
    import hashlib
    import json

    changed["digest"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in changed.items() if key != "digest"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with pytest.raises(SpineBindCheckpointError, match="checkpoint rewrite"):
        journal.append(changed, now=BASE)


def test_checkpoint_chain_fails_closed_on_promoted_row(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.sqlite"
    journal = SpineBindCheckpoint(path)
    journal.append(_recovery(), now=BASE)
    journal._connection.execute(
        "UPDATE spine_bind_checkpoint SET ci_green = 1 WHERE tenant_id = ?",
        (TENANT,),
    )
    journal._connection.commit()

    with pytest.raises(SpineBindCheckpointChainError, match="not dark"):
        SpineBindCheckpointChain(path).seal(TENANT)
