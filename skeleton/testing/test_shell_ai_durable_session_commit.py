"""Signed cross-store durable session commit tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_session_commit import (
    DurableSessionCommit,
    DurableSessionCommitBuilder,
    DurableSessionCommitConflict,
    DurableSessionCommitCorruption,
    DurableSessionCommitHead,
    DurableSessionCommitPolicy,
    DurableSessionCommitPublication,
    DurableSessionCommitStore,
    SignedDurableSessionCommit,
    StoredDurableSessionCommit,
    finalization_evidence_dict,
    finalization_evidence_digest,
)
from skeleton.shells.ai.finalization_state import (
    AIExecutionFinalization,
    FinalizationPhase,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner


def fp(char: str) -> str:
    return char * 64


def finalization(
    *,
    finalization_id="finalization",
    session_id="session",
    phase=FinalizationPhase.COMPLETE,
    updated_at=2.0,
    error_count=0,
    last_error_type="",
    last_error_at=0.0,
    session_evidence_digest=None,
    recovery_checkpoint_digest=None,
    audit_anchor_digest=None,
    audit_chain_node_hash=None,
    audit_root=None,
    audit_witness_digest=None,
    audit_witness_sequence=1,
    execution_evidence_digest=None,
    execution_evidence_chain_node_hash=None,
    runtime_trust_digest=None,
    release_evidence_digest=None,
) -> AIExecutionFinalization:
    return AIExecutionFinalization(
        schema_version=1,
        finalization_id=finalization_id,
        session_id=session_id,
        provenance_digest=fp("p"),
        phase=phase,
        created_at=1.0,
        updated_at=updated_at,
        execution_attempt_id="attempt",
        execution_attempt_authority_digest=fp("a"),
        runtime_trust_digest=(
            runtime_trust_digest or fp("t")
        ),
        release_evidence_digest=(
            release_evidence_digest or fp("r")
        ),
        require_recovery_checkpoint=True,
        require_witness=True,
        require_signed_evidence=True,
        session_evidence_digest=(
            session_evidence_digest or fp("s")
        ),
        recovery_checkpoint_digest=(
            recovery_checkpoint_digest or fp("c")
        ),
        audit_anchor_digest=(
            audit_anchor_digest or fp("d")
        ),
        audit_chain_node_hash=(
            audit_chain_node_hash or fp("n")
        ),
        audit_root=audit_root or fp("o"),
        audit_witness_digest=(
            audit_witness_digest or fp("w")
        ),
        audit_witness_sequence=audit_witness_sequence,
        execution_evidence_digest=(
            execution_evidence_digest or fp("e")
        ),
        execution_evidence_chain_node_hash=(
            execution_evidence_chain_node_hash
            or fp("x")
        ),
        error_count=error_count,
        last_error_type=last_error_type,
        last_error_at=last_error_at,
    )


def builder(
    policy: DurableSessionCommitPolicy | None = None,
) -> DurableSessionCommitBuilder:
    return DurableSessionCommitBuilder(
        policy
    )


def build_commit(
    *,
    item=None,
    commit_builder=None,
    finalization_revision=7,
    recovery_revision=3,
    session_evidence_revision=2,
    session_journal_revision=5,
    recovery_checkpoint_digest=None,
    session_evidence_digest=None,
    session_journal_digest=None,
    session_journal_manifest_digest=None,
    session_integrity_digest=None,
    journal_root=None,
    receipt_root=None,
    audit_anchor_digest=None,
    audit_chain_node_hash=None,
    audit_root=None,
    audit_witness_digest=None,
    audit_witness_sequence=1,
    execution_evidence_digest=None,
    execution_evidence_chain_node_hash=None,
):
    item = item or finalization()
    commit_builder = (
        commit_builder or builder()
    )
    return commit_builder.build(
        finalization=item,
        finalization_revision=(
            finalization_revision
        ),
        recovery_checkpoint_digest=(
            recovery_checkpoint_digest
            or item.recovery_checkpoint_digest
        ),
        recovery_revision=recovery_revision,
        session_evidence_digest=(
            session_evidence_digest
            or item.session_evidence_digest
        ),
        session_evidence_revision=(
            session_evidence_revision
        ),
        session_journal_digest=(
            session_journal_digest or fp("j")
        ),
        session_journal_manifest_digest=(
            session_journal_manifest_digest
            or fp("m")
        ),
        session_journal_revision=(
            session_journal_revision
        ),
        session_integrity_digest=(
            session_integrity_digest or fp("i")
        ),
        journal_root=(
            journal_root or fp("q")
        ),
        receipt_root=(
            receipt_root or fp("z")
        ),
        audit_anchor_digest=(
            audit_anchor_digest
            or item.audit_anchor_digest
        ),
        audit_chain_node_hash=(
            audit_chain_node_hash
            or item.audit_chain_node_hash
        ),
        audit_root=(
            audit_root or item.audit_root
        ),
        audit_witness_digest=(
            audit_witness_digest
            or item.audit_witness_digest
        ),
        audit_witness_sequence=(
            audit_witness_sequence
        ),
        execution_evidence_digest=(
            execution_evidence_digest
            or item.execution_evidence_digest
        ),
        execution_evidence_chain_node_hash=(
            execution_evidence_chain_node_hash
            or item.execution_evidence_chain_node_hash
        ),
    )


def store(
    backend=None,
    *,
    namespace="session-commit",
    key=b"k" * 32,
):
    backend = backend or InMemoryFencedStore()
    return DurableSessionCommitStore(
        backend,
        ArtifactSigner(
            "session-commit-key",
            key,
            clock=lambda: 10.0,
        ),
        namespace=namespace,
    )


def test_finalization_evidence_dict_excludes_operational_metadata():
    item = finalization(
        updated_at=5.0,
        error_count=1,
        last_error_type="RuntimeError",
        last_error_at=5.0,
    )
    data = finalization_evidence_dict(
        item
    )
    assert "updated_at" not in data
    assert "created_at" not in data
    assert "error_count" not in data
    assert "last_error_type" not in data
    assert "last_error_at" not in data
    assert data["phase"] == "complete"
    assert (
        data["finalization_id"]
        == item.finalization_id
    )


def test_finalization_evidence_digest_ignores_updated_at():
    first = finalization(updated_at=2.0)
    second = finalization(updated_at=99.0)
    assert (
        finalization_evidence_digest(first)
        == finalization_evidence_digest(second)
    )


def test_finalization_evidence_digest_ignores_error_metadata():
    first = finalization()
    second = finalization(
        updated_at=5.0,
        error_count=2,
        last_error_type="RuntimeError",
        last_error_at=5.0,
    )
    assert (
        finalization_evidence_digest(first)
        == finalization_evidence_digest(second)
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_evidence_digest", fp("u")),
        ("recovery_checkpoint_digest", fp("v")),
        ("audit_anchor_digest", fp("f")),
        ("audit_chain_node_hash", fp("g")),
        ("audit_root", fp("h")),
        ("audit_witness_digest", fp("k")),
        ("execution_evidence_digest", fp("l")),
        (
            "execution_evidence_chain_node_hash",
            fp("y"),
        ),
        ("runtime_trust_digest", fp("b")),
        ("release_evidence_digest", fp("c")),
    ],
)
def test_finalization_evidence_digest_changes_for_authority_binding(
    field,
    value,
):
    first = finalization()
    second = finalization(
        **{field: value}
    )
    assert (
        finalization_evidence_digest(first)
        != finalization_evidence_digest(second)
    )


def test_finalization_evidence_helpers_require_finalization():
    with pytest.raises(TypeError):
        finalization_evidence_dict(
            object()
        )
    with pytest.raises(TypeError):
        finalization_evidence_digest(
            object()
        )


def test_policy_default_requires_full_durable_stack():
    policy = DurableSessionCommitPolicy()
    assert policy.require_complete_finalization
    assert policy.require_recovery_checkpoint
    assert policy.require_session_journal_manifest
    assert policy.require_audit_witness
    assert policy.require_signed_execution_evidence
    assert len(policy.digest) == 64


def test_policy_digest_is_stable():
    first = DurableSessionCommitPolicy()
    second = DurableSessionCommitPolicy()
    assert first.digest == second.digest
    assert first.to_dict() == second.to_dict()


def test_policy_digest_changes_with_requirement():
    first = DurableSessionCommitPolicy()
    second = DurableSessionCommitPolicy(
        require_audit_witness=False,
    )
    assert first.digest != second.digest


@pytest.mark.parametrize(
    "field",
    [
        "require_complete_finalization",
        "require_recovery_checkpoint",
        "require_session_journal_manifest",
        "require_audit_witness",
        "require_signed_execution_evidence",
    ],
)
def test_policy_fields_must_be_bool(field):
    values = DurableSessionCommitPolicy().to_dict()
    values[field] = "yes"
    with pytest.raises(
        ValueError,
        match="bool",
    ):
        DurableSessionCommitPolicy(
            **values
        )


def test_builder_happy_path():
    commit = build_commit()
    item = finalization()
    assert commit.schema_version == 1
    assert commit.finalization_id == "finalization"
    assert commit.session_id == "session"
    assert commit.execution_attempt_id == "attempt"
    assert commit.provenance_digest == fp("p")
    assert (
        commit.finalization_evidence_digest
        == finalization_evidence_digest(item)
    )
    assert commit.recovery_checkpoint_digest == fp("c")
    assert commit.session_evidence_digest == fp("s")
    assert commit.session_journal_digest == fp("j")
    assert (
        commit.session_journal_manifest_digest
        == fp("m")
    )
    assert commit.session_integrity_digest == fp("i")
    assert commit.journal_root == fp("q")
    assert commit.receipt_root == fp("z")
    assert commit.audit_anchor_digest == fp("d")
    assert commit.audit_chain_node_hash == fp("n")
    assert commit.audit_root == fp("o")
    assert commit.audit_witness_digest == fp("w")
    assert commit.audit_witness_sequence == 1
    assert commit.execution_evidence_digest == fp("e")
    assert (
        commit.execution_evidence_chain_node_hash
        == fp("x")
    )
    assert commit.finalization_revision == 7
    assert commit.recovery_revision == 3
    assert commit.session_evidence_revision == 2
    assert commit.session_journal_revision == 5
    assert len(commit.commit_id) == 64
    assert len(commit.digest) == 64


def test_commit_authority_digest_excludes_only_finalization_revision():
    first = build_commit(
        finalization_revision=1,
    )
    second = build_commit(
        finalization_revision=10,
    )
    assert first.commit_id == second.commit_id
    assert first.digest == second.digest
    assert first.to_dict() != second.to_dict()


@pytest.mark.parametrize(
    "field,value",
    [
        ("recovery_revision", 30),
        ("session_evidence_revision", 20),
        ("session_journal_revision", 50),
    ],
)
def test_commit_authority_digest_signs_immutable_store_revisions(field, value):
    first = build_commit()
    kwargs = {field: value}
    second = build_commit(**kwargs)
    assert first.commit_id == second.commit_id
    assert first.digest != second.digest


def test_commit_id_is_policy_and_finalization_specific():
    base = build_commit()
    other_policy = build_commit(
        commit_builder=builder(
            DurableSessionCommitPolicy(
                require_audit_witness=False,
            )
        )
    )
    other_finalization = build_commit(
        item=finalization(
            finalization_id="other",
        )
    )
    assert base.commit_id != other_policy.commit_id
    assert base.commit_id != other_finalization.commit_id


def test_builder_rejects_nonfinalization():
    with pytest.raises(TypeError):
        build_commit(
            item=object()
        )


def test_builder_rejects_incomplete_finalization():
    item = finalization(
        phase=FinalizationPhase.SIGNED,
    )
    with pytest.raises(
        DurableSessionCommitConflict,
        match="complete",
    ):
        build_commit(item=item)


def test_relaxed_policy_can_bind_noncomplete_finalization():
    item = finalization(
        phase=FinalizationPhase.SIGNED,
    )
    policy = DurableSessionCommitPolicy(
        require_complete_finalization=False,
    )
    commit = build_commit(
        item=item,
        commit_builder=builder(policy),
    )
    assert (
        commit.finalization_evidence_digest
        == finalization_evidence_digest(item)
    )


def test_builder_rejects_session_evidence_mismatch():
    with pytest.raises(
        DurableSessionCommitConflict,
        match="session evidence",
    ):
        build_commit(
            session_evidence_digest=fp("u")
        )


def test_builder_rejects_recovery_mismatch():
    with pytest.raises(
        DurableSessionCommitConflict,
        match="recovery checkpoint",
    ):
        build_commit(
            recovery_checkpoint_digest=fp("u")
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"audit_anchor_digest": fp("u")},
        {"audit_chain_node_hash": fp("u")},
        {"audit_root": fp("u")},
    ],
)
def test_builder_rejects_audit_anchor_mismatch(kwargs):
    with pytest.raises(
        DurableSessionCommitConflict,
        match="audit anchor",
    ):
        build_commit(**kwargs)


def test_builder_rejects_witness_digest_mismatch():
    with pytest.raises(
        DurableSessionCommitConflict,
        match="audit witness",
    ):
        build_commit(
            audit_witness_digest=fp("u")
        )


def test_builder_rejects_witness_sequence_mismatch():
    with pytest.raises(
        DurableSessionCommitConflict,
        match="audit witness",
    ):
        build_commit(
            audit_witness_sequence=2
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"execution_evidence_digest": fp("u")},
        {
            "execution_evidence_chain_node_hash":
            fp("u")
        },
    ],
)
def test_builder_rejects_execution_evidence_mismatch(kwargs):
    with pytest.raises(
        DurableSessionCommitConflict,
        match="signed execution evidence",
    ):
        build_commit(**kwargs)


def test_strong_policy_requires_recovery_revision():
    with pytest.raises(
        DurableSessionCommitConflict,
        match="durably stored recovery",
    ):
        build_commit(
            recovery_revision=None
        )


def test_strong_policy_requires_session_journal_revision():
    with pytest.raises(
        DurableSessionCommitConflict,
        match="session-journal",
    ):
        build_commit(
            session_journal_revision=None
        )


def test_strong_policy_requires_session_journal_manifest_digest():
    with pytest.raises(
        DurableSessionCommitConflict,
        match="session-journal",
    ):
        build_commit(
            session_journal_manifest_digest=""
        )


def test_strong_policy_requires_witness():
    item = finalization(
        audit_witness_digest="",
        audit_witness_sequence=None,
    )
    with pytest.raises(
        DurableSessionCommitConflict,
        match="witness",
    ):
        build_commit(
            item=item,
            audit_witness_digest="",
            audit_witness_sequence=None,
        )


def test_strong_policy_requires_signed_execution_evidence():
    item = finalization(
        execution_evidence_digest="",
        execution_evidence_chain_node_hash="",
    )
    with pytest.raises(
        DurableSessionCommitConflict,
        match="signed execution evidence",
    ):
        build_commit(
            item=item,
            execution_evidence_digest="",
            execution_evidence_chain_node_hash="",
        )


def test_relaxed_policy_allows_optional_durable_layers():
    item = finalization(
        audit_witness_digest="",
        audit_witness_sequence=None,
        execution_evidence_digest="",
        execution_evidence_chain_node_hash="",
    )
    policy = DurableSessionCommitPolicy(
        require_recovery_checkpoint=False,
        require_session_journal_manifest=False,
        require_audit_witness=False,
        require_signed_execution_evidence=False,
    )
    commit = build_commit(
        item=item,
        commit_builder=builder(policy),
        recovery_revision=None,
        session_journal_manifest_digest="",
        session_journal_revision=None,
        audit_witness_digest="",
        audit_witness_sequence=None,
        execution_evidence_digest="",
        execution_evidence_chain_node_hash="",
    )
    assert commit.recovery_revision is None
    assert commit.session_journal_revision is None
    assert commit.audit_witness_digest == ""
    assert commit.execution_evidence_digest == ""


def test_signed_commit_validates_artifact_type():
    commit = build_commit()
    signer = ArtifactSigner(
        "key",
        b"k" * 32,
        clock=lambda: 1.0,
    )
    signed = signer.sign(
        "wrong",
        commit.digest,
    )
    with pytest.raises(
        ValueError,
        match="artifact type",
    ):
        SignedDurableSessionCommit(
            commit,
            signed,
        )


def test_signed_commit_validates_artifact_digest():
    commit = build_commit()
    signer = ArtifactSigner(
        "key",
        b"k" * 32,
        clock=lambda: 1.0,
    )
    signed = signer.sign(
        "ai-durable-session-commit",
        fp("u"),
    )
    with pytest.raises(
        ValueError,
        match="signature digest",
    ):
        SignedDurableSessionCommit(
            commit,
            signed,
        )


def test_store_publish_and_require():
    target = store()
    commit = build_commit()
    publication = target.publish(
        commit
    )
    assert publication.head_created
    assert publication.stored.revision == 1
    assert publication.head_revision == 1
    assert (
        publication.stored.signed.commit
        == commit
    )
    assert target.verify(
        commit.finalization_id
    )
    required = target.require(
        commit.finalization_id,
        commit_digest=commit.digest,
    )
    assert required == publication.stored


def test_store_publish_is_idempotent():
    target = store()
    commit = build_commit()
    first = target.publish(commit)
    second = target.publish(commit)
    assert second.stored == first.stored
    assert second.head == first.head
    assert second.head_revision == first.head_revision
    assert not second.head_created


def test_store_publish_preserves_original_signature_on_retry():
    backend = InMemoryFencedStore()
    target = store(backend)
    commit = build_commit()
    first = target.publish(commit)
    second = target.publish(commit)
    assert (
        second.stored.signed.signature
        == first.stored.signed.signature
    )


def test_store_rejects_conflicting_finalization_commit():
    target = store()
    first = build_commit()
    target.publish(first)
    second = replace(
        first,
        session_integrity_digest=fp("u"),
    )
    with pytest.raises(
        DurableSessionCommitConflict,
        match="different session commit",
    ):
        target.publish(second)


def test_session_head_prevents_second_finalization_for_same_session():
    target = store()
    first = build_commit()
    target.publish(first)
    second = build_commit(
        item=finalization(
            finalization_id="other-finalization",
        )
    )
    with pytest.raises(
        DurableSessionCommitConflict,
        match="session already binds",
    ):
        target.publish(second)


def test_different_sessions_publish_independently():
    target = store()
    first = build_commit()
    second = build_commit(
        item=finalization(
            finalization_id="f2",
            session_id="session-2",
        )
    )
    first_pub = target.publish(first)
    second_pub = target.publish(second)
    assert first_pub.head.session_id == "session"
    assert second_pub.head.session_id == "session-2"
    assert (
        target.require_session("session")
        .signed.commit
        == first
    )
    assert (
        target.require_session("session-2")
        .signed.commit
        == second
    )


def test_require_session_resolves_commit():
    target = store()
    commit = build_commit()
    target.publish(commit)
    stored = target.require_session(
        commit.session_id
    )
    assert stored.signed.commit == commit


def test_require_missing_commit():
    target = store()
    with pytest.raises(
        DurableSessionCommitConflict,
        match="missing",
    ):
        target.require("missing")


def test_require_missing_session_head():
    target = store()
    with pytest.raises(
        DurableSessionCommitConflict,
        match="head is missing",
    ):
        target.require_session("missing")


def test_require_checks_commit_digest():
    target = store()
    commit = build_commit()
    target.publish(commit)
    with pytest.raises(
        DurableSessionCommitConflict,
        match="digest mismatch",
    ):
        target.require(
            commit.finalization_id,
            commit_digest=fp("u"),
        )


def test_head_repair_recovers_post_commit_crash_window():
    backend = InMemoryFencedStore()
    target = store(backend)
    commit = build_commit()
    publication = target.publish(commit)
    head_key = target._head_key(
        commit.session_id
    )
    head_record = backend.get(
        target.namespace,
        head_key,
    )
    backend.delete(
        target.namespace,
        head_key,
        expected_revision=head_record.revision,
    )
    assert target.head(
        commit.session_id
    ) is None

    repaired = target.repair_head(
        commit.finalization_id
    )
    assert repaired.head_created
    assert repaired.stored == publication.stored
    assert target.verify(
        commit.finalization_id
    )


def test_publish_repairs_missing_head_automatically():
    backend = InMemoryFencedStore()
    target = store(backend)
    commit = build_commit()
    first = target.publish(commit)
    head_key = target._head_key(
        commit.session_id
    )
    head_record = backend.get(
        target.namespace,
        head_key,
    )
    backend.delete(
        target.namespace,
        head_key,
        expected_revision=head_record.revision,
    )
    second = target.publish(commit)
    assert second.head_created
    assert second.stored == first.stored


def test_repair_head_requires_commit_record():
    target = store()
    with pytest.raises(
        DurableSessionCommitConflict,
        match="without commit",
    ):
        target.repair_head("missing")


def test_signature_tamper_is_corruption():
    backend = InMemoryFencedStore()
    target = store(backend)
    commit = build_commit()
    publication = target.publish(commit)
    key = target._commit_key(
        commit.finalization_id
    )
    record = backend.get(
        target.namespace,
        key,
    )
    tampered_signature = replace(
        publication.stored.signed.signature,
        signature="0" * 64,
    )
    tampered = replace(
        publication.stored.signed,
        signature=tampered_signature,
    )
    backend.compare_and_swap(
        target.namespace,
        key,
        expected_revision=record.revision,
        value=tampered,
    )
    with pytest.raises(
        DurableSessionCommitCorruption,
        match="signature",
    ):
        target.get(
            commit.finalization_id
        )
    assert not target.verify(
        commit.finalization_id
    )


def test_commit_payload_tamper_is_corruption():
    backend = InMemoryFencedStore()
    target = store(backend)
    commit = build_commit()
    publication = target.publish(commit)
    key = target._commit_key(
        commit.finalization_id
    )
    record = backend.get(
        target.namespace,
        key,
    )
    tampered_commit = replace(
        commit,
        session_integrity_digest=fp("u"),
    )
    tampered = SignedDurableSessionCommit(
        tampered_commit,
        publication.stored.signed.signature,
    )
    backend.compare_and_swap(
        target.namespace,
        key,
        expected_revision=record.revision,
        value=tampered,
    )
    with pytest.raises(
        (
            ValueError,
            DurableSessionCommitCorruption,
        )
    ):
        target.get(
            commit.finalization_id
        )


def test_wrong_commit_backend_type_is_corruption():
    backend = InMemoryFencedStore()
    target = store(backend)
    backend.put_if_absent(
        target.namespace,
        target._commit_key("finalization"),
        {"bad": True},
    )
    with pytest.raises(
        DurableSessionCommitCorruption,
        match="value type",
    ):
        target.get("finalization")


def test_wrong_head_backend_type_is_corruption():
    backend = InMemoryFencedStore()
    target = store(backend)
    backend.put_if_absent(
        target.namespace,
        target._head_key("session"),
        {"bad": True},
    )
    with pytest.raises(
        DurableSessionCommitCorruption,
        match="head backend",
    ):
        target.head("session")


def test_head_missing_record_is_corruption():
    backend = InMemoryFencedStore()
    target = store(backend)
    commit = build_commit()
    head = DurableSessionCommitHead(
        commit.session_id,
        commit.finalization_id,
        commit.commit_id,
        commit.digest,
    )
    backend.put_if_absent(
        target.namespace,
        target._head_key(
            commit.session_id
        ),
        head,
    )
    with pytest.raises(
        DurableSessionCommitCorruption,
        match="missing record",
    ):
        target.require_session(
            commit.session_id
        )


def test_require_detects_missing_head_after_commit():
    backend = InMemoryFencedStore()
    target = store(backend)
    commit = build_commit()
    publication = target.publish(commit)
    key = target._head_key(
        commit.session_id
    )
    record = backend.get(
        target.namespace,
        key,
    )
    backend.delete(
        target.namespace,
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DurableSessionCommitCorruption,
        match="head is missing",
    ):
        target.require(
            commit.finalization_id
        )
    assert publication.stored.signed.commit == commit


def test_require_detects_head_commit_digest_tamper():
    backend = InMemoryFencedStore()
    target = store(backend)
    commit = build_commit()
    target.publish(commit)
    key = target._head_key(
        commit.session_id
    )
    record = backend.get(
        target.namespace,
        key,
    )
    tampered = replace(
        record.value,
        commit_digest=fp("u"),
    )
    backend.compare_and_swap(
        target.namespace,
        key,
        expected_revision=record.revision,
        value=tampered,
    )
    with pytest.raises(
        DurableSessionCommitCorruption,
        match="differs",
    ):
        target.require(
            commit.finalization_id
        )


def test_store_rejects_wrong_signer_on_read():
    backend = InMemoryFencedStore()
    first = store(
        backend,
        key=b"a" * 32,
    )
    commit = build_commit()
    first.publish(commit)
    second = store(
        backend,
        key=b"b" * 32,
    )
    with pytest.raises(
        DurableSessionCommitCorruption,
        match="signature",
    ):
        second.get(
            commit.finalization_id
        )


def test_store_namespace_validation():
    with pytest.raises(
        ValueError,
        match="namespace",
    ):
        store(namespace="")


def test_store_signer_validation():
    with pytest.raises(
        TypeError,
        match="signer",
    ):
        DurableSessionCommitStore(
            InMemoryFencedStore(),
            object(),
        )


def test_publish_type_validation():
    target = store()
    with pytest.raises(
        TypeError,
        match="DurableSessionCommit",
    ):
        target.publish(object())


def test_commit_key_hides_finalization_identity():
    key = DurableSessionCommitStore._commit_key(
        "sensitive-finalization"
    )
    assert key.startswith("commit:")
    assert "sensitive-finalization" not in key
    assert key == DurableSessionCommitStore._commit_key(
        "sensitive-finalization"
    )


def test_head_key_hides_session_identity():
    key = DurableSessionCommitStore._head_key(
        "sensitive-session"
    )
    assert key.startswith("head:")
    assert "sensitive-session" not in key
    assert key == DurableSessionCommitStore._head_key(
        "sensitive-session"
    )


def test_commit_to_dict_separates_operational_finalization_revision():
    commit = build_commit()
    data = commit.to_dict()
    authority = commit.authority_dict
    assert "finalization_revision" not in authority
    assert authority["recovery_revision"] == 3
    assert authority["session_evidence_revision"] == 2
    assert authority["session_journal_revision"] == 5
    assert data["finalization_revision"] == 7
    assert data["recovery_revision"] == 3
    assert data["session_evidence_revision"] == 2
    assert data["session_journal_revision"] == 5
    assert data["digest"] == commit.digest


def test_signed_commit_to_dict():
    target = store()
    commit = build_commit()
    publication = target.publish(commit)
    data = publication.stored.signed.to_dict()
    assert data["commit"]["commit_id"] == commit.commit_id
    assert data["commit_digest"] == commit.digest
    assert data["signature"]["artifact_type"] == (
        "ai-durable-session-commit"
    )


def test_publication_to_dict():
    target = store()
    commit = build_commit()
    publication = target.publish(commit)
    data = publication.to_dict()
    assert data["head_created"] is True
    assert data["head"]["session_id"] == "session"
    assert data["stored"]["revision"] == 1


def test_head_to_dict():
    commit = build_commit()
    head = DurableSessionCommitHead(
        commit.session_id,
        commit.finalization_id,
        commit.commit_id,
        commit.digest,
    )
    assert head.to_dict() == {
        "session_id": "session",
        "finalization_id": "finalization",
        "commit_id": commit.commit_id,
        "commit_digest": commit.digest,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("commit_id", "bad"),
        ("finalization_id", ""),
        ("session_id", ""),
        ("provenance_digest", "bad"),
        ("finalization_evidence_digest", "bad"),
        ("session_evidence_digest", "bad"),
        ("session_journal_digest", "bad"),
        ("session_integrity_digest", "bad"),
        ("journal_root", "bad"),
        ("receipt_root", "bad"),
        ("audit_anchor_digest", "bad"),
        ("audit_chain_node_hash", "bad"),
        ("audit_root", "bad"),
        ("policy_digest", "bad"),
        ("finalization_revision", 0),
        ("session_evidence_revision", 0),
    ],
)
def test_commit_validation(field, value):
    commit = build_commit()
    values = dict(commit.__dict__)
    values[field] = value
    with pytest.raises(ValueError):
        DurableSessionCommit(**values)


def test_commit_rejects_derived_id_mismatch():
    commit = build_commit()
    with pytest.raises(
        ValueError,
        match="commit_id",
    ):
        replace(
            commit,
            commit_id=fp("u"),
        )


@pytest.mark.parametrize(
    "revision_name",
    [
        "recovery_revision",
        "session_journal_revision",
    ],
)
def test_optional_revision_validation(revision_name):
    commit = build_commit()
    with pytest.raises(ValueError):
        replace(
            commit,
            **{revision_name: 0},
        )


@pytest.mark.parametrize(
    "digest_name",
    [
        "recovery_checkpoint_digest",
        "session_journal_manifest_digest",
        "audit_witness_digest",
        "execution_evidence_digest",
        "execution_evidence_chain_node_hash",
        "runtime_trust_digest",
        "release_evidence_digest",
    ],
)
def test_optional_digest_validation(digest_name):
    commit = build_commit()
    with pytest.raises(ValueError):
        replace(
            commit,
            **{digest_name: "bad"},
        )


def test_witness_digest_requires_sequence():
    commit = build_commit()
    with pytest.raises(ValueError):
        replace(
            commit,
            audit_witness_sequence=None,
        )


def test_witness_sequence_requires_digest():
    policy = DurableSessionCommitPolicy(
        require_audit_witness=False,
    )
    item = finalization(
        audit_witness_digest="",
        audit_witness_sequence=None,
    )
    commit = build_commit(
        item=item,
        commit_builder=builder(policy),
        audit_witness_digest="",
        audit_witness_sequence=None,
    )
    with pytest.raises(ValueError):
        replace(
            commit,
            audit_witness_sequence=1,
        )


def test_publication_validation_detects_session_mismatch():
    target = store()
    commit = build_commit()
    publication = target.publish(commit)
    bad_head = replace(
        publication.head,
        session_id="other",
    )
    with pytest.raises(ValueError, match="session mismatch"):
        DurableSessionCommitPublication(
            publication.stored,
            publication.head_revision,
            bad_head,
            publication.head_created,
        )


def test_stored_commit_revision_validation():
    target = store()
    commit = build_commit()
    publication = target.publish(commit)
    with pytest.raises(ValueError):
        StoredDurableSessionCommit(
            0,
            publication.stored.signed,
        )


def test_verify_returns_false_for_missing():
    assert not store().verify(
        "missing"
    )


def test_operational_finalization_update_does_not_change_commit_authority():
    original = finalization()
    commit = build_commit(item=original)
    updated = finalization(
        updated_at=20.0,
        error_count=1,
        last_error_type="RuntimeError",
        last_error_at=20.0,
    )
    rebuilt = build_commit(
        item=updated,
        finalization_revision=99,
    )
    assert (
        rebuilt.finalization_evidence_digest
        == commit.finalization_evidence_digest
    )
    assert rebuilt.commit_id == commit.commit_id
    assert rebuilt.digest == commit.digest


def test_semantic_finalization_change_changes_commit_authority():
    original = build_commit()
    changed_item = finalization(
        runtime_trust_digest=fp("u"),
    )
    changed = build_commit(
        item=changed_item,
    )
    assert (
        changed.finalization_evidence_digest
        != original.finalization_evidence_digest
    )
    assert changed.commit_id != original.commit_id
    assert changed.digest != original.digest
