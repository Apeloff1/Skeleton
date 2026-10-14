from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.ai.assistant.turn_ownership import (
    TurnLeaseExpired,
    TurnLeasePolicy,
    TurnLeaseToken,
    TurnOwnershipError,
    TurnOwnershipReceipt,
)


NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def _lease(**overrides):
    values = {
        "operation_id": "operation-1",
        "tenant_id": "tenant-a",
        "owner_id": "owner-a",
        "holder_id": "worker-a",
        "epoch": 7,
        "heartbeat_sequence": 2,
        "granted_at": NOW,
        "expires_at": NOW + timedelta(seconds=45),
        "previous_lease_digest": "a" * 64,
    }
    values.update(overrides)
    return TurnLeaseToken(**values)


def test_lease_digest_binds_identity_fence_and_expiry() -> None:
    lease = _lease()
    assert len(lease.digest) == 64
    assert lease.is_live(NOW + timedelta(seconds=44))
    lease.require_live(NOW + timedelta(seconds=44))
    with pytest.raises(TurnLeaseExpired):
        lease.require_live(NOW + timedelta(seconds=45))

    changed = _lease(epoch=8)
    assert changed.digest != lease.digest
    assert changed.same_fence(lease) is False


def test_same_fence_ignores_heartbeat_refresh_but_not_holder_or_epoch() -> None:
    lease = _lease()
    renewed = _lease(
        heartbeat_sequence=3,
        expires_at=NOW + timedelta(seconds=90),
    )
    assert lease.same_fence(renewed) is True
    assert lease.same_fence(_lease(holder_id="worker-b")) is False
    assert lease.same_fence(_lease(epoch=8)) is False


def test_policy_fails_closed_on_unbounded_or_tiny_ttl() -> None:
    policy = TurnLeasePolicy(
        default_ttl_seconds=30,
        max_ttl_seconds=120,
        minimum_renewal_seconds=5,
    )
    assert policy.clamp_ttl(None) == 30
    assert policy.clamp_ttl(60) == 60
    with pytest.raises(TurnOwnershipError, match="exceeds maximum"):
        policy.clamp_ttl(121)
    with pytest.raises(TurnOwnershipError, match="below minimum"):
        policy.clamp_ttl(1)


def test_receipt_digest_chains_ownership_mutations() -> None:
    lease = _lease()
    acquired = TurnOwnershipReceipt(
        operation_id=lease.operation_id,
        action="acquire",
        epoch=lease.epoch,
        holder_id=lease.holder_id,
        observed_at=NOW,
        lease_digest=lease.digest,
    )
    renewed = TurnOwnershipReceipt(
        operation_id=lease.operation_id,
        action="renew",
        epoch=lease.epoch,
        holder_id=lease.holder_id,
        observed_at=NOW + timedelta(seconds=10),
        lease_digest=_lease(
            heartbeat_sequence=3,
            expires_at=NOW + timedelta(seconds=90),
        ).digest,
        previous_receipt_digest=acquired.digest,
    )
    assert len(acquired.digest) == 64
    assert len(renewed.digest) == 64
    assert renewed.digest != acquired.digest
    assert renewed.previous_receipt_digest == acquired.digest
