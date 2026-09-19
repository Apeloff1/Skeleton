"""Execution assurance and durable signed audit-anchor tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from skeleton.shells.ai.assurance import (
    AIExecutionAssuranceInspector,
    AIExecutionAssurancePolicy,
    AssuranceLevel,
)
from skeleton.shells.ai.audit_anchor import AIAuditAnchor, AIAuditAnchorStore
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.risk import RiskBand
from skeleton.shells.ai.signed_artifact import ArtifactSigner


def fp(char):
    return char * 64


def test_assurance_low_allows_standard_execution():
    decision = AIExecutionAssuranceInspector().inspect(
        RiskBand.LOW,
        sealed=False,
        sandbox_verified=False,
        backend_id="shell-service-host",
    )
    assert decision.allowed
    assert decision.required is AssuranceLevel.STANDARD


def test_assurance_medium_requires_seal():
    inspector = AIExecutionAssuranceInspector()
    denied = inspector.inspect(
        RiskBand.MEDIUM,
        sealed=False,
        sandbox_verified=False,
        backend_id="shell-service-host",
    )
    assert not denied.allowed
    assert denied.required is AssuranceLevel.SEALED
    allowed = inspector.inspect(
        RiskBand.MEDIUM,
        sealed=True,
        sandbox_verified=False,
        backend_id="shell-service-host",
    )
    assert allowed.allowed


def test_assurance_high_requires_seal_and_verified_sandbox():
    inspector = AIExecutionAssuranceInspector()
    no_seal = inspector.inspect(
        RiskBand.HIGH,
        sealed=False,
        sandbox_verified=True,
        backend_id="sandbox:real",
    )
    assert not no_seal.allowed
    no_sandbox = inspector.inspect(
        RiskBand.HIGH,
        sealed=True,
        sandbox_verified=False,
        backend_id="sandbox:spoofed",
    )
    assert not no_sandbox.allowed
    allowed = inspector.inspect(
        RiskBand.HIGH,
        sealed=True,
        sandbox_verified=True,
        backend_id="sandbox:real",
    )
    assert allowed.allowed
    assert allowed.sandboxed


def test_assurance_backend_name_cannot_spoof_sandbox_verification():
    decision = AIExecutionAssuranceInspector().inspect(
        RiskBand.HIGH,
        sealed=True,
        sandbox_verified=False,
        backend_id="sandbox:totally-real",
    )
    assert not decision.allowed
    assert any("verified sandbox" in reason for reason in decision.reasons)


def test_assurance_critical_denied_even_when_sealed_sandboxed():
    decision = AIExecutionAssuranceInspector().inspect(
        RiskBand.CRITICAL,
        sealed=True,
        sandbox_verified=True,
        backend_id="sandbox:real",
    )
    assert not decision.allowed
    assert decision.required is AssuranceLevel.DENIED


def test_assurance_custom_policy_can_require_seal_for_low():
    inspector = AIExecutionAssuranceInspector(
        AIExecutionAssurancePolicy(low=AssuranceLevel.SEALED)
    )
    assert not inspector.inspect(
        RiskBand.LOW,
        sealed=False,
        sandbox_verified=False,
    ).allowed
    assert inspector.inspect(
        RiskBand.LOW,
        sealed=True,
        sandbox_verified=False,
    ).allowed


def test_assurance_require_raises_on_failure():
    with pytest.raises(RuntimeError, match="sealed"):
        AIExecutionAssuranceInspector().require(
            RiskBand.MEDIUM,
            sealed=False,
            sandbox_verified=False,
        )


def anchor_store(clock=lambda: 100.0):
    backend = InMemoryFencedStore()
    signer = ArtifactSigner("audit-key", b"k" * 32, clock=clock)
    return backend, signer, AIAuditAnchorStore(
        backend,
        signer,
        namespace="audit",
        clock=clock,
    )


def append_anchor(store, session_id="session"):
    return store.append(
        session_id=session_id,
        checkpoint_digest=fp("c"),
        provenance_digest=fp("p"),
        journal_root=fp("j"),
        receipt_root=fp("r"),
        session_evidence_digest=fp("s"),
        release_evidence_digest=fp("l"),
        sandbox_binding_digest=fp("b"),
    )


def test_audit_anchor_digest_stable():
    anchor = AIAuditAnchor(
        1,
        "session",
        fp("c"),
        fp("p"),
        fp("j"),
        fp("r"),
        fp("s"),
        fp("l"),
        fp("b"),
        100.0,
    )
    assert len(anchor.digest) == 64
    assert anchor.digest == anchor.digest


def test_audit_anchor_append_and_verify():
    _, signer, store = anchor_store()
    record = append_anchor(store)
    assert len(record.chain_node_hash) == 64
    assert record.signature.artifact_digest == record.anchor.digest
    signer.verify(record.signature)
    assert store.verify()
    assert store.root_hash() == record.chain_node_hash


def test_audit_anchor_survives_new_store_instance():
    backend, signer, first = anchor_store()
    one = append_anchor(first, "one")
    second = AIAuditAnchorStore(
        backend,
        signer,
        namespace="audit",
        clock=lambda: 101.0,
    )
    two = append_anchor(second, "two")
    items = second.snapshot()
    assert [item.anchor.session_id for item in items] == ["one", "two"]
    assert second.verify()
    assert second.root_hash() == two.chain_node_hash
    assert one.chain_node_hash != two.chain_node_hash


def test_audit_anchor_signature_tamper_detected():
    backend, _, store = anchor_store()
    append_anchor(store)
    node = store._chain.snapshot()[0]
    record = backend.get("audit", f"node:{node.node_hash}")
    payload = dict(node.payload)
    signature = dict(payload["signature"])
    signature["signature"] = fp("x")
    payload["signature"] = signature
    backend.compare_and_swap(
        "audit",
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload=payload),
    )
    assert not store.verify()


def test_audit_anchor_content_tamper_detected():
    backend, _, store = anchor_store()
    append_anchor(store)
    node = store._chain.snapshot()[0]
    record = backend.get("audit", f"node:{node.node_hash}")
    payload = dict(node.payload)
    anchor = dict(payload["anchor"])
    anchor["session_id"] = "other"
    payload["anchor"] = anchor
    backend.compare_and_swap(
        "audit",
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload=payload),
    )
    assert not store.verify()


def test_audit_anchor_wrong_artifact_type_detected():
    backend, _, store = anchor_store()
    append_anchor(store)
    node = store._chain.snapshot()[0]
    record = backend.get("audit", f"node:{node.node_hash}")
    payload = dict(node.payload)
    signature = dict(payload["signature"])
    signature["artifact_type"] = "wrong"
    payload["signature"] = signature
    backend.compare_and_swap(
        "audit",
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload=payload),
    )
    assert not store.verify()


def test_audit_anchor_invalid_required_digest():
    with pytest.raises(ValueError):
        AIAuditAnchor(
            1,
            "session",
            "bad",
            fp("p"),
            fp("j"),
            fp("r"),
            fp("s"),
        )


def test_audit_anchor_invalid_optional_digest():
    with pytest.raises(ValueError):
        AIAuditAnchor(
            1,
            "session",
            fp("c"),
            fp("p"),
            fp("j"),
            fp("r"),
            fp("s"),
            release_evidence_digest="bad",
        )


def test_audit_anchor_negative_time_rejected():
    with pytest.raises(ValueError):
        AIAuditAnchor(
            1,
            "session",
            fp("c"),
            fp("p"),
            fp("j"),
            fp("r"),
            fp("s"),
            observed_at=-1,
        )
