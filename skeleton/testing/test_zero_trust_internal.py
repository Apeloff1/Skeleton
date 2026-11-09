from __future__ import annotations

import hashlib
import hmac

import pytest

from skeleton.ai.runtime.security import zero_trust as mirror
from skeleton.security.zero_trust import (
    IdentityProof,
    InternalGrant,
    TrustDecision,
    TrustError,
    WorkloadIdentity,
    authorize,
    binding_payload,
    revalidate,
)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Key:
    def __init__(self, key_id: str, secret: bytes) -> None:
        self.key_id = key_id
        self._secret = secret

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

    def verify(self, payload: bytes, signature: str) -> bool:
        if not isinstance(payload, bytes) or not isinstance(signature, str):
            return False
        expected = self.sign(payload)
        if len(expected) != len(signature):
            return False
        return hmac.compare_digest(expected, signature)


ROOT = Key("KEY.ROOT", b"root-secret")
IDENTITY = WorkloadIdentity("WORKLOAD.API", "INSTANCE.1", sha("attest"))
GRANT = InternalGrant(
    "GRANT.1",
    "WORKLOAD.API",
    "INSTANCE.1",
    IDENTITY.attestation_digest,
    frozenset({"read", "write"}),
    "tenant/a/",
    0,
    100,
)


def proof_for(
    identity: WorkloadIdentity,
    grant: InternalGrant,
    key: Key = ROOT,
) -> IdentityProof:
    return IdentityProof(key.key_id, key.sign(binding_payload(identity, grant)))


def decide(
    identity: WorkloadIdentity,
    grant: InternalGrant,
    action: str,
    resource: str,
    now: int,
    interval: int = 10,
    *,
    proof: IdentityProof | None = None,
    verifier: Key | object = ROOT,
) -> TrustDecision:
    return authorize(
        identity,
        grant,
        action,
        resource,
        now,
        interval,
        proof=proof_for(identity, grant) if proof is None else proof,
        verifier=verifier,
    )


def test_exact_workload_identity_and_least_privilege_grant() -> None:
    decision = decide(IDENTITY, GRANT, "read", "tenant/a/item", 10)
    assert decision.allowed
    assert decision.action == "read"
    assert decision.resource == "tenant/a/item"


def test_instance_identity_cannot_be_replayed() -> None:
    other = WorkloadIdentity("WORKLOAD.API", "INSTANCE.2", sha("attest2"))
    other_grant = InternalGrant(
        "GRANT.1",
        "WORKLOAD.API",
        "INSTANCE.1",
        IDENTITY.attestation_digest,
        frozenset({"read", "write"}),
        "tenant/a/",
        0,
        100,
    )
    denied = decide(other, other_grant, "read", "tenant/a/item", 10)
    assert not denied.allowed
    assert denied.reason == "identity_mismatch"


def test_action_and_resource_scope_fail_closed() -> None:
    assert not decide(IDENTITY, GRANT, "delete", "tenant/a/item", 10).allowed
    assert not decide(IDENTITY, GRANT, "read", "tenant/b/item", 10).allowed


def test_long_running_authority_has_revalidation_deadline() -> None:
    decision = decide(IDENTITY, GRANT, "read", "tenant/a/item", 10, interval=7)
    assert decision.revalidate_at == 17


def test_expired_grant_denied() -> None:
    assert not decide(IDENTITY, GRANT, "read", "tenant/a/item", 100).allowed


def test_revalidation_preserves_exact_action_and_resource() -> None:
    original = decide(IDENTITY, GRANT, "write", "tenant/a/item/42", 10)
    refreshed = revalidate(
        IDENTITY,
        GRANT,
        original,
        15,
        revalidation_interval=7,
        proof=proof_for(IDENTITY, GRANT),
        verifier=ROOT,
    )
    assert refreshed.allowed
    assert refreshed.action == "write"
    assert refreshed.resource == "tenant/a/item/42"
    assert refreshed.revalidate_at == 22


