"""Fair, bounded and resumable durable sequence-index backfill tests."""

from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.shells.ai.distributed_journal import DistributedAIDecisionJournal
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_sequence_backfill import (
    DurableSequenceBackfillChainReport,
    DurableSequenceBackfillCursor,
    DurableSequenceBackfillError,
    DurableSequenceBackfillFleetReport,
    DurableSequenceBackfillOperator,
    DurableSequenceBackfillPolicy,
    DurableSequenceBackfillState,
    DurableSequenceBackfillStep,
)
from skeleton.shells.distributed_receipts import DistributedReceiptChain
from skeleton.shells.receipts import ExecutionReceipt
from skeleton.shells.sequence_index import SequenceIndexBackfillBatch


GENESIS = "0" * 64


def fp(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def receipt(index: int) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{index}",
        fingerprint=fp(f"receipt-{index}"),
        started_at="2026-09-19T00:00:00+00:00",
        finished_at="2026-09-19T00:00:01+00:00",
        duration_ms=1.0,
        returncode=0,
        ok=True,
        timed_out=False,
        output_limited=False,
        stdout_bytes=1,
        stderr_bytes=0,
        attempt=1,
        receipt_id=f"receipt-{index}",
    )


def journal(count: int):
    chain = DistributedAIDecisionJournal(
        InMemoryFencedStore(),
        clock=lambda: 10.0,
    )
    for index in range(count):
        chain.append(
            "backfill.test",
            session_id=f"session-{index}",
            intent_id=f"intent-{index}",
            proposal_id=f"proposal-{index}",
        )
    return chain


def receipts(count: int):
    chain = DistributedReceiptChain(
        InMemoryFencedStore()
    )
    for index in range(count):
        chain.append(receipt(index))
    return chain


def remove_indexes(chain, sequences):
    for sequence in sequences:
        key = chain._sequence_key(sequence)
        record = chain.backend.get(
            chain.namespace,
            key,
        )
        if record is not None:
            chain.backend.delete(
                chain.namespace,
                key,
                expected_revision=record.revision,
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_items_per_batch", 0),
        ("max_batches_per_chain", 0),
        ("max_total_items", 0),
        ("max_chains", 0),
        ("max_items_per_batch", True),
        ("continue_on_error", "yes"),
    ],
)
def test_policy_validation(field, value):
    kwargs = dict(
        max_items_per_batch=2,
        max_batches_per_chain=2,
        max_total_items=10,
        max_chains=2,
        continue_on_error=True,
    )
    kwargs[field] = value
    with pytest.raises(ValueError):
        DurableSequenceBackfillPolicy(
            **kwargs
        )


def test_policy_digest_is_stable():
    first = DurableSequenceBackfillPolicy(
        max_items_per_batch=2,
        max_batches_per_chain=3,
    )
    second = DurableSequenceBackfillPolicy(
        max_items_per_batch=2,
        max_batches_per_chain=3,
    )
    assert first.digest == second.digest
    assert len(first.digest) == 64


def test_cursor_complete_at_genesis():
    cursor = DurableSequenceBackfillCursor(
        "chain",
        0,
        GENESIS,
        0,
        GENESIS,
    )
    assert cursor.complete
    assert cursor.progress_fraction == 1.0
    assert cursor.items_processed == 0


def test_cursor_progress_fraction():
    cursor = DurableSequenceBackfillCursor(
        "chain",
        10,
        fp("anchor"),
        4,
        fp("next"),
        3,
        6,
        4,
        2,
    )
    assert cursor.progress_fraction == 0.6
    assert not cursor.complete


