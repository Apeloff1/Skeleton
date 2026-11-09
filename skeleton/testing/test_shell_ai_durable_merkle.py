"""Signed durable Merkle checkpoint and inclusion-proof tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_merkle import (
    DurableMerkleAuthority,
    DurableMerkleChainKind,
    DurableMerkleCheckpoint,
    DurableMerkleError,
    DurableMerkleLeaf,
    DurableMerkleProof,
    DurableMerkleProofStep,
    DurableMerkleSide,
    MERKLE_ALGORITHM,
    MERKLE_CHECKPOINT_ARTIFACT,
    SignedDurableMerkleCheckpoint,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
)
from skeleton.shells.receipts import ExecutionReceipt


def fp(char: str) -> str:
    return char * 64


def signer(
    *,
    key_id="merkle",
    key_char=b"k",
    clock=lambda: 100.0,
) -> ArtifactSigner:
    return ArtifactSigner(
        key_id,
        key_char * 32,
        clock=clock,
    )


def authority(
    *,
    key_id="merkle",
    key_char=b"k",
    max_leaves=1_000_000,
) -> DurableMerkleAuthority:
    return DurableMerkleAuthority(
        signer(
            key_id=key_id,
            key_char=key_char,
        ),
        max_leaves=max_leaves,
    )


def journal_fixture(
    count: int,
    *,
    namespace="journal",
):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace=namespace,
        clock=lambda: 10.0,
    )
    events = []
    for index in range(1, count + 1):
        events.append(
            journal.append(
                f"event.{index}",
                session_id=(
                    "session-a"
                    if index % 2
                    else "session-b"
                ),
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
                summary=f"event {index}",
                data={"index": index},
            )
        )
    return backend, journal, tuple(events)


def receipt_value(
    index: int,
    *,
    receipt_id=None,
    fingerprint=None,
) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{index}",
        fingerprint=(
            fingerprint
            or f"{index:064x}"
        ),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=index,
        stderr_bytes=0,
        attempt=1,
        receipt_id=(
            receipt_id
            or f"receipt-{index}"
        ),
        metadata={"index": index},
    )


def receipt_fixture(
    count: int,
    *,
    namespace="receipts",
):
    backend = InMemoryFencedStore()
    chain = DistributedReceiptChain(
        backend,
        namespace=namespace,
    )
    nodes = []
    for index in range(1, count + 1):
        nodes.append(
            chain.append(
                receipt_value(index)
            )
        )
    return backend, chain, tuple(nodes)


def test_journal_checkpoint_single_leaf():
    _, journal, events = journal_fixture(1)
    signed, leaves = authority().build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    assert len(leaves) == 1
    assert signed.checkpoint.sequence_count == 1
    assert (
        signed.checkpoint.chain_root
        == events[0].event_hash
    )
    assert (
        signed.checkpoint.merkle_root
        == leaves[0].leaf_hash
    )
    assert signed.checkpoint.algorithm == MERKLE_ALGORITHM


def test_receipt_checkpoint_single_leaf():
    _, chain, nodes = receipt_fixture(1)
    signed, leaves = authority().build(
        chain,
        chain_id="receipts-main",
        chain_kind=DurableMerkleChainKind.RECEIPTS,
    )
    assert len(leaves) == 1
    assert leaves[0].subject_id == "receipt-1"
    assert (
        leaves[0].payload_fingerprint
        == nodes[0].receipt.fingerprint
    )
    assert (
        leaves[0].item_hash
        == nodes[0].receipt_hash
    )


@pytest.mark.parametrize(
    "count",
    [1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17],
)
def test_every_journal_leaf_can_be_proven(count):
    _, journal, events = journal_fixture(
        count
    )
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    for sequence in range(1, count + 1):
        proof = auth.prove(
            signed,
            leaves,
            sequence=sequence,
        )
        report = auth.require_proof(
            signed,
            proof,
            expected_subject_id=(
                events[sequence - 1].event_hash
            ),
            expected_payload_fingerprint=(
                events[sequence - 1].event_hash
            ),
            chain=journal,
        )
        assert report.ok
        assert (
            report.reconstructed_root
            == signed.checkpoint.merkle_root
        )


@pytest.mark.parametrize(
    "count",
    [1, 2, 3, 5, 6, 7, 10],
)
def test_every_receipt_leaf_can_be_proven(count):
    _, chain, nodes = receipt_fixture(
        count
    )
    auth = authority()
    signed, leaves = auth.build(
        chain,
        chain_id="receipts-main",
        chain_kind=DurableMerkleChainKind.RECEIPTS,
    )
    for sequence in range(1, count + 1):
        node = nodes[sequence - 1]
        proof = auth.prove(
            signed,
            leaves,
            sequence=sequence,
        )
        report = auth.require_proof(
            signed,
            proof,
            expected_subject_id=(
                node.receipt.receipt_id
            ),
            expected_payload_fingerprint=(
                node.receipt.fingerprint
            ),
            chain=chain,
        )
        assert report.ok


def test_odd_width_tree_uses_duplicate_right_sibling():
    _, journal, _ = journal_fixture(3)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=3,
    )
    assert proof.siblings[0].duplicated
    assert (
        proof.siblings[0].sibling_side
        is DurableMerkleSide.RIGHT
    )
    assert (
        proof.siblings[0].sibling_hash
        == proof.leaf.leaf_hash
    )
    assert auth.require_proof(
        signed,
        proof,
    ).ok


def test_even_width_tree_does_not_need_leaf_duplication():
    _, journal, _ = journal_fixture(4)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    for sequence in range(1, 5):
        proof = auth.prove(
            signed,
            leaves,
            sequence=sequence,
        )
        assert not proof.siblings[0].duplicated


def test_checkpoint_signature_verifies():
    _, journal, _ = journal_fixture(2)
    auth = authority()
    signed, _ = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    auth.verify_checkpoint_signature(
        signed
    )


def test_checkpoint_signature_tamper_rejected():
    _, journal, _ = journal_fixture(2)
    auth = authority()
    signed, _ = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    tampered_signature = replace(
        signed.signature,
        signature="f" * 64,
    )
    tampered = SignedDurableMerkleCheckpoint(
        signed.checkpoint,
        tampered_signature,
    )
    with pytest.raises(
        DurableMerkleError,
        match="signature verification",
    ):
        auth.verify_checkpoint_signature(
            tampered
        )


def test_checkpoint_wrong_signing_key_rejected():
    _, journal, _ = journal_fixture(2)
    first = authority(
        key_id="one",
        key_char=b"a",
    )
    signed, _ = first.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    second = authority(
        key_id="two",
        key_char=b"b",
    )
    with pytest.raises(
        DurableMerkleError,
        match="signature verification",
    ):
        second.verify_checkpoint_signature(
            signed
        )


def test_checkpoint_against_chain_is_true():
    _, journal, _ = journal_fixture(5)
    auth = authority()
    signed, _ = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    assert auth.verify_checkpoint_against_chain(
        signed,
        journal,
    )


def test_checkpoint_remains_valid_after_chain_growth():
    _, journal, _ = journal_fixture(3)
    auth = authority()
    signed, _ = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    old_root = signed.checkpoint.chain_root
    journal.append(
        "later",
        session_id="later",
        intent_id="later",
    )
    assert journal.root_hash() != old_root
    assert journal.root_is_ancestor(
        old_root
    )
    assert auth.verify_checkpoint_against_chain(
        signed,
        journal,
    )


def test_historical_checkpoint_can_be_built_after_growth():
    _, journal, events = journal_fixture(3)
    old_root = events[1].event_hash
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
        root_hash=old_root,
    )
    assert signed.checkpoint.sequence_count == 2
    assert len(leaves) == 2
    assert signed.checkpoint.chain_root == old_root


def test_receipt_historical_checkpoint_after_growth():
    _, chain, nodes = receipt_fixture(5)
    root = nodes[2].receipt_hash
    signed, leaves = authority().build(
        chain,
        chain_id="receipts-main",
        chain_kind=DurableMerkleChainKind.RECEIPTS,
        root_hash=root,
    )
    assert signed.checkpoint.sequence_count == 3
    assert len(leaves) == 3
    assert signed.checkpoint.chain_root == root


def test_orphan_journal_root_cannot_be_checkpointed():
    backend, journal, events = journal_fixture(
        2
    )
    head = journal.head()
    from types import MappingProxyType
    from skeleton.shells.ai.journal import (
        AIDecisionEvent,
        AIDecisionJournal,
    )

    data = MappingProxyType({})
    orphan_hash = AIDecisionJournal._hash(
        head.root_hash,
        head.sequence + 1,
        "orphan",
        20.0,
        "orphan-session",
        "orphan-intent",
        "",
        "",
        data,
    )
    orphan = AIDecisionEvent(
        head.sequence + 1,
        head.root_hash,
        orphan_hash,
        "orphan",
        20.0,
        "orphan-session",
        "orphan-intent",
        "",
        "",
        data,
    )
    backend.put_if_absent(
        journal.namespace,
        journal._event_key(orphan_hash),
        orphan,
    )
    assert journal.verify_root(
        orphan_hash
    )
    assert not journal.root_is_ancestor(
        orphan_hash
    )
    with pytest.raises(
        DurableMerkleError,
        match="not committed ancestor",
    ):
        authority().build(
            journal,
            chain_id="journal-main",
            chain_kind=DurableMerkleChainKind.JOURNAL,
            root_hash=orphan_hash,
        )


def test_orphan_receipt_root_cannot_be_checkpointed():
    backend, chain, nodes = receipt_fixture(
        2
    )
    from skeleton.shells.receipts import (
        ChainedReceipt,
        ReceiptChain,
    )

    value = receipt_value(99)
    head = chain.head()
    orphan_hash = ReceiptChain._hash(
        head.root_hash,
        head.sequence + 1,
        value,
    )
    orphan = ChainedReceipt(
        head.sequence + 1,
        head.root_hash,
        orphan_hash,
        value,
    )
    backend.put_if_absent(
        chain.namespace,
        chain._node_key(orphan_hash),
        orphan,
    )
    assert chain.verify_root(
        orphan_hash
    )
    assert not chain.root_is_ancestor(
        orphan_hash
    )
    with pytest.raises(
        DurableMerkleError,
        match="not committed ancestor",
    ):
        authority().build(
            chain,
            chain_id="receipts-main",
            chain_kind=DurableMerkleChainKind.RECEIPTS,
            root_hash=orphan_hash,
        )


def test_proof_wrong_subject_rejected():
    _, chain, _ = receipt_fixture(3)
    auth = authority()
    signed, leaves = auth.build(
        chain,
        chain_id="receipts-main",
        chain_kind=DurableMerkleChainKind.RECEIPTS,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=2,
    )
    report = auth.inspect_proof(
        signed,
        proof,
        expected_subject_id="wrong",
    )
    assert not report.ok
    assert not report.subject_matches
    assert any(
        "subject identity" in issue
        for issue in report.issues
    )


def test_proof_wrong_payload_fingerprint_rejected():
    _, chain, _ = receipt_fixture(3)
    auth = authority()
    signed, leaves = auth.build(
        chain,
        chain_id="receipts-main",
        chain_kind=DurableMerkleChainKind.RECEIPTS,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=2,
    )
    report = auth.inspect_proof(
        signed,
        proof,
        expected_payload_fingerprint=fp("f"),
    )
    assert not report.ok
    assert not report.payload_matches


def test_proof_sibling_hash_tamper_rejected():
    _, journal, _ = journal_fixture(4)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=2,
    )
    bad_step = replace(
        proof.siblings[0],
        sibling_hash=fp("f"),
    )
    bad = replace(
        proof,
        siblings=(
            bad_step,
            *proof.siblings[1:],
        ),
    )
    report = auth.inspect_proof(
        signed,
        bad,
    )
    assert not report.ok
    assert not report.proof_valid
    assert any(
        "reconstructed root mismatch" in issue
        for issue in report.issues
    )


def test_proof_sibling_direction_tamper_rejected():
    _, journal, _ = journal_fixture(4)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=2,
    )
    step = proof.siblings[0]
    bad_side = (
        DurableMerkleSide.RIGHT
        if step.sibling_side
        is DurableMerkleSide.LEFT
        else DurableMerkleSide.LEFT
    )
    bad = replace(
        proof,
        siblings=(
            replace(
                step,
                sibling_side=bad_side,
            ),
            *proof.siblings[1:],
        ),
    )
    assert not auth.inspect_proof(
        signed,
        bad,
    ).ok


def test_proof_duplicate_flag_tamper_rejected():
    _, journal, _ = journal_fixture(3)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=3,
    )
    assert proof.siblings[0].duplicated
    bad = replace(
        proof,
        siblings=(
            replace(
                proof.siblings[0],
                duplicated=False,
            ),
            *proof.siblings[1:],
        ),
    )
    report = auth.inspect_proof(
        signed,
        bad,
    )
    assert report.ok


def test_false_duplicate_flag_on_real_sibling_rejected():
    _, journal, _ = journal_fixture(4)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=1,
    )
    assert not proof.siblings[0].duplicated
    bad = replace(
        proof,
        siblings=(
            replace(
                proof.siblings[0],
                duplicated=True,
            ),
            *proof.siblings[1:],
        ),
    )
    report = auth.inspect_proof(
        signed,
        bad,
    )
    assert not report.ok
    assert not report.proof_valid


def test_detached_proof_checkpoint_digest_rejected():
    _, journal, _ = journal_fixture(3)
    auth = authority()
    first, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        first,
        leaves,
        sequence=2,
    )
    second_auth = DurableMerkleAuthority(
        ArtifactSigner(
            "merkle",
            b"k" * 32,
            clock=lambda: 200.0,
        )
    )
    second, _ = second_auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    assert (
        first.checkpoint.digest
        == second.checkpoint.digest
    )
    assert first.digest != second.digest
    report = second_auth.inspect_proof(
        second,
        proof,
    )
    assert not report.ok
    assert any(
        "checkpoint digest mismatch" in issue
        for issue in report.issues
    )


def test_proof_wrong_chain_id_rejected_by_dataclass():
    _, journal, _ = journal_fixture(2)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=1,
    )
    with pytest.raises(
        ValueError,
        match="chain_id",
    ):
        replace(
            proof,
            chain_id="other-chain",
        )


def test_proof_wrong_chain_kind_rejected_by_dataclass():
    _, journal, _ = journal_fixture(2)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=1,
    )
    with pytest.raises(
        ValueError,
        match="chain kind",
    ):
        replace(
            proof,
            chain_kind=DurableMerkleChainKind.RECEIPTS,
        )


def test_proof_tree_size_mismatch_checkpoint_rejected():
    _, journal, _ = journal_fixture(4)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=1,
    )
    bad = replace(
        proof,
        tree_size=3,
    )
    report = auth.inspect_proof(
        signed,
        bad,
    )
    assert not report.ok
    assert any(
        "tree size mismatch" in issue
        for issue in report.issues
    )


def test_prove_rejects_leaf_digest_substitution():
    _, journal, _ = journal_fixture(3)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    bad_leaf = replace(
        leaves[0],
        subject_id="different",
        leaf_hash=DurableMerkleLeaf.compute_hash(
            chain_id=leaves[0].chain_id,
            chain_kind=leaves[0].chain_kind,
            sequence=leaves[0].sequence,
            item_hash=leaves[0].item_hash,
            previous_hash=leaves[0].previous_hash,
            subject_id="different",
            payload_fingerprint=(
                leaves[0].payload_fingerprint
            ),
        ),
    )
    bad_leaves = (
        bad_leaf,
        *leaves[1:],
    )
    with pytest.raises(
        DurableMerkleError,
        match="leaves digest",
    ):
        auth.prove(
            signed,
            bad_leaves,
            sequence=1,
        )


def test_prove_rejects_wrong_leaf_count():
    _, journal, _ = journal_fixture(3)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    with pytest.raises(
        DurableMerkleError,
        match="length differs",
    ):
        auth.prove(
            signed,
            leaves[:2],
            sequence=1,
        )


def test_prove_rejects_sequence_outside_checkpoint():
    _, journal, _ = journal_fixture(3)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    with pytest.raises(
        DurableMerkleError,
        match="outside checkpoint",
    ):
        auth.prove(
            signed,
            leaves,
            sequence=4,
        )


def test_proofs_for_sequences_deduplicates_requests():
    _, journal, _ = journal_fixture(5)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proofs = auth.proofs_for_sequences(
        signed,
        leaves,
        [3, 1, 3, 5, 1],
    )
    assert [
        proof.sequence
        for proof in proofs
    ] == [3, 1, 5]


def test_merkle_root_changes_when_leaf_order_changes():
    _, journal, _ = journal_fixture(3)
    auth = authority()
    _, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    assert auth.merkle_root(
        leaves
    ) != auth.merkle_root(
        tuple(reversed(leaves))
    )


def test_leaves_digest_changes_when_leaf_order_changes():
    _, journal, _ = journal_fixture(3)
    auth = authority()
    _, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    assert auth.leaves_digest(
        leaves
    ) != auth.leaves_digest(
        tuple(reversed(leaves))
    )


def test_empty_merkle_root_is_stable():
    auth = authority()
    assert len(auth.empty_root()) == 64
    assert auth.empty_root() == auth.empty_root()
    assert auth.merkle_root(()) == auth.empty_root()


def test_empty_chain_cannot_be_checkpointed():
    journal = DistributedAIDecisionJournal(
        InMemoryFencedStore()
    )
    with pytest.raises(
        DurableMerkleError,
        match="empty",
    ):
        authority().build(
            journal,
            chain_id="journal-main",
            chain_kind=DurableMerkleChainKind.JOURNAL,
        )


def test_leaf_bound_is_enforced():
    _, journal, _ = journal_fixture(3)
    with pytest.raises(
        DurableMerkleError,
        match="leaf bound",
    ):
        authority(
            max_leaves=2,
        ).build(
            journal,
            chain_id="journal-main",
            chain_kind=DurableMerkleChainKind.JOURNAL,
        )


def test_authority_requires_signer():
    with pytest.raises(
        TypeError,
        match="ArtifactSigner",
    ):
        DurableMerkleAuthority(
            object()
        )


@pytest.mark.parametrize(
    "maximum",
    [0, -1, True, 1.2],
)
def test_authority_leaf_bound_validation(maximum):
    with pytest.raises(
        ValueError,
        match="max_leaves",
    ):
        DurableMerkleAuthority(
            signer(),
            max_leaves=maximum,
        )


def test_leaf_hash_detects_subject_mutation():
    leaf = DurableMerkleLeaf.create(
        chain_id="chain",
        chain_kind=DurableMerkleChainKind.JOURNAL,
        sequence=1,
        item_hash=fp("a"),
        previous_hash=fp("b"),
        subject_id="subject",
        payload_fingerprint=fp("c"),
    )
    with pytest.raises(
        ValueError,
        match="leaf hash",
    ):
        replace(
            leaf,
            subject_id="other",
        )


def test_leaf_hash_detects_payload_mutation():
    leaf = DurableMerkleLeaf.create(
        chain_id="chain",
        chain_kind=DurableMerkleChainKind.RECEIPTS,
        sequence=1,
        item_hash=fp("a"),
        previous_hash=fp("b"),
        subject_id="receipt",
        payload_fingerprint=fp("c"),
    )
    with pytest.raises(
        ValueError,
        match="leaf hash",
    ):
        replace(
            leaf,
            payload_fingerprint=fp("d"),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("chain_id", ""),
        ("sequence", 0),
        ("item_hash", "bad"),
        ("previous_hash", "bad"),
        ("subject_id", ""),
        ("payload_fingerprint", "bad"),
        ("leaf_hash", "bad"),
    ],
)
def test_leaf_validation(field, value):
    values = dict(
        chain_id="chain",
        chain_kind=DurableMerkleChainKind.JOURNAL,
        sequence=1,
        item_hash=fp("a"),
        previous_hash=fp("b"),
        subject_id="subject",
        payload_fingerprint=fp("c"),
    )
    values["leaf_hash"] = (
        DurableMerkleLeaf.compute_hash(
            **values
        )
    )
    values[field] = value
    with pytest.raises(
        (ValueError, TypeError),
    ):
        DurableMerkleLeaf(**values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("chain_id", ""),
        ("chain_root", "bad"),
        ("sequence_count", 0),
        ("merkle_root", "bad"),
        ("leaves_digest", "bad"),
        ("algorithm", "other"),
    ],
)
def test_checkpoint_validation(field, value):
    values = dict(
        schema_version=1,
        chain_id="chain",
        chain_kind=DurableMerkleChainKind.JOURNAL,
        chain_root=fp("a"),
        sequence_count=1,
        merkle_root=fp("b"),
        leaves_digest=fp("c"),
        algorithm=MERKLE_ALGORITHM,
    )
    values[field] = value
    with pytest.raises(
        (ValueError, TypeError),
    ):
        DurableMerkleCheckpoint(
            **values
        )


def test_signed_checkpoint_rejects_wrong_artifact_type():
    checkpoint = DurableMerkleCheckpoint(
        1,
        "chain",
        DurableMerkleChainKind.JOURNAL,
        fp("a"),
        1,
        fp("b"),
        fp("c"),
    )
    signature = SignedArtifact(
        "wrong",
        checkpoint.digest,
        "key",
        1.0,
        {},
        fp("d"),
    )
    with pytest.raises(
        ValueError,
        match="artifact type",
    ):
        SignedDurableMerkleCheckpoint(
            checkpoint,
            signature,
        )


def test_signed_checkpoint_rejects_wrong_digest():
    checkpoint = DurableMerkleCheckpoint(
        1,
        "chain",
        DurableMerkleChainKind.JOURNAL,
        fp("a"),
        1,
        fp("b"),
        fp("c"),
    )
    signature = SignedArtifact(
        MERKLE_CHECKPOINT_ARTIFACT,
        fp("f"),
        "key",
        1.0,
        {},
        fp("d"),
    )
    with pytest.raises(
        ValueError,
        match="digest mismatch",
    ):
        SignedDurableMerkleCheckpoint(
            checkpoint,
            signature,
        )


def test_proof_step_validation():
    with pytest.raises(
        ValueError,
        match="SHA-256",
    ):
        DurableMerkleProofStep(
            "bad",
            DurableMerkleSide.LEFT,
        )
    with pytest.raises(
        ValueError,
        match="bool",
    ):
        DurableMerkleProofStep(
            fp("a"),
            DurableMerkleSide.LEFT,
            duplicated="yes",
        )


def test_checkpoint_digest_stable():
    _, journal, _ = journal_fixture(2)
    auth = authority()
    first, _ = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    second, _ = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    assert (
        first.checkpoint.digest
        == second.checkpoint.digest
    )


def test_signed_checkpoint_digest_changes_with_signature_time():
    _, journal, _ = journal_fixture(2)
    first_auth = DurableMerkleAuthority(
        ArtifactSigner(
            "same",
            b"k" * 32,
            clock=lambda: 1.0,
        )
    )
    second_auth = DurableMerkleAuthority(
        ArtifactSigner(
            "same",
            b"k" * 32,
            clock=lambda: 2.0,
        )
    )
    first, _ = first_auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    second, _ = second_auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    assert (
        first.checkpoint.digest
        == second.checkpoint.digest
    )
    assert first.digest != second.digest


def test_receipt_subject_identity_is_bound():
    _, chain, _ = receipt_fixture(1)
    auth = authority()
    signed, leaves = auth.build(
        chain,
        chain_id="receipts-main",
        chain_kind=DurableMerkleChainKind.RECEIPTS,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=1,
    )
    assert auth.require_proof(
        signed,
        proof,
        expected_subject_id="receipt-1",
    ).ok
    assert not auth.inspect_proof(
        signed,
        proof,
        expected_subject_id="receipt-other",
    ).ok


def test_receipt_payload_fingerprint_is_bound():
    _, chain, nodes = receipt_fixture(1)
    auth = authority()
    signed, leaves = auth.build(
        chain,
        chain_id="receipts-main",
        chain_kind=DurableMerkleChainKind.RECEIPTS,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=1,
    )
    assert auth.require_proof(
        signed,
        proof,
        expected_payload_fingerprint=(
            nodes[0].receipt.fingerprint
        ),
    ).ok


def test_journal_payload_is_event_hash():
    _, journal, events = journal_fixture(1)
    signed, leaves = authority().build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    assert (
        leaves[0].subject_id
        == events[0].event_hash
    )
    assert (
        leaves[0].payload_fingerprint
        == events[0].event_hash
    )


def test_build_rejects_chain_kind_mismatch():
    _, journal, _ = journal_fixture(1)
    with pytest.raises(
        DurableMerkleError,
        match="receipt item",
    ):
        authority().build(
            journal,
            chain_id="wrong-kind",
            chain_kind=DurableMerkleChainKind.RECEIPTS,
        )


def test_build_rejects_receipts_as_journal():
    _, chain, _ = receipt_fixture(1)
    with pytest.raises(
        DurableMerkleError,
        match="event_hash",
    ):
        authority().build(
            chain,
            chain_id="wrong-kind",
            chain_kind=DurableMerkleChainKind.JOURNAL,
        )


def test_proof_serialization_is_json_shaped():
    _, journal, _ = journal_fixture(3)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=2,
    )
    data = proof.to_dict()
    assert data["sequence"] == 2
    assert data["tree_size"] == 3
    assert data["chain_kind"] == "journal"
    assert data["leaf"]["sequence"] == 2
    assert isinstance(data["siblings"], list)
    assert len(data["digest"]) == 64


def test_checkpoint_serialization_is_json_shaped():
    _, journal, _ = journal_fixture(2)
    signed, _ = authority().build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    data = signed.to_dict()
    assert (
        data["checkpoint"]["chain_id"]
        == "journal-main"
    )
    assert (
        data["checkpoint"]["algorithm"]
        == MERKLE_ALGORITHM
    )
    assert (
        data["signature"]["artifact_type"]
        == MERKLE_CHECKPOINT_ARTIFACT
    )
    assert len(data["digest"]) == 64


def test_inspect_with_no_chain_uses_signature_as_checkpoint_authority():
    _, journal, _ = journal_fixture(2)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=1,
    )
    report = auth.inspect_proof(
        signed,
        proof,
        chain=None,
    )
    assert report.ok
    assert report.checkpoint_matches_chain


def test_inspect_with_wrong_authoritative_chain_fails():
    _, first, _ = journal_fixture(
        2,
        namespace="first",
    )
    _, second, _ = journal_fixture(
        1,
        namespace="second",
    )
    auth = authority()
    signed, leaves = auth.build(
        first,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=1,
    )
    report = auth.inspect_proof(
        signed,
        proof,
        chain=second,
    )
    assert not report.ok
    assert not report.checkpoint_matches_chain


def test_checkpoint_metadata_binds_sequence_count():
    _, journal, _ = journal_fixture(5)
    signed, _ = authority().build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    assert (
        signed.signature.metadata[
            "sequence_count"
        ]
        == "5"
    )


def test_checkpoint_metadata_binds_chain_root():
    _, journal, events = journal_fixture(2)
    signed, _ = authority().build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    assert (
        signed.signature.metadata[
            "chain_root"
        ]
        == events[-1].event_hash
    )


def test_merkle_node_hash_is_order_sensitive():
    auth = authority()
    assert auth.node_hash(
        fp("a"),
        fp("b"),
    ) != auth.node_hash(
        fp("b"),
        fp("a"),
    )


def test_leaf_hash_is_chain_id_scoped():
    first = DurableMerkleLeaf.compute_hash(
        chain_id="one",
        chain_kind=DurableMerkleChainKind.JOURNAL,
        sequence=1,
        item_hash=fp("a"),
        previous_hash=fp("b"),
        subject_id="subject",
        payload_fingerprint=fp("c"),
    )
    second = DurableMerkleLeaf.compute_hash(
        chain_id="two",
        chain_kind=DurableMerkleChainKind.JOURNAL,
        sequence=1,
        item_hash=fp("a"),
        previous_hash=fp("b"),
        subject_id="subject",
        payload_fingerprint=fp("c"),
    )
    assert first != second


def test_leaf_hash_is_chain_kind_scoped():
    first = DurableMerkleLeaf.compute_hash(
        chain_id="chain",
        chain_kind=DurableMerkleChainKind.JOURNAL,
        sequence=1,
        item_hash=fp("a"),
        previous_hash=fp("b"),
        subject_id="subject",
        payload_fingerprint=fp("c"),
    )
    second = DurableMerkleLeaf.compute_hash(
        chain_id="chain",
        chain_kind=DurableMerkleChainKind.RECEIPTS,
        sequence=1,
        item_hash=fp("a"),
        previous_hash=fp("b"),
        subject_id="subject",
        payload_fingerprint=fp("c"),
    )
    assert first != second


def test_leaf_hash_is_sequence_scoped():
    first = DurableMerkleLeaf.compute_hash(
        chain_id="chain",
        chain_kind=DurableMerkleChainKind.JOURNAL,
        sequence=1,
        item_hash=fp("a"),
        previous_hash=fp("b"),
        subject_id="subject",
        payload_fingerprint=fp("c"),
    )
    second = DurableMerkleLeaf.compute_hash(
        chain_id="chain",
        chain_kind=DurableMerkleChainKind.JOURNAL,
        sequence=2,
        item_hash=fp("a"),
        previous_hash=fp("b"),
        subject_id="subject",
        payload_fingerprint=fp("c"),
    )
    assert first != second


def test_proof_digest_changes_when_sibling_changes():
    _, journal, _ = journal_fixture(4)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    proof = auth.prove(
        signed,
        leaves,
        sequence=2,
    )
    tampered = replace(
        proof,
        siblings=(
            replace(
                proof.siblings[0],
                sibling_hash=fp("f"),
            ),
            *proof.siblings[1:],
        ),
    )
    assert proof.digest != tampered.digest


def test_proof_digest_is_stable():
    _, journal, _ = journal_fixture(4)
    auth = authority()
    signed, leaves = auth.build(
        journal,
        chain_id="journal-main",
        chain_kind=DurableMerkleChainKind.JOURNAL,
    )
    first = auth.prove(
        signed,
        leaves,
        sequence=2,
    )
    second = auth.prove(
        signed,
        leaves,
        sequence=2,
    )
    assert first.digest == second.digest
    assert first == second
