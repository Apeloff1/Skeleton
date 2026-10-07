from __future__ import annotations

import copy

import pytest

from skeleton.persistence.spine_bind_recovery import (
    SpineBindRecovery,
    SpineBindRecoveryError,
)
from skeleton.persistence.spine_bind_snapshot import (
    SpineBindSnapshot,
    SpineBindSnapshotError,
)


TENANT = "tenant-bind-snapshot"
HEX_A = "a" * 64
HEX_B = "b" * 64


def _bind() -> dict[str, object]:
    return {
        "kind": "spine_bind_card",
        "tenant_id": TENANT,
        "digest": HEX_A,
        "moved": False,
        "epoch_before": 7,
        "epoch_after": 7,
        "apply_landed": False,
    }


def _chain() -> dict[str, object]:
    return {
        "kind": "spine_bind_chain",
        "tenant_id": TENANT,
        "digest": HEX_B,
        "rewritten": False,
        "merged": False,
    }


def _gap() -> dict[str, object]:
    return {
        "kind": "spine_bind_gap",
        "tenant_id": TENANT,
        "missing": [2, 4],
        "seen": [1, 3],
        "filled": False,
        "green": False,
    }


def _surface() -> dict[str, object]:
    return {
        "kind": "spine_bind_surface",
        "tenant_id": TENANT,
        "provider_claimed": 0,
        "pr_claimed": 0,
        "green": False,
        "merged": False,
    }


def test_snapshot_and_recovery_remain_dark_and_deterministic() -> None:
    snapshotter = SpineBindSnapshot()
    first = snapshotter.card(
        tenant_id=TENANT,
        bind=_bind(),
        chain=_chain(),
        gap=_gap(),
        surface=_surface(),
    )
    second = snapshotter.card(
        tenant_id=TENANT,
        bind=_bind(),
        chain=_chain(),
        gap=_gap(),
        surface=_surface(),
    )

    assert first == second
    assert first["digest"] == second["digest"]
    assert first["activated"] is False
    assert first["gap_filled"] is False
    assert first["completion_checkbox"] is False

    recovery = SpineBindRecovery().plan(first)
    assert recovery["ready"] is False
    assert recovery["activated"] is False
    assert recovery["apply_landed"] is False
    assert recovery["provider_surface_green"] is False
    assert recovery["pr_automation_green"] is False
    assert recovery["ci_green"] is False
    assert recovery["merged"] is False
    assert recovery["blockers"] == [
        "apply-not-landed",
        "provider-surface-unclaimed",
        "pr-automation-unclaimed",
        "ci-green-unread",
        "merge-unread",
        "motor-unwired",
        "dispatcher-unwired",
    ]


def test_snapshot_refuses_claimed_surface() -> None:
    surface = _surface()
    surface["provider_claimed"] = True

    with pytest.raises(SpineBindSnapshotError, match="surface is claimed"):
        SpineBindSnapshot().card(
            tenant_id=TENANT,
            bind=_bind(),
            chain=_chain(),
            gap=_gap(),
            surface=surface,
        )


def test_recovery_refuses_promoted_snapshot() -> None:
    snapshot = SpineBindSnapshot().card(
        tenant_id=TENANT,
        bind=_bind(),
        chain=_chain(),
        gap=_gap(),
        surface=_surface(),
    )
    promoted = copy.deepcopy(snapshot)
    promoted["ci_green"] = True

    with pytest.raises(SpineBindRecoveryError, match="snapshot is not dark"):
        SpineBindRecovery().plan(promoted)
