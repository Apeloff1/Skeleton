"""Cross-chain durable consistency barrier tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_consistency_barrier import (
    DurableConsistencyBarrier,
    DurableConsistencyBarrierConflict,
    DurableConsistencyBarrierCoordinator,
    DurableConsistencyBarrierCorruption,
    DurableConsistencyBarrierHead,
    DurableConsistencyBarrierMember,
    DurableConsistencyBarrierPolicy,
    DurableConsistencyBarrierState,
    DurableConsistencyBarrierStore,
    DurableConsistencyBarrierUnstable,
    SignedDurableConsistencyBarrier,
)
from skeleton.shells.ai.durable_hot_floor import HotFloorPosition
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.receipts import ExecutionReceipt


GENESIS = "0" * 64


def fp(char: str) -> str:
    return char * 64


class FakeHead:
    def __init__(self, sequence: int, root_hash: str):
        self.sequence = sequence
        self.root_hash = root_hash


class FakeChain:
    def __init__(
        self,
        sequence: int = 1,
        root_hash: str = fp("a"),
        *,
        verified: bool = True,
        floor: HotFloorPosition | None = None,
    ) -> None:
        self.sequence = sequence
        self.root = root_hash
        self.verified = verified
        self.floor = (
            floor
            if floor is not None
            else HotFloorPosition.genesis()
        )
        self.ancestors: set[str] = {
            root_hash,
            self.floor.root_hash,
        }

    def head(self):
        return FakeHead(
            self.sequence,
            self.root,
        )

    def verify(self):
        return self.verified

    def root_hash(self):
        return self.root

    def length(self):
        return self.sequence

    def hot_floor(self):
        return self.floor

    def hot_length(self):
        return (
            self.sequence
            - self.floor.sequence
            if self.floor.sequence
            else self.sequence
        )

    def root_is_ancestor(self, root_hash):
        return root_hash in self.ancestors

    def advance(self, root_hash: str):
        self.ancestors.add(self.root)
        self.sequence += 1
        self.root = root_hash
        self.ancestors.add(root_hash)


def store(
    backend=None,
    *,
    clock=lambda: 10.0,
):
    backend = backend or InMemoryFencedStore()
    signer = ArtifactSigner(
        "barrier",
        b"b" * 32,
        clock=clock,
    )
    return (
        backend,
        signer,
        DurableConsistencyBarrierStore(
            backend,
            signer,
            namespace="barriers",
        ),
    )


def coordinator(
    barrier_store,
    *,
    clock=lambda: 10.0,
    policy=None,
    between_passes=None,
):
    return DurableConsistencyBarrierCoordinator(
        barrier_store,
        policy=policy,
        clock=clock,
        between_passes=between_passes,
    )


def test_capture_single_stable_chain():
    _, _, barrier_store = store()
    chain = FakeChain()
    result = coordinator(
        barrier_store
    ).capture(
        "backup",
        (("journal", chain),),
        operator_id="operator",
    )
    barrier = result.stored.signed.barrier
    assert barrier.generation == 1
    assert barrier.previous_barrier_id == ""
    assert barrier.previous_barrier_digest == ""
    assert barrier.atomic_snapshot is False
    assert barrier.write_fenced is False
    assert barrier.capture_attempt == 1
    assert barrier.stabilization_passes == 2
    assert len(barrier.members) == 1
    assert barrier.members[0].chain_id == "journal"
    assert barrier.members[0].head_sequence == 1
    assert barrier.members[0].head_root == fp("a")
    assert barrier.members[0].chain_verified
    assert result.head_created


def test_capture_multiple_chains_sorts_members():
    _, _, barrier_store = store()
    result = coordinator(
        barrier_store
    ).capture(
        "backup",
        (
            ("receipts", FakeChain(2, fp("b"))),
            ("journal", FakeChain(3, fp("c"))),
        ),
        operator_id="operator",
    )
    assert [
        member.chain_id
        for member
        in result.stored.signed.barrier.members
    ] == ["journal", "receipts"]


def test_barrier_does_not_claim_authority():
    _, _, barrier_store = store()
    barrier = coordinator(
        barrier_store
    ).capture(
        "backup",
        (("journal", FakeChain()),),
        operator_id="operator",
    ).stored.signed.barrier
    data = barrier.to_dict()
    assert data["atomic_snapshot"] is False
    assert data["write_fenced"] is False
    assert data["grants_execution_authority"] is False
    assert data["grants_pruning_authority"] is False
    assert data["grants_restore_authority"] is False


def test_second_generation_binds_predecessor():
    _, _, barrier_store = store()
    coord = coordinator(barrier_store)
    first = coord.capture(
        "backup",
        (("journal", FakeChain()),),
        operator_id="operator",
    ).stored.signed.barrier
    second = coord.capture(
        "backup",
        (("journal", FakeChain(2, fp("b"))),),
        operator_id="operator",
    ).stored.signed.barrier
    assert second.generation == 2
    assert second.previous_barrier_id == first.barrier_id
    assert second.previous_barrier_digest == first.digest


def test_different_names_have_independent_generations():
    _, _, barrier_store = store()
    coord = coordinator(barrier_store)
    first = coord.capture(
        "alpha",
        (("journal", FakeChain()),),
        operator_id="operator",
    ).stored.signed.barrier
    second = coord.capture(
        "beta",
        (("journal", FakeChain()),),
        operator_id="operator",
    ).stored.signed.barrier
    assert first.generation == 1
    assert second.generation == 1
    assert first.barrier_id != second.barrier_id


def test_current_returns_latest_generation():
    _, _, barrier_store = store()
    coord = coordinator(barrier_store)
    coord.capture(
        "backup",
        (("journal", FakeChain()),),
        operator_id="operator",
    )
    second = coord.capture(
        "backup",
        (("journal", FakeChain(2, fp("b"))),),
        operator_id="operator",
    )
    current = barrier_store.current("backup")
    assert current is not None
    assert (
        current.signed.barrier.barrier_id
        == second.stored.signed.barrier.barrier_id
    )


def test_require_returns_signed_record():
    _, _, barrier_store = store()
    publication = coordinator(
        barrier_store
    ).capture(
        "backup",
        (("journal", FakeChain()),),
        operator_id="operator",
    )
    stored = barrier_store.require(
        publication.stored.signed.barrier.barrier_id
    )
    assert stored == publication.stored


def test_require_missing_barrier():
    _, _, barrier_store = store()
    with pytest.raises(
        DurableConsistencyBarrierConflict,
        match="missing",
    ):
        barrier_store.require(fp("f"))


def test_unstable_first_attempt_retries_and_succeeds():
    _, _, barrier_store = store()
    chain = FakeChain()
    mutated = {"done": False}

    def hook(attempt, pass_index):
        if (
            attempt == 1
            and pass_index == 2
            and not mutated["done"]
        ):
            mutated["done"] = True
            chain.advance(fp("b"))

    publication = coordinator(
        barrier_store,
        between_passes=hook,
    ).capture(
        "backup",
        (("journal", chain),),
        operator_id="operator",
    )
    barrier = publication.stored.signed.barrier
    assert barrier.capture_attempt == 2
    assert barrier.members[0].head_sequence == 2
    assert barrier.members[0].head_root == fp("b")


def test_never_stable_hits_capture_bound():
    _, _, barrier_store = store()
    chain = FakeChain()
    counter = {"value": 0}

    def hook(attempt, pass_index):
        counter["value"] += 1
        digit = hex(
            (counter["value"] % 15) + 1
        )[2:]
        chain.advance(digit * 64)

    policy = DurableConsistencyBarrierPolicy(
        stabilization_passes=2,
        max_capture_attempts=3,
    )
    with pytest.raises(
        DurableConsistencyBarrierUnstable,
        match="did not stabilize",
    ):
        coordinator(
            barrier_store,
            policy=policy,
            between_passes=hook,
        ).capture(
            "backup",
            (("journal", chain),),
            operator_id="operator",
        )


def test_three_pass_stabilization_requires_all_passes_equal():
    _, _, barrier_store = store()
    chain = FakeChain()
    calls = []

    def hook(attempt, pass_index):
        calls.append((attempt, pass_index))

    policy = DurableConsistencyBarrierPolicy(
        stabilization_passes=3,
    )
    result = coordinator(
        barrier_store,
        policy=policy,
        between_passes=hook,
    ).capture(
        "backup",
        (("journal", chain),),
        operator_id="operator",
    )
    assert result.stabilization_passes == 3
    assert calls == [(1, 2), (1, 3)]


def test_chain_verify_failure_blocks_capture():
    _, _, barrier_store = store()
    with pytest.raises(
        DurableConsistencyBarrierCorruption,
        match="integrity",
    ):
        coordinator(
            barrier_store
        ).capture(
            "backup",
            (
                (
                    "journal",
                    FakeChain(
                        verified=False,
                    ),
                ),
            ),
            operator_id="operator",
        )


def test_verify_requirement_can_be_disabled_explicitly():
    _, _, barrier_store = store()
    policy = DurableConsistencyBarrierPolicy(
        require_chain_verify=False,
    )
    barrier = coordinator(
        barrier_store,
        policy=policy,
    ).capture(
        "backup",
        (
            (
                "journal",
                FakeChain(
                    verified=False,
                ),
            ),
        ),
        operator_id="operator",
    ).stored.signed.barrier
    assert barrier.members[0].chain_verified is False


def test_hot_floor_binding_is_captured():
    _, _, barrier_store = store()
    floor = HotFloorPosition(
        3,
        fp("c"),
        fp("f"),
        "archive-1",
        fp("m"),
        fp("o"),
        7,
    )
    chain = FakeChain(
        5,
        fp("e"),
        floor=floor,
    )
    barrier = coordinator(
        barrier_store
    ).capture(
        "backup",
        (("journal", chain),),
        operator_id="operator",
    ).stored.signed.barrier
    member = barrier.members[0]
    assert member.hot_floor_sequence == 3
    assert member.hot_floor_root == fp("c")
    assert member.hot_floor_id == fp("f")
    assert member.hot_floor_archive_id == "archive-1"
    assert (
        member.hot_floor_archive_manifest_digest
        == fp("m")
    )
    assert member.hot_floor_fencing_token == 7
    assert member.hot_length == 2


def test_hot_floor_ahead_of_head_is_corruption():
    _, _, barrier_store = store()
    floor = HotFloorPosition(
        3,
        fp("c"),
        fp("f"),
        "archive-1",
        fp("m"),
        fp("o"),
        7,
    )
    with pytest.raises(
        DurableConsistencyBarrierCorruption,
        match="ahead",
    ):
        coordinator(
            barrier_store
        ).capture(
            "backup",
            (
                (
                    "journal",
                    FakeChain(
                        2,
                        fp("b"),
                        floor=floor,
                    ),
                ),
            ),
            operator_id="operator",
        )


def test_inspect_current_is_stable_when_unchanged():
    _, _, barrier_store = store()
    chain = FakeChain()
    coord = coordinator(barrier_store)
    coord.capture(
        "backup",
        (("journal", chain),),
        operator_id="operator",
    )
    assert (
        coord.inspect_current(
            "backup",
            (("journal", chain),),
        )
        is DurableConsistencyBarrierState.STABLE
    )


def test_inspect_current_accepts_descendant_head():
    _, _, barrier_store = store()
    chain = FakeChain()
    coord = coordinator(barrier_store)
    coord.capture(
        "backup",
        (("journal", chain),),
        operator_id="operator",
    )
    chain.advance(fp("b"))
    assert (
        coord.inspect_current(
            "backup",
            (("journal", chain),),
        )
        is DurableConsistencyBarrierState.STABLE
    )


def test_inspect_current_rejects_same_sequence_divergence():
    _, _, barrier_store = store()
    chain = FakeChain()
    coord = coordinator(barrier_store)
    coord.capture(
        "backup",
        (("journal", chain),),
        operator_id="operator",
    )
    chain.root = fp("b")
    assert (
        coord.inspect_current(
            "backup",
            (("journal", chain),),
        )
        is DurableConsistencyBarrierState.INVALID
    )


def test_inspect_current_rejects_sequence_rollback():
    _, _, barrier_store = store()
    chain = FakeChain(2, fp("b"))
    coord = coordinator(barrier_store)
    coord.capture(
        "backup",
        (("journal", chain),),
        operator_id="operator",
    )
    chain.sequence = 1
    chain.root = fp("a")
    assert (
        coord.inspect_current(
            "backup",
            (("journal", chain),),
        )
        is DurableConsistencyBarrierState.INVALID
    )


def test_inspect_current_rejects_missing_ancestor():
    _, _, barrier_store = store()
    chain = FakeChain()
    coord = coordinator(barrier_store)
    coord.capture(
        "backup",
        (("journal", chain),),
        operator_id="operator",
    )
    chain.sequence = 2
    chain.root = fp("b")
    chain.ancestors = {fp("b")}
    assert (
        coord.inspect_current(
            "backup",
            (("journal", chain),),
        )
        is DurableConsistencyBarrierState.INVALID
    )


def test_inspect_current_missing_barrier_is_invalid():
    _, _, barrier_store = store()
    assert (
        coordinator(
            barrier_store
        ).inspect_current(
            "missing",
            (("journal", FakeChain()),),
        )
        is DurableConsistencyBarrierState.INVALID
    )


def test_inspect_current_member_set_mismatch_is_invalid():
    _, _, barrier_store = store()
    coord = coordinator(barrier_store)
    coord.capture(
        "backup",
        (("journal", FakeChain()),),
        operator_id="operator",
    )
    assert (
        coord.inspect_current(
            "backup",
            (
                ("journal", FakeChain()),
                ("receipts", FakeChain()),
            ),
        )
        is DurableConsistencyBarrierState.INVALID
    )


def test_duplicate_chain_id_rejected():
    _, _, barrier_store = store()
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        coordinator(
            barrier_store
        ).capture(
            "backup",
            (
                ("journal", FakeChain()),
                ("journal", FakeChain()),
            ),
            operator_id="operator",
        )


def test_chain_bound_enforced():
    _, _, barrier_store = store()
    policy = DurableConsistencyBarrierPolicy(
        max_chains=1,
    )
    with pytest.raises(
        DurableConsistencyBarrierConflict,
        match="bound",
    ):
        coordinator(
            barrier_store,
            policy=policy,
        ).capture(
            "backup",
            (
                ("a", FakeChain()),
                ("b", FakeChain()),
            ),
            operator_id="operator",
        )


def test_empty_chain_set_rejected_by_default():
    _, _, barrier_store = store()
    with pytest.raises(
        ValueError,
        match="at least one",
    ):
        coordinator(
            barrier_store
        ).capture(
            "backup",
            (),
            operator_id="operator",
        )


def test_chain_surface_validation():
    _, _, barrier_store = store()
    with pytest.raises(
        TypeError,
        match="does not implement",
    ):
        coordinator(
            barrier_store
        ).capture(
            "backup",
            (("broken", object()),),
            operator_id="operator",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_chains": 0},
        {"stabilization_passes": 1},
        {"max_capture_attempts": 0},
        {"require_chain_verify": "yes"},
        {"require_hot_floor_consistency": "yes"},
        {"require_nonempty": "yes"},
    ],
)
def test_policy_validation(kwargs):
    with pytest.raises(ValueError):
        DurableConsistencyBarrierPolicy(
            **kwargs
        )


def test_policy_digest_is_deterministic():
    first = DurableConsistencyBarrierPolicy()
    second = DurableConsistencyBarrierPolicy()
    assert first.digest == second.digest


def test_member_digest_is_deterministic():
    member = DurableConsistencyBarrierMember(
        "journal",
        1,
        fp("a"),
        0,
        GENESIS,
        "",
        "",
        "",
        0,
        1,
        True,
    )
    assert member.digest == member.digest


def test_member_rejects_bad_hot_length():
    with pytest.raises(
        ValueError,
        match="hot_length",
    ):
        DurableConsistencyBarrierMember(
            "journal",
            2,
            fp("b"),
            0,
            GENESIS,
            "",
            "",
            "",
            0,
            1,
            True,
        )


def test_member_rejects_non_genesis_floor_without_authority():
    with pytest.raises(
        ValueError,
        match="floor_id",
    ):
        DurableConsistencyBarrierMember(
            "journal",
            2,
            fp("b"),
            1,
            fp("a"),
            "",
            "",
            "",
            0,
            1,
            True,
        )


def test_barrier_member_lookup():
    _, _, barrier_store = store()
    barrier = coordinator(
        barrier_store
    ).capture(
        "backup",
        (
            ("journal", FakeChain()),
            ("receipts", FakeChain()),
        ),
        operator_id="operator",
    ).stored.signed.barrier
    assert (
        barrier.member("journal").chain_id
        == "journal"
    )
    with pytest.raises(KeyError):
        barrier.member("missing")


def test_barrier_id_changes_with_member_vector():
    _, _, first_store = store()
    first = coordinator(
        first_store,
        clock=lambda: 10.0,
    ).capture(
        "backup",
        (("journal", FakeChain()),),
        operator_id="operator",
    ).stored.signed.barrier

    _, _, second_store = store()
    second = coordinator(
        second_store,
        clock=lambda: 10.0,
    ).capture(
        "backup",
        (("journal", FakeChain(2, fp("b"))),),
        operator_id="operator",
    ).stored.signed.barrier
    assert first.barrier_id != second.barrier_id


def test_barrier_rejects_atomic_snapshot_claim():
    member = DurableConsistencyBarrierMember(
        "journal",
        1,
        fp("a"),
        0,
        GENESIS,
        "",
        "",
        "",
        0,
        1,
        True,
    )
    barrier_id = DurableConsistencyBarrier.derive_id(
        barrier_name="backup",
        generation=1,
        previous_barrier_id="",
        previous_barrier_digest="",
        operator_id="operator",
        captured_at=10.0,
        policy_digest=fp("p"),
        stabilization_passes=2,
        capture_attempt=1,
        members=(member,),
    )
    with pytest.raises(
        ValueError,
        match="atomic",
    ):
        DurableConsistencyBarrier(
            1,
            barrier_id,
            "backup",
            1,
            "",
            "",
            "operator",
            10.0,
            fp("p"),
            2,
            1,
            (member,),
            True,
            False,
        )


def test_barrier_rejects_write_fence_claim():
    member = DurableConsistencyBarrierMember(
        "journal",
        1,
        fp("a"),
        0,
        GENESIS,
        "",
        "",
        "",
        0,
        1,
        True,
    )
    barrier_id = DurableConsistencyBarrier.derive_id(
        barrier_name="backup",
        generation=1,
        previous_barrier_id="",
        previous_barrier_digest="",
        operator_id="operator",
        captured_at=10.0,
        policy_digest=fp("p"),
        stabilization_passes=2,
        capture_attempt=1,
        members=(member,),
    )
    with pytest.raises(
        ValueError,
        match="writer fencing",
    ):
        DurableConsistencyBarrier(
            1,
            barrier_id,
            "backup",
            1,
            "",
            "",
            "operator",
            10.0,
            fp("p"),
            2,
            1,
            (member,),
            False,
            True,
        )


def test_signature_tamper_detected():
    backend, _, barrier_store = store()
    publication = coordinator(
        barrier_store
    ).capture(
        "backup",
        (("journal", FakeChain()),),
        operator_id="operator",
    )
    barrier_id = (
        publication.stored.signed.barrier.barrier_id
    )
    key = barrier_store._record_key(
        barrier_id
    )
    record = backend.get(
        barrier_store.namespace,
        key,
    )
    tampered_signature = replace(
        record.value.signature,
        signature="f" * 64,
    )
    backend.compare_and_swap(
        barrier_store.namespace,
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            signature=tampered_signature,
        ),
    )
    with pytest.raises(
        DurableConsistencyBarrierCorruption,
        match="signature",
    ):
        barrier_store.get(barrier_id)


def test_head_to_missing_record_is_corruption():
    backend, _, barrier_store = store()
    backend.put_if_absent(
        barrier_store.namespace,
        barrier_store._head_key("backup"),
        DurableConsistencyBarrierHead(
            "backup",
            1,
            fp("a"),
            fp("b"),
        ),
    )
    with pytest.raises(
        DurableConsistencyBarrierCorruption,
        match="missing",
    ):
        barrier_store.current("backup")


def test_wrong_head_type_is_corruption():
    backend, _, barrier_store = store()
    backend.put_if_absent(
        barrier_store.namespace,
        barrier_store._head_key("backup"),
        {"bad": True},
    )
    with pytest.raises(
        DurableConsistencyBarrierCorruption,
        match="head",
    ):
        barrier_store.head("backup")


def test_wrong_record_type_is_corruption():
    backend, _, barrier_store = store()
    backend.put_if_absent(
        barrier_store.namespace,
        barrier_store._record_key(fp("a")),
        {"bad": True},
    )
    with pytest.raises(
        DurableConsistencyBarrierCorruption,
        match="value type",
    ):
        barrier_store.get(fp("a"))


def test_publish_rejects_stale_generation():
    _, _, barrier_store = store()
    coord = coordinator(barrier_store)
    first = coord.capture(
        "backup",
        (("journal", FakeChain()),),
        operator_id="operator",
    ).stored.signed.barrier
    member = first.members[0]
    duplicate_id = DurableConsistencyBarrier.derive_id(
        barrier_name="backup",
        generation=1,
        previous_barrier_id="",
        previous_barrier_digest="",
        operator_id="operator",
        captured_at=11.0,
        policy_digest=first.policy_digest,
        stabilization_passes=2,
        capture_attempt=1,
        members=(member,),
    )
    stale = DurableConsistencyBarrier(
        1,
        duplicate_id,
        "backup",
        1,
        "",
        "",
        "operator",
        11.0,
        first.policy_digest,
        2,
        1,
        (member,),
    )
    with pytest.raises(
        DurableConsistencyBarrierConflict,
        match="generation",
    ):
        barrier_store.publish(stale)


def test_real_distributed_journal_and_receipt_capture():
    backend, _, barrier_store = store()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 10.0,
    )
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    journal.append(
        "event",
        session_id="session",
        intent_id="intent",
    )
    receipts.append(
        ExecutionReceipt.now_failure(
            command="python",
            correlation_id="correlation",
            fingerprint=fp("e"),
        )
    )
    barrier = coordinator(
        barrier_store
    ).capture(
        "backup",
        (
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    ).stored.signed.barrier
    assert barrier.member(
        "journal"
    ).head_sequence == 1
    assert barrier.member(
        "receipts"
    ).head_sequence == 1
    assert barrier.member(
        "journal"
    ).head_root == journal.root_hash()
    assert barrier.member(
        "receipts"
    ).head_root == receipts.root_hash()


def test_real_chains_remain_stable_after_descendant_appends():
    backend, _, barrier_store = store()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 10.0,
    )
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    journal.append(
        "one",
        session_id="session",
        intent_id="intent",
    )
    receipts.append(
        ExecutionReceipt.now_failure(
            command="python",
            correlation_id="one",
            fingerprint=fp("e"),
        )
    )
    coord = coordinator(
        barrier_store
    )
    coord.capture(
        "backup",
        (
            ("journal", journal),
            ("receipts", receipts),
        ),
        operator_id="operator",
    )
    journal.append(
        "two",
        session_id="session-2",
        intent_id="intent-2",
    )
    receipts.append(
        ExecutionReceipt.now_failure(
            command="python",
            correlation_id="two",
            fingerprint=fp("f"),
        )
    )
    assert (
        coord.inspect_current(
            "backup",
            (
                ("journal", journal),
                ("receipts", receipts),
            ),
        )
        is DurableConsistencyBarrierState.STABLE
    )


def test_store_namespace_validation():
    backend = InMemoryFencedStore()
    signer = ArtifactSigner(
        "barrier",
        b"b" * 32,
    )
    with pytest.raises(
        ValueError,
        match="namespace",
    ):
        DurableConsistencyBarrierStore(
            backend,
            signer,
            namespace="",
        )


def test_store_signer_validation():
    with pytest.raises(
        TypeError,
        match="signer",
    ):
        DurableConsistencyBarrierStore(
            InMemoryFencedStore(),
            object(),
        )


def test_coordinator_type_validation():
    with pytest.raises(
        TypeError,
        match="store",
    ):
        DurableConsistencyBarrierCoordinator(
            object()
        )


def test_operator_identity_validation():
    _, _, barrier_store = store()
    with pytest.raises(
        ValueError,
        match="operator_id",
    ):
        coordinator(
            barrier_store
        ).capture(
            "backup",
            (("journal", FakeChain()),),
            operator_id="",
        )


def test_barrier_name_validation():
    _, _, barrier_store = store()
    with pytest.raises(
        ValueError,
        match="barrier_name",
    ):
        coordinator(
            barrier_store
        ).capture(
            "",
            (("journal", FakeChain()),),
            operator_id="operator",
        )


def test_publication_serializes():
    _, _, barrier_store = store()
    publication = coordinator(
        barrier_store
    ).capture(
        "backup",
        (("journal", FakeChain()),),
        operator_id="operator",
    )
    data = publication.to_dict()
    assert (
        data["head"]["barrier_id"]
        == publication.stored.signed.barrier.barrier_id
    )
    assert (
        data["stored"]["signed"]["barrier"]["atomic_snapshot"]
        is False
    )