@pytest.mark.parametrize(
    "kwargs",
    [
        {"chain_id": ""},
        {"anchor_sequence": -1},
        {"next_sequence": -1},
        {"anchor_root": "bad"},
        {"next_root": "bad"},
        {
            "anchor_sequence": 0,
            "anchor_root": fp("not-genesis"),
            "next_sequence": 0,
            "next_root": GENESIS,
        },
        {
            "anchor_sequence": 1,
            "anchor_root": GENESIS,
            "next_sequence": 1,
            "next_root": fp("next"),
        },
        {
            "anchor_sequence": 2,
            "next_sequence": 3,
        },
        {
            "anchor_sequence": 3,
            "next_sequence": 0,
            "next_root": fp("wrong"),
        },
        {
            "anchor_sequence": 3,
            "next_sequence": 2,
            "next_root": GENESIS,
        },
        {
            "anchor_sequence": 3,
            "next_sequence": 2,
            "items_processed": 2,
            "indexed": 1,
            "already_indexed": 0,
        },
    ],
)
def test_cursor_validation(kwargs):
    values = dict(
        chain_id="chain",
        anchor_sequence=3,
        anchor_root=fp("anchor"),
        next_sequence=2,
        next_root=fp("next"),
        batches_completed=0,
        items_processed=0,
        indexed=0,
        already_indexed=0,
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        DurableSequenceBackfillCursor(
            **values
        )


def test_cursor_digest_changes_with_progress():
    first = DurableSequenceBackfillCursor(
        "chain",
        4,
        fp("anchor"),
        4,
        fp("anchor"),
    )
    second = DurableSequenceBackfillCursor(
        "chain",
        4,
        fp("anchor"),
        2,
        fp("next"),
        1,
        2,
        2,
        0,
    )
    assert first.digest != second.digest


@pytest.mark.parametrize("factory", [journal, receipts])
def test_begin_pins_current_head(factory):
    chain = factory(5)
    operator = DurableSequenceBackfillOperator()
    cursor = operator.begin(
        "chain",
        chain,
    )
    assert cursor.anchor_sequence == 5
    assert cursor.next_sequence == 5
    assert cursor.anchor_root == chain.root_hash()
    assert cursor.next_root == chain.root_hash()
    assert not cursor.complete


@pytest.mark.parametrize("factory", [journal, receipts])
def test_begin_empty_chain_is_complete(factory):
    chain = factory(0)
    cursor = DurableSequenceBackfillOperator().begin(
        "chain",
        chain,
    )
    assert cursor.complete
    assert cursor.anchor_root == GENESIS
    assert cursor.next_root == GENESIS


@pytest.mark.parametrize("factory", [journal, receipts])
def test_single_step_advances_cursor(factory):
    chain = factory(5)
    remove_indexes(chain, range(1, 6))
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
        )
    )
    before = operator.begin(
        "chain",
        chain,
    )
    step = operator.step(
        "chain",
        chain,
        before,
    )
    assert step is not None
    assert step.batch.covered_items == 2
    assert step.batch.indexed == 2
    assert step.after.next_sequence == 3
    assert step.after.items_processed == 2
    assert step.after.indexed == 2
    assert step.after.batches_completed == 1


@pytest.mark.parametrize("factory", [journal, receipts])
def test_step_complete_cursor_is_noop(factory):
    chain = factory(0)
    operator = DurableSequenceBackfillOperator()
    cursor = operator.begin(
        "chain",
        chain,
    )
    assert operator.step(
        "chain",
        chain,
        cursor,
    ) is None


@pytest.mark.parametrize("factory", [journal, receipts])
def test_step_honors_smaller_call_budget(factory):
    chain = factory(5)
    remove_indexes(chain, range(1, 6))
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=4,
        )
    )
    cursor = operator.begin("chain", chain)
    step = operator.step(
        "chain",
        chain,
        cursor,
        max_items=1,
    )
    assert step.batch.covered_items == 1


@pytest.mark.parametrize("factory", [journal, receipts])
def test_step_clamps_large_call_budget_to_policy(factory):
    chain = factory(5)
    remove_indexes(chain, range(1, 6))
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
        )
    )
    cursor = operator.begin("chain", chain)
    step = operator.step(
        "chain",
        chain,
        cursor,
        max_items=99,
    )
    assert step.batch.covered_items == 2


