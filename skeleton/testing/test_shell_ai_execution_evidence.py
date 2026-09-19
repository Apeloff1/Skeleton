"""Final signed AI execution-evidence bundle tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.execution_evidence import (
    AIExecutionEvidence,
    AIExecutionEvidenceBuilder,
    AIExecutionEvidenceStore,
    SignedAIExecutionEvidence,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.evidence_chain import EvidenceCorruption


def fp(char):
    return char * 64


def build(builder=None, **changes):
    builder = builder or AIExecutionEvidenceBuilder(clock=lambda: 100.0)
    values = dict(
        session_id="session",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
        provenance_digest=fp("v"),
        checkpoint_digest=fp("c"),
        session_evidence_digest=fp("e"),
        session_journal_digest=fp("j"),
        audit_anchor_digest=fp("a"),
        audit_chain_node_hash=fp("n"),
        release_evidence_digest=fp("r"),
        sandbox_binding_digest=fp("s"),
        model_attestation_digest=fp("m"),
        execution_seal_id="seal-1",
        quorum_approval_digest=fp("q"),
        runtime_trust_digest=fp("t"),
        authority_health_policy_digest=fp("h"),
        audit_witness_digest=fp("w"),
        audit_witness_sequence=1,
    )
    values.update(changes)
    return builder.build(**values)


def store(backend=None, signer=None, **kwargs):
    return AIExecutionEvidenceStore(
        backend or InMemoryFencedStore(),
        signer or ArtifactSigner("evidence-key", b"k" * 32),
        **kwargs,
    )


def test_execution_evidence_builder_timestamp():
    evidence = build()
    assert evidence.completed_at == 100
    assert evidence.schema_version == 1


def test_execution_evidence_digest_stable():
    evidence = build()
    assert len(evidence.digest) == 64
    assert evidence.digest == evidence.digest


def test_execution_evidence_digest_changes_with_seal():
    first = build(execution_seal_id="seal-a")
    second = build(execution_seal_id="seal-b")
    assert first.digest != second.digest


def test_execution_evidence_digest_changes_with_quorum():
    first = build(quorum_approval_digest=fp("a"))
    second = build(quorum_approval_digest=fp("b"))
    assert first.digest != second.digest


def test_execution_evidence_digest_changes_with_release():
    first = build(release_evidence_digest=fp("a"))
    second = build(release_evidence_digest=fp("b"))
    assert first.digest != second.digest


def test_execution_evidence_optional_fields_can_be_empty():
    evidence = build(
        release_evidence_digest="",
        sandbox_binding_digest="",
        model_attestation_digest="",
        execution_seal_id="",
        quorum_approval_digest="",
        runtime_trust_digest="",
        authority_health_policy_digest="",
        audit_witness_digest="",
        audit_witness_sequence=None,
    )
    assert evidence.release_evidence_digest == ""
    assert evidence.execution_seal_id == ""


@pytest.mark.parametrize(
    "field",
    [
        "intent_fingerprint",
        "proposal_fingerprint",
        "provenance_digest",
        "checkpoint_digest",
        "session_evidence_digest",
        "session_journal_digest",
        "audit_anchor_digest",
        "audit_chain_node_hash",
    ],
)
def test_execution_evidence_required_digest_validation(field):
    values = dict(
        schema_version=1,
        session_id="session",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
        provenance_digest=fp("v"),
        checkpoint_digest=fp("c"),
        session_evidence_digest=fp("e"),
        session_journal_digest=fp("j"),
        audit_anchor_digest=fp("a"),
        audit_chain_node_hash=fp("n"),
        completed_at=1.0,
    )
    values[field] = "bad"
    with pytest.raises(ValueError):
        AIExecutionEvidence(**values)


@pytest.mark.parametrize(
    "field",
    [
        "release_evidence_digest",
        "sandbox_binding_digest",
        "model_attestation_digest",
        "quorum_approval_digest",
        "runtime_trust_digest",
        "authority_health_policy_digest",
        "execution_attempt_authority_digest",
        "audit_witness_digest",
    ],
)
def test_execution_evidence_optional_digest_validation(field):
    values = dict(
        schema_version=1,
        session_id="session",
        intent_fingerprint=fp("i"),
        proposal_fingerprint=fp("p"),
        provenance_digest=fp("v"),
        checkpoint_digest=fp("c"),
        session_evidence_digest=fp("e"),
        session_journal_digest=fp("j"),
        audit_anchor_digest=fp("a"),
        audit_chain_node_hash=fp("n"),
        completed_at=1.0,
    )
    values[field] = "bad"
    with pytest.raises(ValueError):
        AIExecutionEvidence(**values)


def test_execution_evidence_schema_validation():
    with pytest.raises(ValueError, match="schema"):
        AIExecutionEvidence(
            2,
            "session",
            fp("i"),
            fp("p"),
            fp("v"),
            fp("c"),
            fp("e"),
            fp("j"),
            fp("a"),
            fp("n"),
        )


def test_execution_evidence_session_validation():
    with pytest.raises(ValueError, match="session"):
        AIExecutionEvidence(
            1,
            "",
            fp("i"),
            fp("p"),
            fp("v"),
            fp("c"),
            fp("e"),
            fp("j"),
            fp("a"),
            fp("n"),
        )


def test_execution_evidence_time_validation():
    with pytest.raises(ValueError, match="completed"):
        AIExecutionEvidence(
            1,
            "session",
            fp("i"),
            fp("p"),
            fp("v"),
            fp("c"),
            fp("e"),
            fp("j"),
            fp("a"),
            fp("n"),
            completed_at=-1,
        )


def test_execution_evidence_seal_id_limit():
    with pytest.raises(ValueError, match="seal"):
        build(execution_seal_id="x" * 129)


def test_execution_evidence_store_append_signs_bundle():
    target = store()
    evidence = build()
    signed = target.append(evidence)
    assert signed.evidence == evidence
    assert signed.signature.artifact_type == "ai-execution-evidence"
    assert signed.signature.artifact_digest == evidence.digest
    assert signed.signature.metadata["session_id"] == "session"
    assert signed.signature.metadata["execution_seal_id"] == "seal-1"
    assert len(signed.chain_node_hash) == 64
    assert target.verify()


def test_execution_evidence_store_snapshot_round_trip():
    target = store()
    first = target.append(build(session_id="one"))
    second = target.append(build(session_id="two"))
    items = target.snapshot()
    assert [item.evidence.session_id for item in items] == ["one", "two"]
    assert items[0].evidence.digest == first.evidence.digest
    assert items[1].evidence.digest == second.evidence.digest


def test_execution_evidence_store_survives_restart():
    backend = InMemoryFencedStore()
    signer = ArtifactSigner("evidence-key", b"k" * 32)
    first = AIExecutionEvidenceStore(
        backend,
        signer,
        namespace="evidence",
    )
    item = first.append(build())
    second = AIExecutionEvidenceStore(
        backend,
        signer,
        namespace="evidence",
    )
    assert second.snapshot()[0].evidence.digest == item.evidence.digest
    assert second.root_hash() == first.root_hash()
    assert second.verify()


def test_execution_evidence_wrong_signing_key_fails():
    backend = InMemoryFencedStore()
    first = AIExecutionEvidenceStore(
        backend,
        ArtifactSigner("key", b"k" * 32),
        namespace="evidence",
    )
    first.append(build())
    second = AIExecutionEvidenceStore(
        backend,
        ArtifactSigner("key", b"x" * 32),
        namespace="evidence",
    )
    assert not second.verify()


def test_execution_evidence_wrong_key_id_fails():
    backend = InMemoryFencedStore()
    first = AIExecutionEvidenceStore(
        backend,
        ArtifactSigner("one", b"k" * 32),
        namespace="evidence",
    )
    first.append(build())
    second = AIExecutionEvidenceStore(
        backend,
        ArtifactSigner("two", b"k" * 32),
        namespace="evidence",
    )
    assert not second.verify()


def test_execution_evidence_tampered_payload_fails_outer_chain():
    backend = InMemoryFencedStore()
    target = store(backend=backend)
    target.append(build())
    node = target._chain.snapshot()[0]
    record = backend.get(
        target._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    raw = dict(payload["evidence"])
    raw["proposal_fingerprint"] = fp("x")
    payload["evidence"] = raw
    backend.compare_and_swap(
        target._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload=payload),
    )
    assert not target.verify()


def test_execution_evidence_tampered_signature_fails():
    backend = InMemoryFencedStore()
    target = store(backend=backend)
    target.append(build())
    node = target._chain.snapshot()[0]
    record = backend.get(
        target._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    raw = dict(payload["signature"])
    raw["signature"] = fp("x")
    payload["signature"] = raw
    backend.compare_and_swap(
        target._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload=payload),
    )
    assert not target.verify()


def test_execution_evidence_missing_signature_payload():
    backend = InMemoryFencedStore()
    target = store(backend=backend)
    target.append(build())
    node = target._chain.snapshot()[0]
    record = backend.get(
        target._chain.namespace,
        f"node:{node.node_hash}",
    )
    backend.compare_and_swap(
        target._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(
            node,
            payload={"evidence": build().to_dict()},
        ),
    )
    with pytest.raises(EvidenceCorruption):
        target.snapshot()
    assert not target.verify()


def test_execution_evidence_metadata_session_binding_verified():
    backend = InMemoryFencedStore()
    target = store(backend=backend)
    target.append(build())
    node = target._chain.snapshot()[0]
    record = backend.get(
        target._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    raw_sig = dict(payload["signature"])
    raw_sig["metadata"] = {
        "session_id": "other",
        "execution_seal_id": "seal-1",
    }
    payload["signature"] = raw_sig
    backend.compare_and_swap(
        target._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload=payload),
    )
    assert not target.verify()


def test_execution_evidence_metadata_seal_binding_verified():
    backend = InMemoryFencedStore()
    target = store(backend=backend)
    target.append(build())
    node = target._chain.snapshot()[0]
    record = backend.get(
        target._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    raw_sig = dict(payload["signature"])
    raw_sig["metadata"] = {
        "session_id": "session",
        "execution_seal_id": "other",
    }
    payload["signature"] = raw_sig
    backend.compare_and_swap(
        target._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload=payload),
    )
    assert not target.verify()


def test_execution_evidence_capacity():
    target = store(max_items=1)
    target.append(build(session_id="one"))
    with pytest.raises(RuntimeError, match="capacity"):
        target.append(build(session_id="two"))


def test_signed_execution_evidence_chain_hash_validation():
    evidence = build()
    signature = ArtifactSigner("key", b"k" * 32).sign(
        "ai-execution-evidence",
        evidence.digest,
    )
    with pytest.raises(ValueError, match="chain_node_hash"):
        SignedAIExecutionEvidence(
            evidence,
            signature,
            "bad",
        )


def test_execution_evidence_root_changes_per_append():
    target = store()
    initial = target.root_hash()
    target.append(build(session_id="one"))
    first = target.root_hash()
    target.append(build(session_id="two"))
    second = target.root_hash()
    assert initial != first
    assert first != second


def test_execution_evidence_digest_changes_with_runtime_trust():
    first = build(runtime_trust_digest=fp("a"))
    second = build(runtime_trust_digest=fp("b"))
    assert first.digest != second.digest


def test_execution_evidence_digest_changes_with_authority_health_policy():
    first = build(authority_health_policy_digest=fp("a"))
    second = build(authority_health_policy_digest=fp("b"))
    assert first.digest != second.digest


def test_execution_evidence_digest_changes_with_audit_witness():
    first = build(
        audit_witness_digest=fp("a"),
        audit_witness_sequence=1,
    )
    second = build(
        audit_witness_digest=fp("b"),
        audit_witness_sequence=1,
    )
    assert first.digest != second.digest


def test_execution_evidence_digest_changes_with_witness_sequence():
    first = build(audit_witness_sequence=1)
    second = build(audit_witness_sequence=2)
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "witness_digest,witness_sequence",
    [
        ("", 1),
        (fp("w"), None),
        ("", 0),
        (fp("w"), 0),
        (fp("w"), -1),
        (fp("w"), True),
    ],
)
def test_execution_evidence_witness_fields_must_be_paired(
    witness_digest,
    witness_sequence,
):
    with pytest.raises(ValueError, match="witness"):
        build(
            audit_witness_digest=witness_digest,
            audit_witness_sequence=witness_sequence,
        )


def test_execution_evidence_witness_round_trip_through_store():
    target = store()
    evidence = build(
        runtime_trust_digest=fp("t"),
        authority_health_policy_digest=fp("h"),
        audit_witness_digest=fp("w"),
        audit_witness_sequence=7,
    )
    target.append(evidence)
    loaded = target.snapshot()[0].evidence
    assert loaded.runtime_trust_digest == fp("t")
    assert loaded.authority_health_policy_digest == fp("h")
    assert loaded.audit_witness_digest == fp("w")
    assert loaded.audit_witness_sequence == 7
    assert target.verify()


def test_execution_evidence_tampered_witness_identity_breaks_outer_chain():
    backend = InMemoryFencedStore()
    target = store(backend=backend)
    target.append(build())
    node = target._chain.snapshot()[0]
    record = backend.get(
        target._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    raw = dict(payload["evidence"])
    raw["audit_witness_digest"] = fp("x")
    payload["evidence"] = raw
    backend.compare_and_swap(
        target._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload=payload),
    )
    assert not target.verify()


def test_execution_evidence_optional_trust_health_can_be_empty():
    evidence = build(
        runtime_trust_digest="",
        authority_health_policy_digest="",
    )
    assert evidence.runtime_trust_digest == ""
    assert evidence.authority_health_policy_digest == ""


def test_execution_evidence_binds_attempt_identity_and_state():
    evidence = build(
        execution_attempt_id="attempt-1",
        execution_attempt_authority_digest=fp("z"),
        execution_attempt_state="succeeded",
    )
    assert evidence.execution_attempt_id == "attempt-1"
    assert evidence.execution_attempt_authority_digest == fp("z")
    assert evidence.execution_attempt_state == "succeeded"
    data = evidence.to_dict()
    assert data["execution_attempt_id"] == "attempt-1"
    assert data["execution_attempt_authority_digest"] == fp("z")
    assert data["execution_attempt_state"] == "succeeded"


def test_execution_evidence_digest_changes_with_attempt_authority():
    first = build(
        execution_attempt_id="attempt",
        execution_attempt_authority_digest=fp("a"),
        execution_attempt_state="succeeded",
    )
    second = build(
        execution_attempt_id="attempt",
        execution_attempt_authority_digest=fp("b"),
        execution_attempt_state="succeeded",
    )
    assert first.digest != second.digest


def test_execution_evidence_digest_changes_with_attempt_state():
    first = build(
        execution_attempt_id="attempt",
        execution_attempt_authority_digest=fp("a"),
        execution_attempt_state="succeeded",
    )
    second = build(
        execution_attempt_id="attempt",
        execution_attempt_authority_digest=fp("a"),
        execution_attempt_state="failed",
    )
    assert first.digest != second.digest


def test_execution_evidence_digest_changes_with_attempt_id():
    first = build(
        execution_attempt_id="attempt-a",
        execution_attempt_authority_digest=fp("a"),
        execution_attempt_state="succeeded",
    )
    second = build(
        execution_attempt_id="attempt-b",
        execution_attempt_authority_digest=fp("a"),
        execution_attempt_state="succeeded",
    )
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "attempt_id,authority_digest,state",
    [
        ("attempt", "", "succeeded"),
        ("", fp("a"), ""),
        ("", "", "succeeded"),
    ],
)
def test_execution_evidence_attempt_fields_must_be_consistent(
    attempt_id,
    authority_digest,
    state,
):
    with pytest.raises(ValueError, match="execution attempt"):
        build(
            execution_attempt_id=attempt_id,
            execution_attempt_authority_digest=authority_digest,
            execution_attempt_state=state,
        )


def test_execution_evidence_attempt_authority_digest_validation():
    with pytest.raises(ValueError, match="execution_attempt_authority_digest"):
        build(
            execution_attempt_id="attempt",
            execution_attempt_authority_digest="bad",
            execution_attempt_state="succeeded",
        )


def test_execution_evidence_attempt_id_limit():
    with pytest.raises(ValueError, match="execution_attempt_id"):
        build(
            execution_attempt_id="x" * 257,
            execution_attempt_authority_digest=fp("a"),
            execution_attempt_state="succeeded",
        )


def test_execution_evidence_attempt_state_limit():
    with pytest.raises(ValueError, match="execution_attempt_state"):
        build(
            execution_attempt_id="attempt",
            execution_attempt_authority_digest=fp("a"),
            execution_attempt_state="x" * 65,
        )


def test_execution_evidence_attempt_round_trip_through_store():
    target = store()
    evidence = build(
        execution_attempt_id="attempt-1",
        execution_attempt_authority_digest=fp("z"),
        execution_attempt_state="succeeded",
    )
    target.append(evidence)
    loaded = target.snapshot()[0].evidence
    assert loaded.execution_attempt_id == "attempt-1"
    assert loaded.execution_attempt_authority_digest == fp("z")
    assert loaded.execution_attempt_state == "succeeded"
    assert loaded.digest == evidence.digest
    assert target.verify()


def test_execution_evidence_attempt_tamper_breaks_outer_chain():
    backend = InMemoryFencedStore()
    target = store(backend=backend)
    target.append(
        build(
            execution_attempt_id="attempt-1",
            execution_attempt_authority_digest=fp("z"),
            execution_attempt_state="succeeded",
        )
    )
    node = target._chain.snapshot()[0]
    record = backend.get(
        target._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    raw = dict(payload["evidence"])
    raw["execution_attempt_state"] = "failed"
    payload["evidence"] = raw
    backend.compare_and_swap(
        target._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload=payload),
    )
    assert not target.verify()


def test_execution_evidence_attempt_fields_can_be_absent_for_legacy_flow():
    evidence = build(
        execution_attempt_id="",
        execution_attempt_authority_digest="",
        execution_attempt_state="",
    )
    assert evidence.execution_attempt_id == ""
    assert evidence.execution_attempt_authority_digest == ""
    assert evidence.execution_attempt_state == ""


def test_execution_evidence_digest_changes_with_execution_attempt():
    first = build(
        execution_attempt_id="seal-a",
        execution_attempt_authority_digest=fp("a"),
    )
    second = build(
        execution_attempt_id="seal-b",
        execution_attempt_authority_digest=fp("b"),
    )
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "attempt_id,authority_digest",
    [
        ("seal", ""),
        ("", fp("a")),
        ("x" * 257, fp("a")),
    ],
)
def test_execution_evidence_attempt_fields_must_be_paired(
    attempt_id,
    authority_digest,
):
    with pytest.raises(ValueError):
        build(
            execution_attempt_id=attempt_id,
            execution_attempt_authority_digest=authority_digest,
        )


def test_execution_evidence_attempt_round_trip_through_store():
    target = store()
    evidence = build(
        execution_attempt_id="seal-1",
        execution_attempt_authority_digest=fp("a"),
    )
    target.append(evidence)
    loaded = target.snapshot()[0].evidence
    assert loaded.execution_attempt_id == "seal-1"
    assert loaded.execution_attempt_authority_digest == fp("a")
    assert loaded.digest == evidence.digest
    assert target.verify()


def test_execution_evidence_attempt_tamper_breaks_outer_chain():
    backend = InMemoryFencedStore()
    target = store(backend=backend)
    target.append(
        build(
            execution_attempt_id="seal-1",
            execution_attempt_authority_digest=fp("a"),
        )
    )
    node = target._chain.snapshot()[0]
    record = backend.get(
        target._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    raw = dict(payload["evidence"])
    raw["execution_attempt_authority_digest"] = fp("x")
    payload["evidence"] = raw
    backend.compare_and_swap(
        target._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload=payload),
    )
    assert not target.verify()
