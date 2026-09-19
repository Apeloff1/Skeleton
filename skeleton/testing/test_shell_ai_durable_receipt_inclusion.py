"""Bounded signed receipt-inclusion proof tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
)
from skeleton.shells.ai.durable_proof_window import (
    DurableHistoricalProofAuthority,
    DurableHistoricalProofStore,
)
from skeleton.shells.ai.durable_receipt_inclusion import (
    DurableReceiptInclusion,
    DurableReceiptInclusionAuthority,
    DurableReceiptInclusionBatchResult,
    DurableReceiptInclusionError,
    DurableReceiptInclusionPolicy,
    DurableReceiptInclusionState,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptSequenceIndex,
    ReceiptIndexEntry,
)
from skeleton.shells.receipts import (
    ChainedReceipt,
    ExecutionReceipt,
    ReceiptChain,
)


def fp(char: str) -> str:
    return char * 64


def receipt(
    name: str,
    *,
    receipt_id: str | None = None,
    fingerprint: str | None = None,
    attempt: int = 1,
) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"correlation-{name}",
        fingerprint=fingerprint or fp("a"),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=attempt,
        receipt_id=receipt_id or f"receipt-{name}",
        metadata={"name": name},
    )


def checkpoint_signer() -> ArtifactSigner:
    return ArtifactSigner(
        "checkpoint",
        b"c" * 32,
        clock=lambda: 100.0,
    )


def proof_signer() -> ArtifactSigner:
    return ArtifactSigner(
        "proof",
        b"p" * 32,
        clock=lambda: 200.0,
    )


class Fixture:
    def __init__(
        self,
        *,
        max_window_items: int = 16,
        policy: DurableReceiptInclusionPolicy | None = None,
        clock=lambda: 300.0,
    ):
        self.backend = InMemoryFencedStore()
        self.chain = DistributedReceiptChain(
            self.backend,
            namespace="receipts",
        )
        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            checkpoint_signer(),
            namespace="checkpoints",
            max_checkpoints=100,
            clock=lambda: 100.0,
        )
        self.proofs = DurableHistoricalProofAuthority(
            self.checkpoints,
            proof_signer(),
            max_window_items=max_window_items,
            clock=lambda: 200.0,
        )
        self.proof_store = DurableHistoricalProofStore(
            self.backend,
            namespace="proofs",
        )
        self.authority = DurableReceiptInclusionAuthority(
            self.proofs,
            proof_store=self.proof_store,
            policy=policy,
            clock=clock,
        )

    def append(self, count: int):
        items = []
        start = self.chain.length()
        for offset in range(count):
            value = receipt(
                str(start + offset + 1),
                fingerprint=fp(
                    chr(ord("a") + ((start + offset) % 6))
                ),
            )
            items.append(
                self.chain.append(value)
            )
        return tuple(items)

    def checkpoint(self):
        return self.checkpoints.publish(
            "receipts",
            self.chain,
        )


def anchored_fixture(
    *,
    before=3,
    after=2,
    max_window_items=16,
    policy=None,
    clock=lambda: 300.0,
):
    env = Fixture(
        max_window_items=max_window_items,
        policy=policy,
        clock=clock,
    )
    before_items = env.append(before)
    checkpoint = env.checkpoint()
    after_items = env.append(after)
    return env, checkpoint, before_items, after_items


def test_build_and_verify_receipt_after_checkpoint():
    env, checkpoint, _, after = anchored_fixture()
    target = after[-1]
    item, verification = env.authority.build_and_require(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    assert verification.valid
    assert verification.state is DurableReceiptInclusionState.VERIFIED
    assert item.receipt_id == target.receipt.receipt_id
    assert item.receipt_hash == target.receipt_hash
    assert item.receipt_fingerprint == target.receipt.fingerprint
    assert item.sequence == target.sequence
    assert item.proof.proof.checkpoint_digest == checkpoint.checkpoint.digest
    assert item.proof.proof.target_root == target.receipt_hash
    assert item.proof.proof.target_sequence == target.sequence
    assert verification.ancestor
    assert verification.indexed
    assert verification.node_valid
    assert verification.proof_valid


def test_zero_length_proof_for_receipt_at_checkpoint():
    env = Fixture()
    target = env.append(1)[0]
    checkpoint = env.checkpoint()
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    assert item.proof.proof.item_count == 0
    assert item.proof.proof.checkpoint_digest == checkpoint.checkpoint.digest
    assert env.authority.require(item, env.chain).valid


def test_cached_proof_is_reused():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    first = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    second = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    assert first.proof == second.proof
    assert env.proof_store.find_target(
        "receipts",
        target.receipt_hash,
    ) == first.proof


def test_cached_proof_can_be_used_when_building_is_disabled():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    first = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    locked = DurableReceiptInclusionAuthority(
        env.proofs,
        proof_store=env.proof_store,
        policy=DurableReceiptInclusionPolicy(
            allow_build_proof=False,
            cache_built_proof=False,
        ),
        clock=lambda: 301.0,
    )
    second = locked.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    assert second.proof == first.proof
    assert locked.require(second, env.chain).valid


def test_missing_cached_proof_fails_when_building_disabled():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    locked = DurableReceiptInclusionAuthority(
        env.proofs,
        proof_store=env.proof_store,
        policy=DurableReceiptInclusionPolicy(
            allow_build_proof=False,
            cache_built_proof=False,
        ),
    )
    with pytest.raises(
        DurableReceiptInclusionError,
        match="policy forbids",
    ):
        locked.build(
            "receipts",
            env.chain,
            target.receipt.receipt_id,
        )


def test_build_requires_receipt_index():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    key = env.chain._index_key(
        target.receipt.receipt_id
    )
    record = env.backend.get(
        env.chain.namespace,
        key,
    )
    env.backend.delete(
        env.chain.namespace,
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DurableReceiptInclusionError,
        match="index is missing",
    ):
        env.authority.build(
            "receipts",
            env.chain,
            target.receipt.receipt_id,
        )


def test_build_requires_prior_checkpoint():
    env = Fixture()
    target = env.append(2)[-1]
    with pytest.raises(
        DurableReceiptInclusionError,
        match="could not be built",
    ):
        env.authority.build(
            "receipts",
            env.chain,
            target.receipt.receipt_id,
        )


def test_window_bound_is_enforced():
    env = Fixture(
        max_window_items=1,
    )
    env.append(1)
    env.checkpoint()
    target = env.append(3)[-1]
    with pytest.raises(
        DurableReceiptInclusionError,
        match="could not be built",
    ):
        env.authority.build(
            "receipts",
            env.chain,
            target.receipt.receipt_id,
        )


def test_valid_inclusion_survives_later_chain_growth():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    env.append(5)
    result = env.authority.require(
        item,
        env.chain,
    )
    assert result.valid
    assert result.current_sequence == env.chain.length()
    assert result.ancestor


def test_receipt_fingerprint_substitution_is_manual_review():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    bad = replace(
        item,
        receipt_fingerprint=fp("f"),
    )
    result = env.authority.verify(
        bad,
        env.chain,
    )
    assert not result.valid
    assert result.state is DurableReceiptInclusionState.MANUAL_REVIEW
    assert any(
        "node identity differs" in reason
        for reason in result.reasons
    )


def test_receipt_id_substitution_is_manual_review():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    bad = replace(
        item,
        receipt_id="receipt-other",
    )
    result = env.authority.verify(
        bad,
        env.chain,
    )
    assert not result.valid
    assert result.state is DurableReceiptInclusionState.MANUAL_REVIEW


def test_missing_index_is_manual_review_when_required():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    key = env.chain._index_key(
        target.receipt.receipt_id
    )
    record = env.backend.get(
        env.chain.namespace,
        key,
    )
    env.backend.delete(
        env.chain.namespace,
        key,
        expected_revision=record.revision,
    )
    result = env.authority.verify(
        item,
        env.chain,
    )
    assert not result.valid
    assert result.state is DurableReceiptInclusionState.MANUAL_REVIEW
    assert not result.indexed


def test_missing_index_can_be_tolerated_for_recovery_policy():
    policy = DurableReceiptInclusionPolicy(
        require_receipt_index=False,
    )
    env, _, _, after = anchored_fixture(
        policy=policy,
    )
    target = after[-1]
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    key = env.chain._index_key(
        target.receipt.receipt_id
    )
    record = env.backend.get(
        env.chain.namespace,
        key,
    )
    env.backend.delete(
        env.chain.namespace,
        key,
        expected_revision=record.revision,
    )
    result = env.authority.verify(
        item,
        env.chain,
    )
    assert result.valid
    assert not result.indexed
    assert result.node_valid
    assert result.proof_valid
    assert result.ancestor


def test_node_tamper_is_manual_review():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    key = env.chain._node_key(
        target.receipt_hash
    )
    record = env.backend.get(
        env.chain.namespace,
        key,
    )
    env.backend.compare_and_swap(
        env.chain.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            target,
            receipt=replace(
                target.receipt,
                stdout_bytes=99,
            ),
        ),
    )
    result = env.authority.verify(
        item,
        env.chain,
    )
    assert not result.valid
    assert result.state is DurableReceiptInclusionState.MANUAL_REVIEW
    assert not result.node_valid


def test_signature_tamper_invalidates_proof():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    bad_signature = replace(
        item.proof.signature,
        signature="f" * 64,
    )
    bad_proof = replace(
        item.proof,
        signature=bad_signature,
    )
    bad = replace(
        item,
        proof=bad_proof,
    )
    result = env.authority.verify(
        bad,
        env.chain,
    )
    assert not result.valid
    assert not result.proof_valid
    assert any(
        reason.startswith("proof:")
        for reason in result.reasons
    )


def test_proof_chain_substitution_rejected_by_dataclass():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    bad_window = replace(
        item.proof.proof,
        chain_id="other",
    )
    bad_signed = replace(
        item.proof,
        proof=bad_window,
    )
    with pytest.raises(
        ValueError,
        match="chain_id",
    ):
        replace(
            item,
            proof=bad_signed,
        )


def test_proof_target_sequence_substitution_rejected_by_dataclass():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    bad_window = replace(
        item.proof.proof,
        target_sequence=item.sequence + 1,
        item_count=item.proof.proof.item_count + 1,
    )
    bad_signed = replace(
        item.proof,
        proof=bad_window,
    )
    with pytest.raises(
        ValueError,
        match="target sequence",
    ):
        replace(
            item,
            proof=bad_signed,
        )


def test_stale_inclusion_is_rejected():
    now = [300.0]
    policy = DurableReceiptInclusionPolicy(
        max_receipt_age_seconds=10.0,
    )
    env, _, _, after = anchored_fixture(
        policy=policy,
        clock=lambda: now[0],
    )
    target = after[-1]
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    now[0] = 311.0
    result = env.authority.verify(
        item,
        env.chain,
    )
    assert not result.valid
    assert result.state is DurableReceiptInclusionState.STALE
    assert any(
        "stale" in reason
        for reason in result.reasons
    )


def test_future_created_at_is_stale():
    now = [300.0]
    policy = DurableReceiptInclusionPolicy(
        max_receipt_age_seconds=10.0,
    )
    env, _, _, after = anchored_fixture(
        policy=policy,
        clock=lambda: now[0],
    )
    target = after[-1]
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    bad = replace(
        item,
        created_at=301.0,
    )
    result = env.authority.verify(
        bad,
        env.chain,
    )
    assert result.state is DurableReceiptInclusionState.STALE


def test_invalid_clock_blocks_build():
    env, _, _, after = anchored_fixture(
        clock=lambda: float("nan"),
    )
    target = after[-1]
    with pytest.raises(
        DurableReceiptInclusionError,
        match="clock",
    ):
        env.authority.build(
            "receipts",
            env.chain,
            target.receipt.receipt_id,
        )


def test_orphan_fork_target_is_rejected_even_with_valid_bounded_proof():
    env = Fixture()
    env.append(3)
    checkpoint = env.checkpoint()
    committed = env.append(1)[0]

    fork_receipt = receipt(
        "fork",
        fingerprint=fp("f"),
    )
    fork_hash = ReceiptChain._hash(
        checkpoint.checkpoint.root_hash,
        4,
        fork_receipt,
    )
    fork = ChainedReceipt(
        4,
        checkpoint.checkpoint.root_hash,
        fork_hash,
        fork_receipt,
    )
    env.backend.put_if_absent(
        env.chain.namespace,
        env.chain._node_key(fork_hash),
        fork,
    )
    env.backend.put_if_absent(
        env.chain.namespace,
        env.chain._index_key(
            fork_receipt.receipt_id
        ),
        ReceiptIndexEntry(
            fork_receipt.receipt_id,
            fork_hash,
            fork_receipt.fingerprint,
            4,
        ),
    )

    seq_key = env.chain._sequence_key(4)
    seq_record = env.backend.get(
        env.chain.namespace,
        seq_key,
    )
    env.backend.compare_and_swap(
        env.chain.namespace,
        seq_key,
        expected_revision=seq_record.revision,
        value=DistributedReceiptSequenceIndex(
            4,
            fork_hash,
        ),
    )

    assert env.chain.head().root_hash == committed.receipt_hash
    assert env.chain.verify_root(fork_hash)
    assert not env.chain.root_is_ancestor(fork_hash)
    with pytest.raises(
        DurableReceiptInclusionError,
        match="not an ancestor",
    ):
        env.authority.build(
            "receipts",
            env.chain,
            fork_receipt.receipt_id,
        )


def test_index_substitution_after_build_is_detected():
    env, _, _, after = anchored_fixture()
    target = after[-1]
    item = env.authority.build(
        "receipts",
        env.chain,
        target.receipt.receipt_id,
    )
    key = env.chain._index_key(
        target.receipt.receipt_id
    )
    record = env.backend.get(
        env.chain.namespace,
        key,
    )
    env.backend.compare_and_swap(
        env.chain.namespace,
        key,
        expected_revision=record.revision,
        value=ReceiptIndexEntry(
            target.receipt.receipt_id,
            after[0].receipt_hash,
            after[0].receipt.fingerprint,
            after[0].sequence,
        ),
    )
    result = env.authority.verify(
        item,
        env.chain,
    )
    assert not result.valid
    assert not result.indexed


def test_build_wrong_chain_type():
    env = Fixture()
    with pytest.raises(TypeError, match="DistributedReceiptChain"):
        env.authority.build(
            "receipts",
            object(),
            "receipt",
        )


def test_verify_wrong_item_type():
    env = Fixture()
    with pytest.raises(
        TypeError,
        match="DurableReceiptInclusion",
    ):
        env.authority.verify(
            object(),
            env.chain,
        )


def test_authority_constructor_validation():
    env = Fixture()
    with pytest.raises(TypeError, match="proofs"):
        DurableReceiptInclusionAuthority(
            object(),
        )
    with pytest.raises(TypeError, match="proof_store"):
        DurableReceiptInclusionAuthority(
            env.proofs,
            proof_store=object(),
        )
    with pytest.raises(TypeError, match="policy"):
        DurableReceiptInclusionAuthority(
            env.proofs,
            policy=object(),
        )
    with pytest.raises(TypeError, match="clock"):
        DurableReceiptInclusionAuthority(
            env.proofs,
            clock=object(),
        )


def test_policy_requires_ancestry_invariant():
    with pytest.raises(
        ValueError,
        match="mandatory security invariant",
    ):
        DurableReceiptInclusionPolicy(
            require_current_ancestry=False,
        )


def test_policy_cache_requires_build_permission():
    with pytest.raises(
        ValueError,
        match="cache_built_proof",
    ):
        DurableReceiptInclusionPolicy(
            allow_build_proof=False,
            cache_built_proof=True,
        )


@pytest.mark.parametrize(
    "value",
    [0, -1, True, float("inf"), float("nan")],
)
def test_policy_age_validation(value):
    with pytest.raises(
        ValueError,
        match="max_receipt_age_seconds",
    ):
        DurableReceiptInclusionPolicy(
            max_receipt_age_seconds=value,
        )


def test_policy_digest_is_stable():
    one = DurableReceiptInclusionPolicy()
    two = DurableReceiptInclusionPolicy()
    assert one.digest == two.digest
    assert len(one.digest) == 64


def test_policy_digest_changes_with_index_requirement():
    strict = DurableReceiptInclusionPolicy()
    recovery = DurableReceiptInclusionPolicy(
        require_receipt_index=False,
    )
    assert strict.digest != recovery.digest


def test_inclusion_digest_is_stable():
    env, _, _, after = anchored_fixture()
    item = env.authority.build(
        "receipts",
        env.chain,
        after[-1].receipt.receipt_id,
    )
    clone = replace(item)
    assert clone.digest == item.digest
    assert len(item.digest) == 64


def test_inclusion_to_dict_contains_proof_and_digest():
    env, _, _, after = anchored_fixture()
    item = env.authority.build(
        "receipts",
        env.chain,
        after[-1].receipt.receipt_id,
    )
    data = item.to_dict()
    assert data["receipt_id"] == item.receipt_id
    assert data["receipt_hash"] == item.receipt_hash
    assert data["proof"]["proof"]["target_root"] == item.receipt_hash
    assert data["digest"] == item.digest


def test_verification_to_dict():
    env, _, _, after = anchored_fixture()
    item, result = env.authority.build_and_require(
        "receipts",
        env.chain,
        after[-1].receipt.receipt_id,
    )
    data = result.to_dict()
    assert data["valid"] is True
    assert data["state"] == "verified"
    assert data["receipt_id"] == item.receipt_id
    assert data["ancestor"] is True
    assert data["proof_valid"] is True


def test_require_raises_for_invalid_item():
    env, _, _, after = anchored_fixture()
    item = env.authority.build(
        "receipts",
        env.chain,
        after[-1].receipt.receipt_id,
    )
    bad = replace(
        item,
        receipt_fingerprint=fp("f"),
    )
    with pytest.raises(
        DurableReceiptInclusionError,
    ):
        env.authority.require(
            bad,
            env.chain,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("chain_id", ""),
        ("receipt_id", ""),
        ("receipt_fingerprint", "bad"),
        ("receipt_hash", "bad"),
        ("sequence", 0),
        ("created_at", -1.0),
    ],
)
def test_inclusion_validation(field, value):
    env, _, _, after = anchored_fixture()
    item = env.authority.build(
        "receipts",
        env.chain,
        after[-1].receipt.receipt_id,
    )
    with pytest.raises((ValueError, TypeError)):
        replace(
            item,
            **{field: value},
        )

def test_build_many_verifies_multiple_receipts_in_order():
    env, _, _, after = anchored_fixture(
        after=4,
        max_window_items=16,
    )
    receipt_ids = tuple(
        item.receipt.receipt_id
        for item in after
    )
    result = env.authority.build_many(
        "receipts",
        env.chain,
        receipt_ids,
    )
    assert isinstance(
        result,
        DurableReceiptInclusionBatchResult,
    )
    assert result.valid
    assert result.verified_count == 4
    assert result.invalid_count == 0
    assert tuple(
        item.receipt_id
        for item in result.items
    ) == receipt_ids
    assert all(
        verification.valid
        for verification in result.verifications
    )
    assert result.current_sequence == env.chain.length()
    assert result.current_root == env.chain.root_hash()


def test_build_many_uses_one_full_ancestry_snapshot():
    env, _, _, after = anchored_fixture(
        after=4,
        max_window_items=16,
    )
    calls = {"snapshot": 0}
    original = env.chain.snapshot

    def counted_snapshot():
        calls["snapshot"] += 1
        return original()

    env.chain.snapshot = counted_snapshot
    result = env.authority.build_many(
        "receipts",
        env.chain,
        tuple(
            item.receipt.receipt_id
            for item in after
        ),
    )
    assert result.valid
    assert calls["snapshot"] == 1


def test_verify_many_uses_one_full_ancestry_snapshot():
    env, _, _, after = anchored_fixture(
        after=3,
    )
    built = env.authority.build_many(
        "receipts",
        env.chain,
        tuple(
            item.receipt.receipt_id
            for item in after
        ),
    )
    calls = {"snapshot": 0}
    original = env.chain.snapshot

    def counted_snapshot():
        calls["snapshot"] += 1
        return original()

    env.chain.snapshot = counted_snapshot
    verified = env.authority.verify_many(
        built.items,
        env.chain,
    )
    assert verified.valid
    assert calls["snapshot"] == 1


def test_batch_proofs_are_cached_per_target():
    env, _, _, after = anchored_fixture(
        after=3,
    )
    batch = env.authority.build_many(
        "receipts",
        env.chain,
        tuple(
            item.receipt.receipt_id
            for item in after
        ),
    )
    for item in batch.items:
        assert env.proof_store.find_target(
            "receipts",
            item.receipt_hash,
        ) == item.proof


def test_verify_many_survives_later_chain_growth():
    env, _, _, after = anchored_fixture(
        after=3,
    )
    built = env.authority.build_many(
        "receipts",
        env.chain,
        tuple(
            item.receipt.receipt_id
            for item in after
        ),
    )
    env.append(5)
    verified = env.authority.require_many(
        built.items,
        env.chain,
    )
    assert verified.valid
    assert (
        verified.current_sequence
        == env.chain.length()
    )


def test_verify_many_reports_single_tampered_item():
    env, _, _, after = anchored_fixture(
        after=3,
    )
    built = env.authority.build_many(
        "receipts",
        env.chain,
        tuple(
            item.receipt.receipt_id
            for item in after
        ),
    )
    items = list(built.items)
    items[1] = replace(
        items[1],
        receipt_fingerprint=fp("f"),
    )
    verified = env.authority.verify_many(
        tuple(items),
        env.chain,
    )
    assert not verified.valid
    assert verified.verified_count == 2
    assert verified.invalid_count == 1
    assert verified.verifications[0].valid
    assert not verified.verifications[1].valid
    assert verified.verifications[2].valid


def test_require_many_raises_on_tampered_item():
    env, _, _, after = anchored_fixture(
        after=2,
    )
    built = env.authority.build_many(
        "receipts",
        env.chain,
        tuple(
            item.receipt.receipt_id
            for item in after
        ),
    )
    items = (
        built.items[0],
        replace(
            built.items[1],
            receipt_fingerprint=fp("f"),
        ),
    )
    with pytest.raises(
        DurableReceiptInclusionError,
    ):
        env.authority.require_many(
            items,
            env.chain,
        )


def test_build_many_rejects_duplicate_receipt_ids():
    env, _, _, after = anchored_fixture()
    receipt_id = after[-1].receipt.receipt_id
    with pytest.raises(
        DurableReceiptInclusionError,
        match="duplicates",
    ):
        env.authority.build_many(
            "receipts",
            env.chain,
            (receipt_id, receipt_id),
        )


def test_verify_many_rejects_duplicate_items():
    env, _, _, after = anchored_fixture()
    item = env.authority.build(
        "receipts",
        env.chain,
        after[-1].receipt.receipt_id,
    )
    with pytest.raises(
        DurableReceiptInclusionError,
        match="duplicates",
    ):
        env.authority.verify_many(
            (item, item),
            env.chain,
        )


def test_build_many_enforces_batch_bound():
    env, _, _, after = anchored_fixture(
        after=3,
    )
    bounded = DurableReceiptInclusionAuthority(
        env.proofs,
        proof_store=env.proof_store,
        max_batch_items=2,
    )
    with pytest.raises(
        DurableReceiptInclusionError,
        match="batch exceeds",
    ):
        bounded.build_many(
            "receipts",
            env.chain,
            tuple(
                item.receipt.receipt_id
                for item in after
            ),
        )


def test_verify_many_enforces_batch_bound():
    env, _, _, after = anchored_fixture(
        after=3,
    )
    built = env.authority.build_many(
        "receipts",
        env.chain,
        tuple(
            item.receipt.receipt_id
            for item in after
        ),
    )
    bounded = DurableReceiptInclusionAuthority(
        env.proofs,
        proof_store=env.proof_store,
        max_batch_items=2,
    )
    with pytest.raises(
        DurableReceiptInclusionError,
        match="batch exceeds",
    ):
        bounded.verify_many(
            built.items,
            env.chain,
        )


@pytest.mark.parametrize(
    "maximum",
    [0, -1, True, 1.2],
)
def test_batch_bound_constructor_validation(maximum):
    env = Fixture()
    with pytest.raises(
        ValueError,
        match="max_batch_items",
    ):
        DurableReceiptInclusionAuthority(
            env.proofs,
            max_batch_items=maximum,
        )


def test_verify_many_rejects_wrong_item_type():
    env = Fixture()
    with pytest.raises(
        TypeError,
        match="all batch items",
    ):
        env.authority.verify_many(
            (object(),),
            env.chain,
        )


def test_verify_many_rejects_mixed_chain_ids():
    env, _, _, after = anchored_fixture(
        after=2,
    )
    built = env.authority.build_many(
        "receipts",
        env.chain,
        tuple(
            item.receipt.receipt_id
            for item in after
        ),
    )
    mixed = (
        built.items[0],
        replace(
            built.items[1],
            chain_id="other",
            proof=replace(
                built.items[1].proof,
                proof=replace(
                    built.items[1].proof.proof,
                    chain_id="other",
                ),
            ),
        ),
    )
    with pytest.raises(
        DurableReceiptInclusionError,
        match="mixes chain identities",
    ):
        env.authority.verify_many(
            mixed,
            env.chain,
        )


def test_build_many_missing_one_index_fails_closed():
    env, _, _, after = anchored_fixture(
        after=3,
    )
    missing = after[1]
    key = env.chain._index_key(
        missing.receipt.receipt_id
    )
    record = env.backend.get(
        env.chain.namespace,
        key,
    )
    env.backend.delete(
        env.chain.namespace,
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DurableReceiptInclusionError,
        match="index is missing",
    ):
        env.authority.build_many(
            "receipts",
            env.chain,
            tuple(
                item.receipt.receipt_id
                for item in after
            ),
        )


def test_batch_rejects_orphan_indexed_fork():
    env = Fixture()
    env.append(3)
    checkpoint = env.checkpoint()
    committed = env.append(1)[0]
    fork_receipt = receipt(
        "batch-fork",
        fingerprint=fp("f"),
    )
    fork_hash = ReceiptChain._hash(
        checkpoint.checkpoint.root_hash,
        4,
        fork_receipt,
    )
    fork = ChainedReceipt(
        4,
        checkpoint.checkpoint.root_hash,
        fork_hash,
        fork_receipt,
    )
    env.backend.put_if_absent(
        env.chain.namespace,
        env.chain._node_key(fork_hash),
        fork,
    )
    env.backend.put_if_absent(
        env.chain.namespace,
        env.chain._index_key(
            fork_receipt.receipt_id
        ),
        ReceiptIndexEntry(
            fork_receipt.receipt_id,
            fork_hash,
            fork_receipt.fingerprint,
            4,
        ),
    )
    assert (
        committed.receipt_hash
        == env.chain.root_hash()
    )
    with pytest.raises(
        DurableReceiptInclusionError,
        match="not in committed chain snapshot",
    ):
        env.authority.build_many(
            "receipts",
            env.chain,
            (fork_receipt.receipt_id,),
        )


def test_empty_build_many_is_valid():
    env = Fixture()
    result = env.authority.build_many(
        "custom-chain",
        env.chain,
        (),
    )
    assert result.valid
    assert result.items == ()
    assert result.verifications == ()
    assert result.verified_count == 0
    assert result.invalid_count == 0
    assert result.chain_id == "custom-chain"


def test_empty_verify_many_is_valid():
    env = Fixture()
    result = env.authority.verify_many(
        (),
        env.chain,
    )
    assert result.valid
    assert result.items == ()
    assert result.chain_id == "receipts"


def test_batch_result_digest_is_stable():
    env, _, _, after = anchored_fixture(
        after=2,
    )
    result = env.authority.build_many(
        "receipts",
        env.chain,
        tuple(
            item.receipt.receipt_id
            for item in after
        ),
    )
    clone = replace(result)
    assert clone.digest == result.digest
    assert len(result.digest) == 64


def test_batch_result_to_dict():
    env, _, _, after = anchored_fixture(
        after=2,
    )
    result = env.authority.build_many(
        "receipts",
        env.chain,
        tuple(
            item.receipt.receipt_id
            for item in after
        ),
    )
    data = result.to_dict()
    assert data["valid"] is True
    assert data["verified_count"] == 2
    assert data["invalid_count"] == 0
    assert len(data["items"]) == 2
    assert len(data["verifications"]) == 2
    assert data["digest"] == result.digest


def test_batch_result_rejects_length_mismatch():
    env, _, _, after = anchored_fixture()
    item, verification = env.authority.build_and_require(
        "receipts",
        env.chain,
        after[-1].receipt.receipt_id,
    )
    with pytest.raises(
        ValueError,
        match="length mismatch",
    ):
        DurableReceiptInclusionBatchResult(
            "receipts",
            env.chain.length(),
            env.chain.root_hash(),
            (item,),
            (),
        )


def test_batch_result_rejects_identity_mismatch():
    env, _, _, after = anchored_fixture()
    item, verification = env.authority.build_and_require(
        "receipts",
        env.chain,
        after[-1].receipt.receipt_id,
    )
    bad_verification = replace(
        verification,
        receipt_id="receipt-other",
    )
    with pytest.raises(
        ValueError,
        match="identity differs",
    ):
        DurableReceiptInclusionBatchResult(
            "receipts",
            env.chain.length(),
            env.chain.root_hash(),
            (item,),
            (bad_verification,),
        )


def test_batch_result_rejects_duplicate_items():
    env, _, _, after = anchored_fixture()
    item, verification = env.authority.build_and_require(
        "receipts",
        env.chain,
        after[-1].receipt.receipt_id,
    )
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        DurableReceiptInclusionBatchResult(
            "receipts",
            env.chain.length(),
            env.chain.root_hash(),
            (item, item),
            (verification, verification),
        )