@pytest.mark.parametrize("factory", [journal, receipts])
def test_run_completes_one_chain(factory):
    chain = factory(7)
    remove_indexes(chain, range(1, 8))
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
            max_batches_per_chain=10,
            max_total_items=20,
        )
    )
    report = operator.require_complete(
        {"chain": chain}
    )
    assert report.all_complete
    assert report.complete == 1
    assert report.errors == 0
    assert report.total_items_processed == 7
    assert report.chains[0].indexed_this_run == 7
    assert report.chains[0].cursor.complete


@pytest.mark.parametrize("factory", [journal, receipts])
def test_run_counts_already_indexed(factory):
    chain = factory(5)
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
            max_batches_per_chain=10,
            max_total_items=20,
        )
    )
    report = operator.require_complete(
        {"chain": chain}
    )
    assert report.total_items_processed == 5
    assert report.chains[0].indexed_this_run == 0
    assert (
        report.chains[0].already_indexed_this_run
        == 5
    )


@pytest.mark.parametrize("factory", [journal, receipts])
def test_per_chain_batch_limit_pauses(factory):
    chain = factory(8)
    remove_indexes(chain, range(1, 9))
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
            max_batches_per_chain=2,
            max_total_items=100,
        )
    )
    report = operator.run(
        {"chain": chain}
    )
    assert not report.all_complete
    assert report.paused == 1
    item = report.chains[0]
    assert (
        item.state
        is DurableSequenceBackfillState.PAUSED
    )
    assert item.batches_run == 2
    assert item.items_processed_this_run == 4
    assert item.cursor.next_sequence == 4


@pytest.mark.parametrize("factory", [journal, receipts])
def test_paused_cursor_can_resume_in_new_operator(factory):
    chain = factory(8)
    remove_indexes(chain, range(1, 9))
    first_operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
            max_batches_per_chain=2,
            max_total_items=100,
        )
    )
    first = first_operator.run(
        {"chain": chain}
    )
    cursor = first.cursors["chain"]
    second_operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
            max_batches_per_chain=10,
            max_total_items=100,
        )
    )
    second = second_operator.require_complete(
        {"chain": chain},
        cursors={"chain": cursor},
    )
    assert second.all_complete
    assert second.chains[0].cursor.items_processed == 8


@pytest.mark.parametrize("factory", [journal, receipts])
def test_global_item_limit_pauses(factory):
    one = factory(6)
    two = factory(6)
    remove_indexes(one, range(1, 7))
    remove_indexes(two, range(1, 7))
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
            max_batches_per_chain=10,
            max_total_items=5,
            max_chains=2,
        )
    )
    report = operator.run(
        {"a": one, "b": two}
    )
    assert report.total_items_processed == 5
    assert not report.all_complete
    assert report.paused >= 1


@pytest.mark.parametrize("factory", [journal, receipts])
def test_round_robin_gives_both_chains_progress(factory):
    one = factory(8)
    two = factory(8)
    remove_indexes(one, range(1, 9))
    remove_indexes(two, range(1, 9))
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
            max_batches_per_chain=10,
            max_total_items=4,
            max_chains=2,
        )
    )
    report = operator.run(
        {"a": one, "b": two}
    )
    by_id = {
        item.chain_id: item
        for item in report.chains
    }
    assert by_id["a"].items_processed_this_run == 2
    assert by_id["b"].items_processed_this_run == 2
    assert by_id["a"].batches_run == 1
    assert by_id["b"].batches_run == 1


@pytest.mark.parametrize("factory", [journal, receipts])
def test_round_robin_second_round_returns_to_first_chain(factory):
    one = factory(8)
    two = factory(8)
    remove_indexes(one, range(1, 9))
    remove_indexes(two, range(1, 9))
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
            max_batches_per_chain=10,
            max_total_items=6,
            max_chains=2,
        )
    )
    report = operator.run(
        {"a": one, "b": two}
    )
    by_id = {
        item.chain_id: item
        for item in report.chains
    }
    assert by_id["a"].items_processed_this_run == 4
    assert by_id["b"].items_processed_this_run == 2
    assert report.rounds == 2


