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
