from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from skeleton.persistence.spine_bind_bundle import SpineBindBundle
from skeleton.persistence.spine_bind_bundle_verify import (
    SpineBindBundleVerify,
    SpineBindBundleVerifyError,
)
from skeleton.persistence.spine_bind_checkpoint import SpineBindCheckpoint
from skeleton.persistence.spine_bind_checkpoint_chain import SpineBindCheckpointChain
from skeleton.persistence.spine_bind_checkpoint_replay import SpineBindCheckpointReplay
from skeleton.persistence.spine_bind_checkpoint_tenant import SpineBindCheckpointTenant
from skeleton.persistence.spine_bind_recovery import SpineBindRecovery
from skeleton.persistence.spine_bind_snapshot import SpineBindSnapshot


BASE = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
TENANT = "tenant-bundle"


def _snapshot() -> dict[str, object]:
    return SpineBindSnapshot().card(
        tenant_id=TENANT,
        bind={
            "kind": "spine_bind_card",
            "tenant_id": TENANT,
            "digest": "a" * 64,
            "moved": False,
            "epoch_before": 3,
            "epoch_after": 3,
            "apply_landed": False,
        },
        chain={
            "kind": "spine_bind_chain",
            "tenant_id": TENANT,
            "digest": "b" * 64,
            "rewritten": False,
            "merged": False,
        },
        gap={
            "kind": "spine_bind_gap",
            "tenant_id": TENANT,
            "missing": [2],
            "seen": [1, 3],
            "filled": False,
            "green": False,
        },
        surface={
            "kind": "spine_bind_surface",
            "tenant_id": TENANT,
            "provider_claimed": 0,
            "pr_claimed": 0,
            "green": False,
            "merged": False,
        },
    )


def test_bundle_verifies_without_becoming_activation_authority(
    tmp_path: Path,
) -> None:
    path = tmp_path / "checkpoint.sqlite"
    recovery = SpineBindRecovery().plan(_snapshot())
    journal = SpineBindCheckpoint(path)
    checkpoint = journal.append(recovery, now=BASE)

    bundle = SpineBindBundle().card(
        checkpoint=checkpoint,
        replay=SpineBindCheckpointReplay(path).replay(checkpoint),
        tenant=SpineBindCheckpointTenant(path).card(TENANT),
        chain=SpineBindCheckpointChain(path).seal(TENANT),
    )
    verified = SpineBindBundleVerify().verify(bundle)

    assert bundle["hit"] is False
    assert bundle["activated"] is False
    assert bundle["apply_landed"] is False
    assert bundle["ci_green"] is False
    assert bundle["merged"] is False
    assert verified["verified"] is True
    assert verified["activated"] is False
    assert verified["completion_checkbox"] is False


def test_bundle_verifier_rejects_digest_tamper(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.sqlite"
    recovery = SpineBindRecovery().plan(_snapshot())
    checkpoint = SpineBindCheckpoint(path).append(recovery, now=BASE)
    bundle = SpineBindBundle().card(
        checkpoint=checkpoint,
        replay=SpineBindCheckpointReplay(path).replay(checkpoint),
        tenant=SpineBindCheckpointTenant(path).card(TENANT),
        chain=SpineBindCheckpointChain(path).seal(TENANT),
    )
    tampered = copy.deepcopy(bundle)
    tampered["ci_green"] = True

    with pytest.raises(SpineBindBundleVerifyError, match="digest mismatch"):
        SpineBindBundleVerify().verify(tampered)