@pytest.mark.parametrize("factory", [journal, receipts])
def test_head_can_advance_after_cursor_capture(factory):
    chain = factory(5)
    remove_indexes(chain, range(1, 6))
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
            max_batches_per_chain=10,
        )
    )
    cursor = operator.begin("chain", chain)
    if isinstance(
        chain,
        DistributedAIDecisionJournal,
    ):
        chain.append(
            "later",
            session_id="later",
            intent_id="later",
        )
    else:
        chain.append(receipt(99))
    report = operator.require_complete(
        {"chain": chain},
        cursors={"chain": cursor},
    )
    assert report.all_complete
    assert (
        report.chains[0].cursor.anchor_sequence
        == 5
    )
    assert (
        report.chains[0].cursor.items_processed
        == 5
    )


class LostAnchorChain:
    def __init__(self):
        self._head = type(
            "Head",
            (),
            {
                "sequence": 2,
                "root_hash": fp("head"),
            },
        )()

    def head(self):
        return self._head

    def root_is_ancestor(self, root_hash):
        return False

    def backfill_sequence_indexes_batch(
        self,
        *,
        end_sequence=None,
        end_root="",
        max_items=1024,
    ):
        raise AssertionError("must not run")


def test_lost_anchor_is_rejected_before_backfill():
    chain = LostAnchorChain()
    operator = DurableSequenceBackfillOperator()
    cursor = DurableSequenceBackfillCursor(
        "chain",
        1,
        fp("old"),
        1,
        fp("old"),
    )
    with pytest.raises(
        DurableSequenceBackfillError,
        match="no longer committed ancestor",
    ):
        operator.step(
            "chain",
            chain,
            cursor,
        )


class ErrorChain:
    def __init__(self, *, message="boom"):
        self.message = message
        self._root = fp("error-root")

    def head(self):
        return type(
            "Head",
            (),
            {
                "sequence": 1,
                "root_hash": self._root,
            },
        )()

    def root_is_ancestor(self, root_hash):
        return root_hash == self._root

    def backfill_sequence_indexes_batch(
        self,
        *,
        end_sequence=None,
        end_root="",
        max_items=1024,
    ):
        raise RuntimeError(self.message)


def test_continue_on_error_reports_error_and_keeps_other_chain():
    good = journal(2)
    remove_indexes(good, (1, 2))
    bad = ErrorChain()
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=1,
            max_total_items=10,
            max_chains=2,
            continue_on_error=True,
        )
    )
    report = operator.run(
        {"bad": bad, "good": good}
    )
    by_id = {
        item.chain_id: item
        for item in report.chains
    }
    assert (
        by_id["bad"].state
        is DurableSequenceBackfillState.ERROR
    )
    assert "RuntimeError: boom" in by_id["bad"].error
    assert by_id["good"].complete
    assert report.errors == 1


def test_stop_on_error_raises_immediately():
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            continue_on_error=False,
        )
    )
    with pytest.raises(
        DurableSequenceBackfillError,
        match="boom",
    ):
        operator.run(
            {"bad": ErrorChain()}
        )


def test_require_complete_raises_for_error():
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            continue_on_error=True,
        )
    )
    with pytest.raises(
        DurableSequenceBackfillError,
        match="encountered errors",
    ):
        operator.require_complete(
            {"bad": ErrorChain()}
        )


@pytest.mark.parametrize("factory", [journal, receipts])
def test_require_complete_raises_when_policy_pauses(factory):
    chain = factory(5)
    remove_indexes(chain, range(1, 6))
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=1,
            max_batches_per_chain=1,
        )
    )
    with pytest.raises(
        DurableSequenceBackfillError,
        match="paused",
    ):
        operator.require_complete(
            {"chain": chain}
        )


class BadTypeChain:
    def head(self):
        return type(
            "Head",
            (),
            {
                "sequence": 1,
                "root_hash": fp("root"),
            },
        )()

    def root_is_ancestor(self, root_hash):
        return True

    def backfill_sequence_indexes_batch(
        self,
        **kwargs,
    ):
        return object()


