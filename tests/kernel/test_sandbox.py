"""Security regressions for kernel capability sandbox lifetimes."""

from __future__ import annotations

import math

import pytest

from skeleton.kernel.sandbox import Capability, Grant, Sandbox


def test_grant_expired_honors_explicit_zero_clock() -> None:
    grant = Grant(
        holder="worker",
        capability=Capability.FS_READ,
        scope="*",
        granted_at=0.0,
        expires_at=10.0,
    )

    assert grant.expired(now=0.0) is False
    assert grant.expired(now=10.0) is True


@pytest.mark.parametrize(
    "ttl",
    [0, 0.0, -1, True, False, math.nan, math.inf, -math.inf, "1"],
)
def test_invalid_ttls_are_rejected_without_grant_or_audit_mutation(ttl) -> None:
    sandbox = Sandbox()

    with pytest.raises(ValueError, match="ttl_seconds"):
        sandbox.grant("worker", Capability.NET_EGRESS, ttl_seconds=ttl)

    assert sandbox.grants_for("worker") == ()
    assert sandbox.audit_trail() == ()


def test_none_ttl_remains_explicit_permanent_grant() -> None:
    sandbox = Sandbox()

    grant = sandbox.grant("worker", Capability.FS_READ, ttl_seconds=None)

    assert grant.expires_at is None
    assert sandbox.can("worker", Capability.FS_READ) is True


def test_positive_ttl_is_normalized_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skeleton.kernel.sandbox.time.time", lambda: 100.0)
    sandbox = Sandbox()

    grant = sandbox.grant("worker", Capability.NET_EGRESS, ttl_seconds=2)

    assert grant.granted_at == 100.0
    assert grant.expires_at == 102.0
    assert grant.expired(now=101.999) is False
    assert grant.expired(now=102.0) is True
