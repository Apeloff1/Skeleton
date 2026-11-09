"""Rollback-resistant audit witness tests for the AI shell plane."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from skeleton.shells.ai.audit_witness import (
    AIAuditWitness,
    AIAuditWitnessStore,
    AuditWitnessHead,
    SignedAIAuditWitness,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
    SignedArtifact,
)


def fp(char: str) -> str:
    return hashlib.sha256(char.encode()).hexdigest()


def signer(clock=lambda: 10.0) -> ArtifactSigner:
    return ArtifactSigner(
        "audit-key",
        b"k" * 32,
        clock=clock,
    )


def store(
    backend=None,
    *,
    clock=lambda: 10.0,
    max_witnesses=100,
    max_retries=8,
):
    return AIAuditWitnessStore(
        backend or InMemoryFencedStore(),
        signer(clock),
        clock=clock,
        max_witnesses=max_witnesses,
        max_retries=max_retries,
    )


def test_first_audit_witness_has_no_predecessor():
    item = store().publish(fp("a"))
    assert item.witness.sequence == 1
    assert item.witness.audit_root == fp("a")
    assert item.witness.previous_witness_digest == ""
    assert item.signature.artifact_type == "ai-audit-witness"
    assert item.signature.artifact_digest == item.witness.digest


def test_second_audit_witness_chains_to_first_digest():
    target = store()
    first = target.publish(fp("a"))
    second = target.publish(fp("b"))
    assert second.witness.sequence == 2
    assert second.witness.previous_witness_digest == first.witness.digest
    assert second.witness.audit_root == fp("b")


def test_audit_witness_current_head_tracks_latest_publish():
    target = store()
    first = target.publish(fp("a"))
    revision, head = target.current_head()
    assert revision == 1
    assert head == AuditWitnessHead(1, first.witness.digest)

    second = target.publish(fp("b"))
    revision, head = target.current_head()
    assert revision == 2
    assert head.sequence == 2
    assert head.witness_digest == second.witness.digest


def test_audit_witness_verify_empty_store_is_valid():
    report = store().verify()
    assert report.ok
    assert report.head_sequence == 0
    assert report.head_digest == ""
    assert report.audit_root == ""


def test_audit_witness_verify_complete_chain():
    target = store()
    target.publish(fp("a"))
    target.publish(fp("b"))
    target.publish(fp("c"))
    report = target.verify()
    assert report.ok
    assert report.head_sequence == 3
    assert report.audit_root == fp("c")
    assert not report.reasons


def test_audit_witness_get_round_trip():
    target = store()
    first = target.publish(fp("a"))
    loaded = target.get(1)
    assert loaded == first


def test_audit_witness_get_missing_sequence():
    with pytest.raises(KeyError):
        store().get(1)


@pytest.mark.parametrize("sequence", [0, -1, True])
def test_audit_witness_get_rejects_invalid_sequence(sequence):
    with pytest.raises(ValueError, match="sequence"):
        store().get(sequence)


def test_audit_witness_binds_runtime_trust_and_release():
    target = store()
    item = target.publish(
        fp("a"),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    assert item.witness.runtime_trust_digest == fp("t")
    assert item.witness.release_evidence_digest == fp("r")


def test_audit_witness_digest_changes_with_runtime_trust():
    first = AIAuditWitness(1, 1, fp("a"), "", fp("t"))
    second = AIAuditWitness(1, 1, fp("a"), "", fp("u"))
    assert first.digest != second.digest


def test_audit_witness_digest_changes_with_release_evidence():
    first = AIAuditWitness(
        1,
        1,
        fp("a"),
        "",
        release_evidence_digest=fp("r"),
    )
    second = AIAuditWitness(
        1,
        1,
        fp("a"),
        "",
        release_evidence_digest=fp("s"),
    )
    assert first.digest != second.digest


def test_audit_witness_digest_changes_with_observed_time():
    first = AIAuditWitness(1, 1, fp("a"), "", observed_at=1)
    second = AIAuditWitness(1, 1, fp("a"), "", observed_at=2)
    assert first.digest != second.digest


def test_audit_witness_digest_changes_with_predecessor():
    first = AIAuditWitness(1, 2, fp("a"), fp("b"))
    second = AIAuditWitness(1, 2, fp("a"), fp("c"))
    assert first.digest != second.digest


def test_require_current_root_happy_path():
    target = store()
    current = target.publish(
        fp("a"),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    loaded = target.require_current_root(
        fp("a"),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    assert loaded == current


def test_require_current_root_detects_rollback_or_drift():
    target = store()
    target.publish(fp("a"))
    with pytest.raises(RuntimeError, match="rollback or drift"):
        target.require_current_root(fp("b"))


def test_require_current_root_detects_runtime_trust_mismatch():
    target = store()
    target.publish(fp("a"), runtime_trust_digest=fp("t"))
    with pytest.raises(RuntimeError, match="runtime trust"):
        target.require_current_root(
            fp("a"),
            runtime_trust_digest=fp("u"),
        )


def test_require_current_root_detects_release_mismatch():
    target = store()
    target.publish(fp("a"), release_evidence_digest=fp("r"))
    with pytest.raises(RuntimeError, match="release"):
        target.require_current_root(
            fp("a"),
            release_evidence_digest=fp("s"),
        )


def test_require_current_root_requires_published_head():
    with pytest.raises(RuntimeError, match="no audit witness"):
        store().require_current_root(fp("a"))


def test_store_reconstruction_reads_existing_chain():
    backend = InMemoryFencedStore()
    first_store = AIAuditWitnessStore(
        backend,
        signer(),
    )
    first = first_store.publish(fp("a"))
    second_store = AIAuditWitnessStore(
        backend,
        signer(),
    )
    loaded = second_store.require_current_root(fp("a"))
    assert loaded.witness.digest == first.witness.digest
    assert second_store.verify().ok


def test_sequential_writers_share_monotonic_head():
    backend = InMemoryFencedStore()
    one = AIAuditWitnessStore(backend, signer())
    two = AIAuditWitnessStore(backend, signer())
    first = one.publish(fp("a"))
    second = two.publish(fp("b"))
    third = one.publish(fp("c"))
    assert first.witness.sequence == 1
    assert second.witness.sequence == 2
    assert third.witness.sequence == 3
    assert one.verify().ok
    assert two.verify().ok


def test_publish_respects_witness_capacity():
    target = store(max_witnesses=2)
    target.publish(fp("a"))
    target.publish(fp("b"))
    with pytest.raises(RuntimeError, match="capacity"):
        target.publish(fp("c"))
    assert target.current_head()[1].sequence == 2


def test_invalid_witness_schema_rejected():
    with pytest.raises(ValueError, match="schema"):
        AIAuditWitness(2, 1, fp("a"), "")


@pytest.mark.parametrize("sequence", [0, -1, True])
def test_invalid_witness_sequence_rejected(sequence):
    with pytest.raises(ValueError, match="sequence"):
        AIAuditWitness(1, sequence, fp("a"), "")


def test_first_witness_cannot_claim_predecessor():
    with pytest.raises(ValueError, match="first"):
        AIAuditWitness(1, 1, fp("a"), fp("b"))


def test_later_witness_requires_predecessor():
    with pytest.raises(ValueError, match="predecessor"):
        AIAuditWitness(1, 2, fp("a"), "")


@pytest.mark.parametrize(
    "field,value",
    [
        ("audit_root", "bad"),
        ("previous_witness_digest", "bad"),
        ("runtime_trust_digest", "bad"),
        ("release_evidence_digest", "bad"),
    ],
)
def test_witness_digest_field_validation(field, value):
    values = dict(
        schema_version=1,
        sequence=2,
        audit_root=fp("a"),
        previous_witness_digest=fp("b"),
    )
    values[field] = value
    with pytest.raises(ValueError):
        AIAuditWitness(**values)


def test_witness_rejects_negative_observed_time():
    with pytest.raises(ValueError, match="observed"):
        AIAuditWitness(1, 1, fp("a"), "", observed_at=-1)


def test_signed_witness_rejects_wrong_artifact_type():
    witness = AIAuditWitness(1, 1, fp("a"), "")
    signature = signer().sign("wrong", witness.digest)
    with pytest.raises(ValueError, match="artifact type"):
        SignedAIAuditWitness(witness, signature)


def test_signed_witness_rejects_wrong_artifact_digest():
    witness = AIAuditWitness(1, 1, fp("a"), "")
    signature = signer().sign("ai-audit-witness", fp("b"))
    with pytest.raises(ValueError, match="digest mismatch"):
        SignedAIAuditWitness(witness, signature)


def test_audit_head_validation():
    with pytest.raises(ValueError, match="sequence"):
        AuditWitnessHead(0, fp("a"))
    with pytest.raises(ValueError, match="witness_digest"):
        AuditWitnessHead(1, "bad")


def _rewrite_record(backend, namespace, key, mutate):
    current = backend.get(namespace, key)
    assert current is not None
    backend.compare_and_swap(
        namespace,
        key,
        expected_revision=current.revision,
        value=mutate(current.value),
    )


def test_verify_detects_signature_tamper():
    backend = InMemoryFencedStore()
    target = AIAuditWitnessStore(backend, signer())
    target.publish(fp("a"))

    def mutate(value):
        changed = dict(value)
        signature = dict(changed["signature"])
        signature["signature"] = "0" * 64
        changed["signature"] = signature
        return changed

    _rewrite_record(
        backend,
        target.namespace,
        target._node_key(1),
        mutate,
    )
    report = target.verify()
    assert not report.ok
    assert any("signature invalid" in reason for reason in report.reasons)


def test_verify_detects_witness_payload_tamper_even_with_old_signature():
    backend = InMemoryFencedStore()
    target = AIAuditWitnessStore(backend, signer())
    target.publish(fp("a"))

    def mutate(value):
        changed = dict(value)
        witness = dict(changed["witness"])
        witness["audit_root"] = fp("b")
        changed["witness"] = witness
        return changed

    _rewrite_record(
        backend,
        target.namespace,
        target._node_key(1),
        mutate,
    )
    report = target.verify()
    assert not report.ok
    assert any("invalid" in reason for reason in report.reasons)


def test_verify_detects_predecessor_break():
    backend = InMemoryFencedStore()
    target = AIAuditWitnessStore(backend, signer())
    target.publish(fp("a"))
    second = target.publish(fp("b"))

    forged = AIAuditWitness(
        1,
        2,
        fp("b"),
        fp("f"),
        observed_at=second.witness.observed_at,
    )
    forged_signed = SignedAIAuditWitness(
        forged,
        target.signer.sign("ai-audit-witness", forged.digest),
    )

    def mutate(_):
        return forged_signed.to_dict()

    _rewrite_record(
        backend,
        target.namespace,
        target._node_key(2),
        mutate,
    )
    report = target.verify()
    assert not report.ok
    assert any("predecessor mismatch" in reason for reason in report.reasons)


def test_verify_detects_missing_canonical_node():
    backend = InMemoryFencedStore()
    target = AIAuditWitnessStore(backend, signer())
    target.publish(fp("a"))
    target.publish(fp("b"))
    node = backend.get(target.namespace, target._node_key(2))
    assert node is not None
    backend.delete(
        target.namespace,
        target._node_key(2),
        expected_revision=node.revision,
    )
    report = target.verify()
    assert not report.ok
    assert any("unavailable" in reason for reason in report.reasons)


def test_verify_detects_head_digest_tamper():
    backend = InMemoryFencedStore()
    target = AIAuditWitnessStore(backend, signer())
    target.publish(fp("a"))
    head = backend.get(target.namespace, target.head_key)
    assert head is not None
    backend.compare_and_swap(
        target.namespace,
        target.head_key,
        expected_revision=head.revision,
        value=AuditWitnessHead(1, fp("f")).to_dict(),
    )
    report = target.verify()
    assert not report.ok
    assert any("head does not match" in reason for reason in report.reasons)


def test_require_current_root_detects_head_digest_tamper_before_signature():
    backend = InMemoryFencedStore()
    target = AIAuditWitnessStore(backend, signer())
    target.publish(fp("a"))
    head = backend.get(target.namespace, target.head_key)
    assert head is not None
    backend.compare_and_swap(
        target.namespace,
        target.head_key,
        expected_revision=head.revision,
        value=AuditWitnessHead(1, fp("f")).to_dict(),
    )
    with pytest.raises(RuntimeError, match="head digest"):
        target.require_current_root(fp("a"))


def test_head_rollback_is_detectable_against_expected_current_root():
    backend = InMemoryFencedStore()
    target = AIAuditWitnessStore(backend, signer())
    first = target.publish(fp("a"))
    target.publish(fp("b"))
    head_record = backend.get(target.namespace, target.head_key)
    assert head_record is not None
    backend.compare_and_swap(
        target.namespace,
        target.head_key,
        expected_revision=head_record.revision,
        value=AuditWitnessHead(1, first.witness.digest).to_dict(),
    )
    # The older witness is internally valid, but the caller's current audit
    # root commitment prevents a silent rollback from being accepted.
    with pytest.raises(RuntimeError, match="rollback or drift"):
        target.require_current_root(fp("b"))


def test_verify_report_is_json_shaped():
    target = store()
    target.publish(fp("a"))
    data = target.verify().to_dict()
    assert data["ok"] is True
    assert data["head_sequence"] == 1
    assert data["audit_root"] == fp("a")


def test_witness_to_dict_is_stable_and_complete():
    item = AIAuditWitness(
        1,
        2,
        fp("a"),
        fp("b"),
        fp("t"),
        fp("r"),
        12.5,
    )
    assert item.to_dict() == {
        "schema_version": 1,
        "sequence": 2,
        "audit_root": fp("a"),
        "previous_witness_digest": fp("b"),
        "runtime_trust_digest": fp("t"),
        "release_evidence_digest": fp("r"),
        "observed_at": 12.5,
    }


def test_signed_witness_to_dict_exposes_digest_not_signing_key():
    target = store()
    item = target.publish(fp("a"))
    data = item.to_dict()
    assert data["witness_digest"] == item.witness.digest
    assert "key" not in data["signature"]
    assert data["signature"]["key_id"] == "audit-key"


def test_publish_clock_is_bound_into_witness():
    now = [100.0]
    target = store(clock=lambda: now[0])
    first = target.publish(fp("a"))
    now[0] = 101.0
    second = target.publish(fp("b"))
    assert first.witness.observed_at == 100.0
    assert second.witness.observed_at == 101.0
    assert first.witness.digest != second.witness.digest


def test_store_constructor_bounds():
    with pytest.raises(ValueError, match="namespace"):
        AIAuditWitnessStore(
            InMemoryFencedStore(),
            signer(),
            namespace="",
        )
    with pytest.raises(ValueError, match="head key"):
        AIAuditWitnessStore(
            InMemoryFencedStore(),
            signer(),
            head_key="",
        )
    with pytest.raises(ValueError, match="max_witnesses"):
        AIAuditWitnessStore(
            InMemoryFencedStore(),
            signer(),
            max_witnesses=0,
        )
    with pytest.raises(ValueError, match="max_retries"):
        AIAuditWitnessStore(
            InMemoryFencedStore(),
            signer(),
            max_retries=0,
        )


def test_publish_rejects_invalid_external_digests():
    target = store()
    with pytest.raises(ValueError, match="audit_root"):
        target.publish("bad")
    with pytest.raises(ValueError, match="runtime_trust"):
        target.publish(fp("a"), runtime_trust_digest="bad")
    with pytest.raises(ValueError, match="release"):
        target.publish(fp("a"), release_evidence_digest="bad")


def test_require_current_root_optional_bindings_are_only_checked_when_requested():
    target = store()
    target.publish(
        fp("a"),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    assert target.require_current_root(fp("a")).witness.audit_root == fp("a")


def test_signature_key_mismatch_detected_after_restart():
    backend = InMemoryFencedStore()
    target = AIAuditWitnessStore(backend, signer())
    target.publish(fp("a"))
    other_signer = ArtifactSigner("other", b"z" * 32)
    restarted = AIAuditWitnessStore(backend, other_signer)
    report = restarted.verify()
    assert not report.ok
    assert any("signature invalid" in reason for reason in report.reasons)


def test_node_key_is_lexically_sequence_ordered():
    target = store()
    assert target._node_key(2) < target._node_key(10)
    assert target._node_key(10) < target._node_key(100)


def test_identical_audit_roots_still_advance_witness_sequence():
    target = store()
    first = target.publish(fp("a"))
    second = target.publish(fp("a"))
    assert second.witness.sequence == 2
    assert second.witness.previous_witness_digest == first.witness.digest
    assert second.witness.digest != first.witness.digest
