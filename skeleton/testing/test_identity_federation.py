from __future__ import annotations

from skeleton.ai.runtime.deferred.deployment_operations_assurance import (
    FederatedPrincipal, evaluate_federated_session,
)

A="a"*64

def principal()->FederatedPrincipal:
    return FederatedPrincipal("issuer","external-sub","principal","tenant",("ops",),A)

def test_federated_session_requires_unexpired_exact_revocation_epoch()->None:
    active=evaluate_federated_session(
        principal(),session_id="s1",issued_at_ms=100,expires_at_ms=200,
        now_ms=150,revocation_epoch=7,observed_revocation_epoch=7,
    )
    assert active.active is True

    revoked=evaluate_federated_session(
        principal(),session_id="s2",issued_at_ms=100,expires_at_ms=200,
        now_ms=150,revocation_epoch=7,observed_revocation_epoch=8,
    )
    assert revoked.active is False

    stale=evaluate_federated_session(
        principal(),session_id="s3",issued_at_ms=100,expires_at_ms=200,
        now_ms=150,revocation_epoch=7,observed_revocation_epoch=6,
    )
    assert stale.active is False