def test_invalid_batch_type_is_rejected():
    operator = DurableSequenceBackfillOperator()
    chain = BadTypeChain()
    cursor = operator.begin("chain", chain)
    with pytest.raises(
        DurableSequenceBackfillError,
        match="invalid backfill batch type",
    ):
        operator.step(
            "chain",
            chain,
            cursor,
        )


class WrongRequestChain(BadTypeChain):
    def backfill_sequence_indexes_batch(
        self,
        *,
        end_sequence=None,
        end_root="",
        max_items=1024,
    ):
        return SequenceIndexBackfillBatch(
            1,
            fp("different"),
            1,
            1,
            1,
            0,
            0,
            GENESIS,
            True,
        )


def test_batch_request_substitution_is_rejected():
    chain = WrongRequestChain()
    operator = DurableSequenceBackfillOperator()
    cursor = operator.begin("chain", chain)
    with pytest.raises(
        DurableSequenceBackfillError,
        match="changed requested cursor",
    ):
        operator.step(
            "chain",
            chain,
            cursor,
        )


class OversizedBatchChain(BadTypeChain):
    def __init__(self):
        self._root = fp("root-3")

    def head(self):
        return type(
            "Head",
            (),
            {
                "sequence": 3,
                "root_hash": self._root,
            },
        )()

    def backfill_sequence_indexes_batch(
        self,
        *,
        end_sequence=None,
        end_root="",
        max_items=1024,
    ):
        return SequenceIndexBackfillBatch(
            3,
            self._root,
            1,
            3,
            3,
            0,
            0,
            GENESIS,
            True,
        )


def test_batch_may_not_exceed_call_budget():
    chain = OversizedBatchChain()
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=3,
        )
    )
    cursor = operator.begin("chain", chain)
    with pytest.raises(
        DurableSequenceBackfillError,
        match="exceeded batch budget",
    ):
        operator.step(
            "chain",
            chain,
            cursor,
            max_items=2,
        )


@pytest.mark.parametrize("factory", [journal, receipts])
def test_unknown_cursor_chain_is_rejected(factory):
    chain = factory(1)
    operator = DurableSequenceBackfillOperator()
    other = DurableSequenceBackfillCursor(
        "other",
        0,
        GENESIS,
        0,
        GENESIS,
    )
    with pytest.raises(
        DurableSequenceBackfillError,
        match="unknown chain",
    ):
        operator.run(
            {"chain": chain},
            cursors={"other": other},
        )


@pytest.mark.parametrize("factory", [journal, receipts])
def test_cursor_chain_mismatch_is_rejected(factory):
    chain = factory(1)
    operator = DurableSequenceBackfillOperator()
    cursor = DurableSequenceBackfillCursor(
        "other",
        1,
        chain.root_hash(),
        1,
        chain.root_hash(),
    )
    with pytest.raises(
        DurableSequenceBackfillError,
        match="chain mismatch",
    ):
        operator.run(
            {"chain": chain},
            cursors={"chain": cursor},
        )


def test_run_requires_mapping():
    with pytest.raises(TypeError):
        DurableSequenceBackfillOperator().run(
            [("chain", journal(1))]
        )


def test_run_requires_nonempty_chains():
    with pytest.raises(ValueError):
        DurableSequenceBackfillOperator().run(
            {}
        )


def test_run_respects_max_chain_count():
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_chains=1,
        )
    )
    with pytest.raises(
        DurableSequenceBackfillError,
        match="chain count",
    ):
        operator.run(
            {
                "a": journal(1),
                "b": journal(1),
            }
        )


def test_duplicate_normalized_chain_ids_are_rejected():
    operator = DurableSequenceBackfillOperator()
    with pytest.raises(ValueError, match="duplicate"):
        operator.run(
            {
                " a ": journal(1),
                "a": journal(1),
            }
        )


def test_invalid_chain_surface_is_rejected():
    with pytest.raises(TypeError, match="SequenceIndexBackfillableChain"):
        DurableSequenceBackfillOperator().run(
            {"bad": object()}
        )