def test_revalidation_fails_closed_when_grant_scope_changes() -> None:
    original = decide(IDENTITY, GRANT, "write", "tenant/a/item", 10)
    reduced = InternalGrant(
        "GRANT.1",
        "WORKLOAD.API",
        "INSTANCE.1",
        IDENTITY.attestation_digest,
        frozenset({"read"}),
        "tenant/a/",
        0,
        100,
    )
    refreshed = revalidate(
        IDENTITY,
        reduced,
        original,
        15,
        proof=proof_for(IDENTITY, reduced),
        verifier=ROOT,
    )
    assert not refreshed.allowed
    assert refreshed.reason == "least_privilege_denied"
    assert refreshed.action is None
    assert refreshed.resource is None


def test_revalidation_rejects_different_grant_identity() -> None:
    original = decide(IDENTITY, GRANT, "read", "tenant/a/item", 10)
    replacement = InternalGrant(
        "GRANT.2",
        "WORKLOAD.API",
        "INSTANCE.1",
        IDENTITY.attestation_digest,
        frozenset({"read"}),
        "tenant/a/",
        0,
        100,
    )
    with pytest.raises(TrustError, match="invalid prior decision"):
        revalidate(
            IDENTITY,
            replacement,
            original,
            15,
            proof=proof_for(IDENTITY, replacement),
            verifier=ROOT,
        )


def test_denied_decision_cannot_smuggle_authority() -> None:
    with pytest.raises(TrustError, match="denied decision cannot carry authority"):
        TrustDecision(
            False,
            "denied",
            "GRANT.1",
            IDENTITY.attestation_digest,
            "read",
            "tenant/a/item",
            20,
        )


def test_boolean_ticks_and_unbounded_actions_are_rejected() -> None:
    with pytest.raises(TrustError, match="now must be bounded"):
        decide(IDENTITY, GRANT, "read", "tenant/a/item", True)  # type: ignore[arg-type]
    with pytest.raises(TrustError, match="grant action"):
        InternalGrant(
            "GRANT.2",
            "WORKLOAD.API",
            "INSTANCE.1",
            IDENTITY.attestation_digest,
            frozenset(f"action{i}" for i in range(257)),
            "tenant/a/",
            0,
            100,
        )


def test_resource_prefix_requires_path_boundary() -> None:
    scoped = InternalGrant(
        "GRANT.PATH",
        "WORKLOAD.API",
        "INSTANCE.1",
        IDENTITY.attestation_digest,
        frozenset({"read"}),
        "tenant/a",
        0,
        100,
    )
    assert decide(IDENTITY, scoped, "read", "tenant/a", 10).allowed
    assert decide(IDENTITY, scoped, "read", "tenant/a/item", 10).allowed
    denied = decide(IDENTITY, scoped, "read", "tenant/a-evil/item", 10)
    assert not denied.allowed
    assert denied.reason == "least_privilege_denied"


def test_rotated_attestation_cannot_reuse_existing_grant() -> None:
    rotated = WorkloadIdentity("WORKLOAD.API", "INSTANCE.1", sha("rotated-attestation"))
    denied = decide(rotated, GRANT, "read", "tenant/a/item", 10)
    assert not denied.allowed
    assert denied.reason == "attestation_mismatch"


def test_revalidation_detects_attestation_rotation() -> None:
    original = decide(IDENTITY, GRANT, "read", "tenant/a/item", 10)
    rotated = WorkloadIdentity("WORKLOAD.API", "INSTANCE.1", sha("rotated-attestation"))
    denied = revalidate(
        rotated,
        GRANT,
        original,
        15,
        proof=proof_for(rotated, GRANT),
        verifier=ROOT,
    )
    assert not denied.allowed
    assert denied.reason == "attestation_mismatch"
    assert denied.grant_id is None


