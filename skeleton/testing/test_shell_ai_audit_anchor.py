"""Signed durable AI audit-anchor tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.audit_anchor import (
    AIAuditAnchor,
    AIAuditAnchorStore,
    SignedAIAuditAnchor,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.evidence_chain import EvidenceCorruption


def fp(char):
    return char * 64


def append(store, session="s", **changes):
    values = dict(
        session_id=session,
        checkpoint_digest=fp("c"),
        provenance_digest=fp("p"),
        journal_root=fp("j"),
        receipt_root=fp("r"),
        session_evidence_digest=fp("e"),
        release_evidence_digest=fp("l"),
        sandbox_binding_digest=fp("b"),
    )
    values.update(changes)
    return store.append(**values)


def make_store(backend=None, signer=None, **kwargs):
    return AIAuditAnchorStore(
        backend or InMemoryFencedStore(),
        signer or ArtifactSigner("audit-key", b"k" * 32),
        **kwargs,
    )


def test_audit_anchor_digest_stable():
    anchor = AIAuditAnchor(
        1,
        "session",
        fp("c"),
        fp("p"),
        fp("j"),
        fp("r"),
        fp("e"),
        fp("l"),
        fp("b"),
        observed_at=123.0,
    )
    assert len(anchor.digest) == 64
    assert anchor.digest == anchor.digest


def test_audit_anchor_optional_release_and_sandbox():
    anchor = AIAuditAnchor(
        1,
        "session",
        fp("c"),
        fp("p"),
        fp("j"),
        fp("r"),
        fp("e"),
        "",
        "",
        observed_at=0.0,
    )
    assert anchor.release_evidence_digest == ""
    assert anchor.sandbox_binding_digest == ""


@pytest.mark.parametrize(
    "field,value",
    [
        ("checkpoint_digest", "bad"),
        ("provenance_digest", "bad"),
        ("journal_root", "bad"),
        ("receipt_root", "bad"),
        ("session_evidence_digest", "bad"),
        ("release_evidence_digest", "bad"),
        ("sandbox_binding_digest", "bad"),
        ("execution_attempt_authority_digest", "bad"),
    ],
)
def test_audit_anchor_digest_validation(field, value):
    values = dict(
        schema_version=1,
        session_id="session",
        checkpoint_digest=fp("c"),
        provenance_digest=fp("p"),
        journal_root=fp("j"),
        receipt_root=fp("r"),
        session_evidence_digest=fp("e"),
        release_evidence_digest=fp("l"),
        sandbox_binding_digest=fp("b"),
        observed_at=1.0,
    )
    values[field] = value
    with pytest.raises(ValueError):
        AIAuditAnchor(**values)


def test_audit_anchor_schema_validation():
    with pytest.raises(ValueError, match="schema"):
        AIAuditAnchor(
            2,
            "session",
            fp("c"),
            fp("p"),
            fp("j"),
            fp("r"),
            fp("e"),
        )


def test_audit_anchor_session_validation():
    with pytest.raises(ValueError, match="session"):
        AIAuditAnchor(
            1,
            "",
            fp("c"),
            fp("p"),
            fp("j"),
            fp("r"),
            fp("e"),
        )


def test_audit_anchor_time_validation():
    with pytest.raises(ValueError, match="observed"):
        AIAuditAnchor(
            1,
            "session",
            fp("c"),
            fp("p"),
            fp("j"),
            fp("r"),
            fp("e"),
            observed_at=-1,
        )


def test_audit_anchor_store_append_and_verify():
    now = [10.0]
    store = make_store(clock=lambda: now[0])
    item = append(store)
    assert item.anchor.observed_at == 10
    assert item.signature.artifact_type == "ai-audit-anchor"
    assert item.signature.artifact_digest == item.anchor.digest
    assert len(item.chain_node_hash) == 64
    assert store.verify()


def test_audit_anchor_snapshot_round_trip():
    store = make_store()
    first = append(store, "s1")
    second = append(store, "s2")
    items = store.snapshot()
    assert [item.anchor.session_id for item in items] == ["s1", "s2"]
    assert items[0].anchor.digest == first.anchor.digest
    assert items[1].anchor.digest == second.anchor.digest
    assert store.verify()


def test_audit_anchor_survives_new_store_instance():
    backend = InMemoryFencedStore()
    signer = ArtifactSigner("audit-key", b"k" * 32)
    first = AIAuditAnchorStore(
        backend,
        signer,
        namespace="audit",
    )
    item = append(first)
    second = AIAuditAnchorStore(
        backend,
        signer,
        namespace="audit",
    )
    assert second.snapshot()[0].anchor.digest == item.anchor.digest
    assert second.verify()
    assert second.root_hash() == first.root_hash()


def test_audit_anchor_wrong_signer_key_fails_verification():
    backend = InMemoryFencedStore()
    first = AIAuditAnchorStore(
        backend,
        ArtifactSigner("audit-key", b"k" * 32),
        namespace="audit",
    )
    append(first)
    second = AIAuditAnchorStore(
        backend,
        ArtifactSigner("audit-key", b"x" * 32),
        namespace="audit",
    )
    assert not second.verify()


def test_audit_anchor_wrong_signer_id_fails_verification():
    backend = InMemoryFencedStore()
    first = AIAuditAnchorStore(
        backend,
        ArtifactSigner("key-one", b"k" * 32),
        namespace="audit",
    )
    append(first)
    second = AIAuditAnchorStore(
        backend,
        ArtifactSigner("key-two", b"k" * 32),
        namespace="audit",
    )
    assert not second.verify()


def test_audit_anchor_tampered_signature_fails():
    backend = InMemoryFencedStore()
    store = make_store(backend=backend)
    append(store)
    node = store._chain.snapshot()[0]
    record = backend.get(
        store._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    signature = dict(payload["signature"])
    signature["signature"] = fp("x")
    payload["signature"] = signature
    backend.compare_and_swap(
        store._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload=payload),
    )
    assert not store.verify()


def test_audit_anchor_tampered_anchor_fails():
    backend = InMemoryFencedStore()
    store = make_store(backend=backend)
    append(store)
    node = store._chain.snapshot()[0]
    record = backend.get(
        store._chain.namespace,
        f"node:{node.node_hash}",
    )
    payload = dict(node.payload)
    anchor = dict(payload["anchor"])
    anchor["provenance_digest"] = fp("x")
    payload["anchor"] = anchor
    backend.compare_and_swap(
        store._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload=payload),
    )
    assert not store.verify()


def test_audit_anchor_missing_payload_rejected():
    backend = InMemoryFencedStore()
    store = make_store(backend=backend)
    append(store)
    node = store._chain.snapshot()[0]
    record = backend.get(
        store._chain.namespace,
        f"node:{node.node_hash}",
    )
    backend.compare_and_swap(
        store._chain.namespace,
        f"node:{node.node_hash}",
        expected_revision=record.revision,
        value=replace(node, payload={"bad": True}),
    )
    with pytest.raises(EvidenceCorruption):
        store.snapshot()
    assert not store.verify()


def test_audit_anchor_capacity():
    store = make_store(max_anchors=1)
    append(store, "s1")
    with pytest.raises(RuntimeError, match="capacity"):
        append(store, "s2")


def test_audit_anchor_release_digest_is_signed():
    store = make_store()
    item = append(
        store,
        release_evidence_digest=fp("x"),
    )
    assert item.anchor.release_evidence_digest == fp("x")
    store.signer.verify(item.signature)


def test_audit_anchor_sandbox_digest_is_signed():
    store = make_store()
    item = append(
        store,
        sandbox_binding_digest=fp("x"),
    )
    assert item.anchor.sandbox_binding_digest == fp("x")
    store.signer.verify(item.signature)


def test_audit_anchor_root_changes_each_append():
    store = make_store()
    initial = store.root_hash()
    append(store, "s1")
    first = store.root_hash()
    append(store, "s2")
    second = store.root_hash()
    assert initial != first
    assert first != second


def test_signed_anchor_chain_hash_validation():
    anchor = AIAuditAnchor(
        1,
        "session",
        fp("c"),
        fp("p"),
        fp("j"),
        fp("r"),
        fp("e"),
    )
    signature = ArtifactSigner("k", b"k" * 32).sign(
        "ai-audit-anchor",
        anchor.digest,
    )
    with pytest.raises(ValueError, match="chain_node_hash"):
        SignedAIAuditAnchor(anchor, signature, "bad")


def test_audit_anchor_execution_attempt_binding_changes_digest():
    first = AIAuditAnchor(
        1,
        "session",
        fp("c"),
        fp("p"),
        fp("j"),
        fp("r"),
        fp("e"),
        execution_attempt_id="seal-a",
        execution_attempt_authority_digest=fp("a"),
    )
    second = replace(
        first,
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
def test_audit_anchor_execution_attempt_fields_are_paired(
    attempt_id,
    authority_digest,
):
    with pytest.raises(ValueError):
        AIAuditAnchor(
            1,
            "session",
            fp("c"),
            fp("p"),
            fp("j"),
            fp("r"),
            fp("e"),
            execution_attempt_id=attempt_id,
            execution_attempt_authority_digest=authority_digest,
        )


def test_audit_anchor_execution_attempt_round_trip():
    store = make_store()
    item = append(
        store,
        execution_attempt_id="seal-1",
        execution_attempt_authority_digest=fp("a"),
    )
    loaded = store.snapshot()[0]
    assert loaded.anchor.execution_attempt_id == "seal-1"
    assert loaded.anchor.execution_attempt_authority_digest == fp("a")
    assert loaded.anchor.digest == item.anchor.digest
    assert store.verify()