def test_step_budget_validation():
    chain = journal(1)
    cursor = DurableSequenceBackfillOperator().begin(
        "chain",
        chain,
    )
    with pytest.raises(ValueError, match="max_items"):
        DurableSequenceBackfillOperator().step(
            "chain",
            chain,
            cursor,
            max_items=0,
        )


def test_step_chain_id_validation():
    chain = journal(1)
    cursor = DurableSequenceBackfillOperator().begin(
        "chain",
        chain,
    )
    with pytest.raises(ValueError):
        DurableSequenceBackfillOperator().step(
            "",
            chain,
            cursor,
        )


def test_report_validation():
    cursor = DurableSequenceBackfillCursor(
        "chain",
        0,
        GENESIS,
        0,
        GENESIS,
    )
    complete = DurableSequenceBackfillChainReport(
        "chain",
        DurableSequenceBackfillState.COMPLETE,
        cursor,
        0,
        0,
        0,
        0,
    )
    assert complete.ok
    assert complete.complete
    assert complete.to_dict()["state"] == "complete"

    with pytest.raises(ValueError):
        DurableSequenceBackfillChainReport(
            "chain",
            DurableSequenceBackfillState.ERROR,
            cursor,
            0,
            0,
            0,
            0,
            "",
        )
    with pytest.raises(ValueError):
        DurableSequenceBackfillChainReport(
            "chain",
            DurableSequenceBackfillState.COMPLETE,
            replace(
                cursor,
                anchor_sequence=1,
                anchor_root=fp("root"),
                next_sequence=1,
                next_root=fp("root"),
            ),
            0,
            0,
            0,
            0,
        )


def test_fleet_report_validation_and_cursors():
    cursor = DurableSequenceBackfillCursor(
        "chain",
        0,
        GENESIS,
        0,
        GENESIS,
    )
    chain_report = DurableSequenceBackfillChainReport(
        "chain",
        DurableSequenceBackfillState.COMPLETE,
        cursor,
        0,
        0,
        0,
        0,
    )
    policy = DurableSequenceBackfillPolicy()
    report = DurableSequenceBackfillFleetReport(
        (chain_report,),
        policy.digest,
        0,
        0,
    )
    assert report.ok
    assert report.all_complete
    assert report.complete == 1
    assert report.paused == 0
    assert report.errors == 0
    assert report.cursors["chain"] == cursor
    assert len(report.digest) == 64


def test_step_digest_is_deterministic():
    chain = journal(2)
    remove_indexes(chain, (1, 2))
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=1,
        )
    )
    cursor = operator.begin("chain", chain)
    step = operator.step(
        "chain",
        chain,
        cursor,
    )
    assert len(step.digest) == 64
    assert step.to_dict()["digest"] == step.digest


@pytest.mark.parametrize("factory", [journal, receipts])
def test_resume_cursor_digest_is_stable_across_fresh_operator(factory):
    chain = factory(6)
    remove_indexes(chain, range(1, 7))
    first = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
            max_batches_per_chain=1,
        )
    ).run({"chain": chain})
    cursor = first.cursors["chain"]
    digest = cursor.digest

    second_operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
            max_batches_per_chain=1,
        )
    )
    second_operator._require_cursor(
        "chain",
        chain,
        cursor,
    )
    assert cursor.digest == digest


@pytest.mark.parametrize("factory", [journal, receipts])
def test_finished_cursor_is_idempotent_across_repeated_run(factory):
    chain = factory(3)
    operator = DurableSequenceBackfillOperator(
        DurableSequenceBackfillPolicy(
            max_items_per_batch=2,
        )
    )
    first = operator.require_complete(
        {"chain": chain}
    )
    cursor = first.cursors["chain"]
    second = operator.require_complete(
        {"chain": chain},
        cursors={"chain": cursor},
    )
    assert second.total_items_processed == 0
    assert second.chains[0].batches_run == 0
    assert second.chains[0].cursor == cursor