def test_random_signature_is_unbound() -> None:
    bogus = IdentityProof("KEY.ROOT", "00" * 32)
    denied = decide(IDENTITY, GRANT, "read", "tenant/a/item", 10, proof=bogus)
    assert not denied.allowed
    assert denied.reason == "identity_unbound"
    assert denied.grant_id is None


def test_proof_for_another_grant_does_not_authorize_this_grant() -> None:
    wider = InternalGrant(
        "GRANT.WIDE",
        "WORKLOAD.API",
        "INSTANCE.1",
        IDENTITY.attestation_digest,
        frozenset({"read", "write", "admin"}),
        "tenant/a/",
        0,
        100,
    )
    stolen = proof_for(IDENTITY, GRANT)
    denied = decide(IDENTITY, wider, "admin", "tenant/a/item", 10, proof=stolen)
    assert not denied.allowed
    assert denied.reason == "identity_unbound"
    allowed = decide(IDENTITY, wider, "admin", "tenant/a/item", 10)
    assert allowed.allowed
    assert allowed.action == "admin"


def test_verifier_exception_fails_closed() -> None:
    class Boom:
        key_id = "KEY.ROOT"

        def verify(self, payload: bytes, signature: str) -> bool:
            raise RuntimeError("kms down")

    denied = decide(
        IDENTITY,
        GRANT,
        "read",
        "tenant/a/item",
        10,
        proof=proof_for(IDENTITY, GRANT),
        verifier=Boom(),
    )
    assert not denied.allowed
    assert denied.reason == "identity_verifier_failed"


def test_wrong_key_and_non_true_verifier_are_unbound() -> None:
    other = Key("KEY.OTHER", b"other-secret")
    foreign = proof_for(IDENTITY, GRANT, other)
    denied = decide(IDENTITY, GRANT, "read", "tenant/a/item", 10, proof=foreign)
    assert denied.reason == "identity_unbound"

    class Soft:
        key_id = "KEY.ROOT"

        def verify(self, payload: bytes, signature: str) -> str:
            return "yes"

    soft = decide(
        IDENTITY,
        GRANT,
        "read",
        "tenant/a/item",
        10,
        proof=proof_for(IDENTITY, GRANT),
        verifier=Soft(),
    )
    assert soft.reason == "identity_unbound"


def test_revalidation_rejects_a_proof_for_a_different_grant() -> None:
    original = decide(IDENTITY, GRANT, "read", "tenant/a/item", 10)
    other = InternalGrant(
        "GRANT.1",
        "WORKLOAD.API",
        "INSTANCE.1",
        IDENTITY.attestation_digest,
        frozenset({"read", "write"}),
        "tenant/b/",
        0,
        100,
    )
    denied = revalidate(
        IDENTITY,
        GRANT,
        original,
        15,
        proof=proof_for(IDENTITY, other),
        verifier=ROOT,
    )
    assert denied.reason == "identity_unbound"


def test_ai_mirror_binds_the_same_canonical_payload() -> None:
    mirrored_identity = mirror.WorkloadIdentity(
        IDENTITY.workload_id,
        IDENTITY.instance_id,
        IDENTITY.attestation_digest,
    )
    mirrored_grant = mirror.InternalGrant(
        GRANT.grant_id,
        GRANT.workload_id,
        GRANT.instance_id,
        GRANT.attestation_digest,
        GRANT.actions,
        GRANT.resource_prefix,
        GRANT.issued_tick,
        GRANT.expires_tick,
    )
    assert mirror.binding_payload(mirrored_identity, mirrored_grant) == binding_payload(
        IDENTITY, GRANT
    )
    payload = binding_payload(IDENTITY, GRANT)
    assert b'"kind":"internal_service_identity"' in payload
    decision = mirror.authorize(
        mirrored_identity,
        mirrored_grant,
        "read",
        "tenant/a/item",
        10,
        proof=mirror.IdentityProof(ROOT.key_id, ROOT.sign(payload)),
        verifier=ROOT,
    )
    assert decision.allowed
