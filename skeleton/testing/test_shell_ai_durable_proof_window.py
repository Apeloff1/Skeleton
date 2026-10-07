"""Signed bounded historical proof-window and operator tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_checkpoint import (
    DurableChainCheckpointStore,
)
from skeleton.shells.ai.durable_proof_window import (
    PROOF_ARTIFACT_TYPE,
    DurableHistoricalProofAuthority,
    DurableHistoricalProofError,
    DurableHistoricalProofIndex,
    DurableHistoricalProofStore,
    DurableHistoricalProofWindow,
    SignedDurableHistoricalProofWindow,
)
from skeleton.shells.ai.durable_proof_window_operator import (
    DurableProofWindowFleetReport,
    DurableProofWindowOperator,
    DurableProofWindowOperatorError,
    DurableProofWindowPolicy,
    DurableProofWindowReport,
    DurableProofWindowState,
    DurableProofWindowTarget,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner


def fp(char: str) -> str:
    return char * 64


def checkpoint_signer():
    return ArtifactSigner(
        "checkpoint",
        b"c" * 32,
        clock=lambda: 100.0,
    )


def proof_signer():
    return ArtifactSigner(
        "proof",
        b"p" * 32,
        clock=lambda: 200.0,
    )


class Fixture:
    def __init__(
        self,
        *,
        max_window_items=16,
    ):
        self.backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="journal",
            clock=lambda: 10.0,
        )
        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            checkpoint_signer(),
            namespace="checkpoints",
            max_checkpoints=100,
            clock=lambda: 100.0,
        )
        self.authority = DurableHistoricalProofAuthority(
            self.checkpoints,
            proof_signer(),
            max_window_items=max_window_items,
            clock=lambda: 200.0,
        )
        self.store = DurableHistoricalProofStore(
            self.backend,
            namespace="proofs",
        )

    def append(self, count, *, session="session"):
        result = []
        start = self.journal.length()
        for offset in range(count):
            result.append(
                self.journal.append(
                    f"event.{start + offset + 1}",
                    session_id=session,
                    intent_id="intent",
                    proposal_id="proposal",
                )
            )
        return tuple(result)

    def checkpoint(self):
        return self.checkpoints.publish(
            "journal",
            self.journal,
        )


def anchored_fixture(
    *,
    before=3,
    after=2,
    max_window_items=16,
):
    env = Fixture(
        max_window_items=max_window_items
    )
    env.append(before)
    checkpoint = env.checkpoint()
    env.append(after)
    return env, checkpoint


def test_build_for_sequence_anchors_nearest_checkpoint():
    env, checkpoint = anchored_fixture(
        before=3,
        after=2,
    )
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    proof = item.proof
    assert proof.checkpoint_digest == checkpoint.checkpoint.digest
    assert proof.checkpoint_sequence == 3
    assert proof.checkpoint_root == checkpoint.checkpoint.root_hash
    assert proof.target_sequence == 5
    assert proof.target_root == env.journal.root_for_sequence(5)
    assert proof.item_count == 2
    assert proof.first_item_hash == env.journal.root_for_sequence(4)
    assert proof.last_item_hash == proof.target_root
    assert len(proof.segment_digest) == 64
    assert item.signature.artifact_type == PROOF_ARTIFACT_TYPE
    assert item.signature.artifact_digest == proof.digest


def test_build_for_root_resolves_same_target():
    env, _ = anchored_fixture()
    root = env.journal.root_for_sequence(5)
    by_root = env.authority.build_for_root(
        "journal",
        env.journal,
        root,
    )
    by_sequence = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    assert by_root.proof.target_root == root
    assert by_root.proof.target_sequence == 5
    assert by_root.proof.digest == by_sequence.proof.digest


def test_zero_length_proof_at_checkpoint():
    env, checkpoint = anchored_fixture(
        before=3,
        after=0,
    )
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        3,
    )
    proof = item.proof
    assert proof.item_count == 0
    assert proof.target_root == checkpoint.checkpoint.root_hash
    assert proof.first_item_hash == ""
    assert proof.last_item_hash == ""
    verification = env.authority.require(
        item,
        env.journal,
    )
    assert verification.valid
    assert verification.checked_items == 0


def test_multiple_checkpoints_choose_closest_prior_anchor():
    env = Fixture()
    env.append(2)
    first = env.checkpoint()
    env.append(2)
    second = env.checkpoint()
    env.append(2)
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        6,
    )
    assert first.checkpoint.sequence == 2
    assert second.checkpoint.sequence == 4
    assert item.proof.checkpoint_sequence == 4
    assert item.proof.checkpoint_digest == second.checkpoint.digest
    assert item.proof.item_count == 2


def test_target_between_checkpoints_uses_earlier_anchor():
    env = Fixture()
    env.append(2)
    first = env.checkpoint()
    env.append(2)
    env.checkpoint()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        3,
    )
    assert item.proof.checkpoint_digest == first.checkpoint.digest
    assert item.proof.checkpoint_sequence == 2
    assert item.proof.item_count == 1


def test_no_checkpoint_before_target_fails_closed():
    env = Fixture()
    env.append(3)
    env.checkpoint()
    with pytest.raises(
        DurableHistoricalProofError,
        match="no signed checkpoint",
    ):
        env.authority.build_for_sequence(
            "journal",
            env.journal,
            2,
        )


def test_no_checkpoints_fails_closed():
    env = Fixture()
    env.append(2)
    with pytest.raises(
        DurableHistoricalProofError,
        match="no signed checkpoint",
    ):
        env.authority.build_for_sequence(
            "journal",
            env.journal,
            2,
        )


def test_target_beyond_head_is_rejected():
    env, _ = anchored_fixture()
    with pytest.raises(
        DurableHistoricalProofError,
        match="exceeds",
    ):
        env.authority.build_for_sequence(
            "journal",
            env.journal,
            99,
        )


def test_target_window_bound_is_enforced():
    env, _ = anchored_fixture(
        before=1,
        after=3,
        max_window_items=2,
    )
    with pytest.raises(
        DurableHistoricalProofError,
        match="window",
    ):
        env.authority.build_for_sequence(
            "journal",
            env.journal,
            4,
        )


def test_target_root_must_exist():
    env, _ = anchored_fixture()
    with pytest.raises(
        DurableHistoricalProofError,
        match="resolve",
    ):
        env.authority.build_for_root(
            "journal",
            env.journal,
            fp("f"),
        )


def test_verify_valid_nonempty_proof():
    env, _ = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    verification = env.authority.verify(
        item,
        env.journal,
    )
    assert verification.valid
    assert verification.reasons == ()
    assert verification.checked_items == 2
    assert verification.current_sequence == 5
    assert verification.current_root == env.journal.root_hash()


def test_valid_proof_survives_later_chain_growth():
    env, _ = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    old_root = item.proof.target_root
    env.append(10, session="later")
    verification = env.authority.require(
        item,
        env.journal,
    )
    assert verification.valid
    assert verification.target_root == old_root
    assert verification.current_sequence == 15
    assert verification.current_root != old_root


def test_signature_tamper_is_rejected():
    env, _ = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    tampered = replace(
        item,
        signature=replace(
            item.signature,
            signature="0" * 64,
        ),
    )
    verification = env.authority.verify(
        tampered,
        env.journal,
    )
    assert not verification.valid
    assert any(
        "signature" in reason
        for reason in verification.reasons
    )


def test_proof_digest_binding_tamper_is_rejected():
    env, _ = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    tampered = replace(
        item,
        proof=replace(
            item.proof,
            segment_digest=fp("f"),
        ),
    )
    verification = env.authority.verify(
        tampered,
        env.journal,
    )
    assert not verification.valid
    assert any(
        "signature digest" in reason
        or "segment digest" in reason
        for reason in verification.reasons
    )


def test_checkpoint_digest_substitution_is_rejected():
    env, _ = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    tampered = replace(
        item,
        proof=replace(
            item.proof,
            checkpoint_digest=fp("f"),
        ),
    )
    verification = env.authority.verify(
        tampered,
        env.journal,
    )
    assert not verification.valid
    assert any(
        "checkpoint" in reason
        for reason in verification.reasons
    )


def test_target_sequence_locator_substitution_is_detected():
    env, _ = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    key = env.journal._sequence_key(5)
    record = env.backend.get(
        "journal",
        key,
    )
    env.backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            event_hash=env.journal.root_for_sequence(4),
        ),
    )
    verification = env.authority.verify(
        item,
        env.journal,
    )
    assert not verification.valid
    assert any(
        "target sequence root" in reason
        or "locators" in reason
        or "reconstruction" in reason
        for reason in verification.reasons
    )


def test_anchor_sequence_locator_substitution_is_detected():
    env, checkpoint = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    key = env.journal._sequence_key(
        checkpoint.checkpoint.sequence
    )
    record = env.backend.get(
        "journal",
        key,
    )
    env.backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=replace(
            record.value,
            event_hash=env.journal.root_for_sequence(2),
        ),
    )
    verification = env.authority.verify(
        item,
        env.journal,
    )
    assert not verification.valid
    assert any(
        "checkpoint sequence root" in reason
        or "locators" in reason
        for reason in verification.reasons
    )


def test_segment_node_tamper_is_detected():
    env, _ = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    event = env.journal.get_by_sequence(4)
    key = env.journal._event_key(
        event.event_hash
    )
    record = env.backend.get(
        "journal",
        key,
    )
    env.backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=replace(
            event,
            summary="tampered",
        ),
    )
    verification = env.authority.verify(
        item,
        env.journal,
    )
    assert not verification.valid


def test_require_raises_on_invalid_proof():
    env, _ = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    bad = replace(
        item,
        signature=replace(
            item.signature,
            signature="0" * 64,
        ),
    )
    with pytest.raises(
        DurableHistoricalProofError,
        match="signature",
    ):
        env.authority.require(
            bad,
            env.journal,
        )


def test_authority_type_validation():
    env = Fixture()
    with pytest.raises(TypeError):
        DurableHistoricalProofAuthority(
            object(),
            proof_signer(),
        )
    with pytest.raises(TypeError):
        DurableHistoricalProofAuthority(
            env.checkpoints,
            object(),
        )


@pytest.mark.parametrize(
    "maximum",
    [0, -1, True, 1.5],
)
def test_authority_window_bound_validation(maximum):
    env = Fixture()
    with pytest.raises(ValueError):
        DurableHistoricalProofAuthority(
            env.checkpoints,
            proof_signer(),
            max_window_items=maximum,
        )


def test_authority_clock_validation():
    env = Fixture()
    with pytest.raises(TypeError):
        DurableHistoricalProofAuthority(
            env.checkpoints,
            proof_signer(),
            clock=object(),
        )


def test_build_rejects_non_chain():
    env = Fixture()
    with pytest.raises(TypeError):
        env.authority.build_for_sequence(
            "journal",
            object(),
            0,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("chain_id", ""),
        ("checkpoint_digest", "bad"),
        ("checkpoint_sequence", -1),
        ("checkpoint_root", "bad"),
        ("target_sequence", -1),
        ("target_root", "bad"),
        ("item_count", -1),
        ("segment_digest", "bad"),
        ("generated_at", -1),
    ],
)
def test_proof_validation(field, value):
    values = dict(
        schema_version=1,
        chain_id="journal",
        checkpoint_digest=fp("a"),
        checkpoint_sequence=1,
        checkpoint_root=fp("b"),
        target_sequence=1,
        target_root=fp("b"),
        item_count=0,
        segment_digest=fp("c"),
        first_item_hash="",
        last_item_hash="",
        generated_at=1.0,
    )
    values[field] = value
    with pytest.raises(ValueError):
        DurableHistoricalProofWindow(
            **values
        )


def test_proof_rejects_target_before_checkpoint():
    with pytest.raises(
        ValueError,
        match="precedes",
    ):
        DurableHistoricalProofWindow(
            1,
            "journal",
            fp("a"),
            2,
            fp("b"),
            1,
            fp("c"),
            0,
            fp("d"),
            "",
            "",
            1.0,
        )


def test_proof_rejects_wrong_item_count():
    with pytest.raises(
        ValueError,
        match="item_count",
    ):
        DurableHistoricalProofWindow(
            1,
            "journal",
            fp("a"),
            1,
            fp("b"),
            3,
            fp("c"),
            1,
            fp("d"),
            fp("e"),
            fp("c"),
            1.0,
        )


def test_nonempty_proof_requires_boundary_hashes():
    with pytest.raises(
        ValueError,
        match="boundary",
    ):
        DurableHistoricalProofWindow(
            1,
            "journal",
            fp("a"),
            1,
            fp("b"),
            2,
            fp("c"),
            1,
            fp("d"),
            "",
            "",
            1.0,
        )


def test_zero_proof_requires_same_target_root():
    with pytest.raises(
        ValueError,
        match="checkpoint root",
    ):
        DurableHistoricalProofWindow(
            1,
            "journal",
            fp("a"),
            1,
            fp("b"),
            1,
            fp("c"),
            0,
            fp("d"),
            "",
            "",
            1.0,
        )


def test_store_round_trip_by_digest_and_target():
    env, _ = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    revision = env.store.put(
        item
    )
    assert revision == 1
    assert env.store.get(
        item.proof.digest
    ) == item
    assert env.store.find_target(
        "journal",
        item.proof.target_root,
    ) == item


def test_store_put_is_idempotent():
    env, _ = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    first = env.store.put(item)
    second = env.store.put(item)
    assert first == second == 1


def test_store_put_once_for_target_is_idempotent():
    env, _ = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    first = env.store.put_once_for_target(
        item
    )
    second = env.store.put_once_for_target(
        item
    )
    assert first == second


def test_store_target_conflict_is_rejected():
    env, _ = anchored_fixture()
    item = env.authority.build_for_sequence(
        "journal",
        env.journal,
        5,
    )
    env.store.put(item)
    other = replace(
        item,
        proof=replace(
            item.proof,
            generated_at=201.0,
        ),
        signature=proof_signer().sign(
            PROOF_ARTIFACT_TYPE,
            replace(
                item.proof,
                generated_at=201.0,
            ).digest,
        ),
    )
    with pytest.raises(
        DurableHistoricalProofError,
        match="different",
    ):
        env.store.put_once_for_target(
            other
        )


def test_store_missing_returns_none():
    env = Fixture()
    assert env.store.get(fp("f")) is None
    assert (
        env.store.find_target(
            "journal",
            fp("f"),
        )
        is None
    )


def test_store_rejects_wrong_proof_type():
    env = Fixture()
    with pytest.raises(TypeError):
        env.store.put(object())


def test_store_namespace_validation():
    with pytest.raises(ValueError):
        DurableHistoricalProofStore(
            InMemoryFencedStore(),
            namespace="",
        )


def test_corrupt_proof_record_type_is_detected():
    env = Fixture()
    key = env.store._proof_key(
        fp("a")
    )
    env.backend.put_if_absent(
        "proofs",
        key,
        {"bad": True},
    )
    with pytest.raises(
        DurableHistoricalProofError,
        match="invalid type",
    ):
        env.store.get(fp("a"))


def test_corrupt_target_index_type_is_detected():
    env = Fixture()
    key = env.store._target_key(
        "journal",
        fp("a"),
    )
    env.backend.put_if_absent(
        "proofs",
        key,
        {"bad": True},
    )
    with pytest.raises(
        DurableHistoricalProofError,
        match="index",
    ):
        env.store.find_target(
            "journal",
            fp("a"),
        )


def test_target_index_missing_proof_is_detected():
    env = Fixture()
    index = DurableHistoricalProofIndex(
        "journal",
        1,
        fp("a"),
        fp("b"),
    )
    env.backend.put_if_absent(
        "proofs",
        env.store._target_key(
            "journal",
            fp("a"),
        ),
        index,
    )
    with pytest.raises(
        DurableHistoricalProofError,
        match="missing proof",
    ):
        env.store.find_target(
            "journal",
            fp("a"),
        )


def test_index_validation():
    with pytest.raises(ValueError):
        DurableHistoricalProofIndex(
            "",
            1,
            fp("a"),
            fp("b"),
        )
    with pytest.raises(ValueError):
        DurableHistoricalProofIndex(
            "journal",
            -1,
            fp("a"),
            fp("b"),
        )
    with pytest.raises(ValueError):
        DurableHistoricalProofIndex(
            "journal",
            1,
            "bad",
            fp("b"),
        )


def operator_fixture(
    *,
    policy=None,
    max_window_items=16,
):
    env, checkpoint = anchored_fixture(
        max_window_items=max_window_items,
    )
    operator = DurableProofWindowOperator(
        env.authority,
        env.store,
        {"journal": env.journal},
        policy=policy,
    )
    target = DurableProofWindowTarget(
        "journal",
        env.journal.root_hash(),
    )
    return env, checkpoint, operator, target


def test_operator_inspect_reports_missing():
    _, _, operator, target = (
        operator_fixture()
    )
    report = operator.inspect_target(
        target
    )
    assert report.state is DurableProofWindowState.MISSING
    assert not report.ok
    assert report.repairable
    assert not report.cached
    assert not report.built


def test_operator_ensure_builds_missing_proof():
    env, _, operator, target = (
        operator_fixture()
    )
    report = operator.ensure_target(
        target
    )
    assert report.ok
    assert report.built
    assert report.cached
    assert report.state is DurableProofWindowState.CURRENT
    assert env.store.find_target(
        "journal",
        target.target_root,
    ) is not None


def test_operator_second_ensure_is_nonmutating():
    _, _, operator, target = (
        operator_fixture()
    )
    first = operator.ensure_target(
        target
    )
    second = operator.ensure_target(
        target
    )
    assert first.built
    assert not second.built
    assert second.ok
    assert second.proof_digest == first.proof_digest


def test_operator_inspect_cached_valid_proof():
    _, _, operator, target = (
        operator_fixture()
    )
    operator.ensure_target(target)
    report = operator.inspect_target(
        target
    )
    assert report.ok
    assert report.cached
    assert not report.built
    assert report.verification.valid


def test_operator_policy_can_forbid_missing_build():
    policy = DurableProofWindowPolicy(
        allow_build_missing=False,
    )
    _, _, operator, target = (
        operator_fixture(
            policy=policy
        )
    )
    report = operator.ensure_target(
        target
    )
    assert report.state is DurableProofWindowState.MISSING
    assert not report.built


def test_operator_require_cached_policy():
    policy = DurableProofWindowPolicy(
        allow_build_missing=False,
        require_cached=True,
    )
    _, _, operator, target = (
        operator_fixture(
            policy=policy
        )
    )
    with pytest.raises(
        DurableProofWindowOperatorError,
    ):
        operator.require(
            (target,),
            build_missing=True,
        )


def test_operator_reports_unanchored_target():
    env = Fixture()
    env.append(2)
    operator = DurableProofWindowOperator(
        env.authority,
        env.store,
        {"journal": env.journal},
    )
    target = DurableProofWindowTarget(
        "journal",
        env.journal.root_hash(),
    )
    report = operator.ensure_target(
        target
    )
    assert report.state is DurableProofWindowState.UNANCHORED
    assert not report.ok


def test_operator_reports_out_of_window_target():
    env = Fixture(
        max_window_items=1
    )
    env.append(1)
    env.checkpoint()
    env.append(2)
    operator = DurableProofWindowOperator(
        env.authority,
        env.store,
        {"journal": env.journal},
    )
    target = DurableProofWindowTarget(
        "journal",
        env.journal.root_hash(),
    )
    report = operator.ensure_target(
        target
    )
    assert report.state is DurableProofWindowState.OUT_OF_WINDOW
    assert not report.ok


def test_operator_detects_corrupt_cached_signature():
    env, _, operator, target = (
        operator_fixture()
    )
    item = env.authority.build_for_root(
        "journal",
        env.journal,
        target.target_root,
    )
    corrupted = replace(
        item,
        signature=replace(
            item.signature,
            signature="0" * 64,
        ),
    )
    env.store.put(corrupted)
    report = operator.inspect_target(
        target
    )
    assert report.state is DurableProofWindowState.INVALID
    assert not report.ok


def test_operator_fleet_ensure_is_sorted_and_bounded():
    env = Fixture()
    env.append(2)
    env.checkpoint()
    root_two = env.journal.root_hash()
    env.append(1)
    root_three = env.journal.root_hash()
    operator = DurableProofWindowOperator(
        env.authority,
        env.store,
        {"journal": env.journal},
    )
    targets = (
        DurableProofWindowTarget(
            "journal",
            root_three,
        ),
        DurableProofWindowTarget(
            "journal",
            root_two,
        ),
    )
    report = operator.ensure(
        targets
    )
    assert report.ok
    assert report.current == 2
    assert report.repaired
    assert len(report.mutations) == 2
    keys = tuple(
        item.target.key
        for item in report.reports
    )
    assert keys == tuple(sorted(keys))


def test_operator_rejects_duplicate_targets():
    _, _, operator, target = (
        operator_fixture()
    )
    with pytest.raises(
        DurableProofWindowOperatorError,
        match="duplicate",
    ):
        operator.inspect(
            (target, target)
        )


def test_operator_target_bound():
    policy = DurableProofWindowPolicy(
        max_targets=1,
    )
    env, _, operator, target = (
        operator_fixture(
            policy=policy
        )
    )
    second = DurableProofWindowTarget(
        "journal",
        env.journal.root_for_sequence(4),
    )
    with pytest.raises(
        DurableProofWindowOperatorError,
        match="bound",
    ):
        operator.inspect(
            (target, second)
        )


def test_operator_unknown_chain_is_rejected():
    _, _, operator, _ = (
        operator_fixture()
    )
    target = DurableProofWindowTarget(
        "unknown",
        fp("a"),
    )
    with pytest.raises(
        DurableProofWindowOperatorError,
        match="unknown chain",
    ):
        operator.inspect_target(
            target
        )


def test_operator_constructor_validates_components():
    env = Fixture()
    with pytest.raises(TypeError):
        DurableProofWindowOperator(
            object(),
            env.store,
            {},
        )
    with pytest.raises(TypeError):
        DurableProofWindowOperator(
            env.authority,
            object(),
            {},
        )
    with pytest.raises(TypeError):
        DurableProofWindowOperator(
            env.authority,
            env.store,
            {"journal": object()},
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_targets": 0},
        {"max_targets": True},
        {"require_all": "yes"},
        {"allow_build_missing": "yes"},
        {"refresh_invalid": "yes"},
        {"require_cached": "yes"},
    ],
)
def test_operator_policy_validation(kwargs):
    values = dict(
        max_targets=16,
        require_all=True,
        allow_build_missing=True,
        refresh_invalid=False,
        require_cached=False,
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        DurableProofWindowPolicy(
            **values
        )


def test_operator_policy_rejects_cached_and_build_missing():
    with pytest.raises(
        ValueError,
        match="conflicts",
    ):
        DurableProofWindowPolicy(
            require_cached=True,
            allow_build_missing=True,
        )


def test_target_validation():
    with pytest.raises(ValueError):
        DurableProofWindowTarget(
            "",
            fp("a"),
        )
    with pytest.raises(ValueError):
        DurableProofWindowTarget(
            "journal",
            "bad",
        )


def test_target_key_is_stable():
    target = DurableProofWindowTarget(
        "journal",
        fp("a"),
    )
    assert target.key == (
        "journal:" + fp("a")
    )


def test_fleet_report_serialization():
    env, _, operator, target = (
        operator_fixture()
    )
    report = operator.ensure(
        (target,)
    )
    data = report.to_dict()
    assert data["ok"] is True
    assert data["current"] == 1
    assert data["missing"] == 0
    assert data["repaired"] is True
    assert len(data["digest"]) == 64


def test_report_serialization():
    _, _, operator, target = (
        operator_fixture()
    )
    report = operator.ensure_target(
        target
    )
    data = report.to_dict()
    assert data["state"] == "current"
    assert data["ok"] is True
    assert data["verification"]["valid"] is True
    assert data["digest"] == report.digest


def test_fleet_report_rejects_unsorted_reports():
    env, _, operator, target = (
        operator_fixture()
    )
    first = operator.ensure_target(
        target
    )
    older_target = DurableProofWindowTarget(
        "journal",
        env.journal.root_for_sequence(4),
    )
    second = operator.ensure_target(
        older_target
    )
    ordered = tuple(
        sorted(
            (first, second),
            key=lambda item: item.target.key,
        )
    )
    with pytest.raises(ValueError):
        DurableProofWindowFleetReport(
            operator.policy.digest,
            tuple(reversed(ordered)),
            (),
        )


def test_fleet_report_rejects_duplicate_mutations():
    _, _, operator, target = (
        operator_fixture()
    )
    report = operator.ensure_target(
        target
    )
    with pytest.raises(ValueError):
        DurableProofWindowFleetReport(
            operator.policy.digest,
            (report,),
            (target.key, target.key),
        )
