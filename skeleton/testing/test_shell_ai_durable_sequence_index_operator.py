"""Operational tests for durable sequence-index inspection and repair."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
    DistributedJournalSequenceIndex,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_sequence_index import (
    DurableSequenceIndexChainReport,
    DurableSequenceIndexError,
    DurableSequenceIndexFinding,
    DurableSequenceIndexFleetReport,
    DurableSequenceIndexOperator,
    DurableSequenceIndexPolicy,
    DurableSequenceIndexState,
)
from skeleton.shells.distributed_receipts import (
    DistributedReceiptChain,
    DistributedReceiptSequenceIndex,
)
from skeleton.shells.receipts import ExecutionReceipt


def fp(char: str) -> str:
    return char * 64


def receipt(index: int) -> ExecutionReceipt:
    return ExecutionReceipt(
        command="python",
        correlation_id=f"corr-{index}",
        fingerprint=fp(chr(96 + ((index - 1) % 20) + 1)),
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
        receipt_id=f"receipt-{index}",
    )


def chains(count: int = 8):
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
        clock=lambda: 1.0,
    )
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    for index in range(1, count + 1):
        journal.append(
            f"event.{index}",
            session_id="session",
            intent_id="intent",
            proposal_id=f"proposal-{index}",
        )
        receipts.append(receipt(index))
    return backend, journal, receipts


def test_inspect_healthy_mixed_fleet():
    _, journal, receipts = chains(6)
    report = DurableSequenceIndexOperator().inspect(
        {
            "journal": journal,
            "receipts": receipts,
        }
    )
    assert report.ok
    assert report.healthy == 2
    assert report.missing == 0
    assert report.corrupt == 0
    assert report.bounded_out == 0
    assert report.errors == 0
    assert report.repaired == 0
    assert {
        item.chain_id
        for item in report.chains
    } == {"journal", "receipts"}
    assert all(item.healthy for item in report.chains)
    assert all(
        item.sample_windows_verified > 0
        for item in report.chains
    )


def test_inspect_is_deterministically_sorted():
    _, journal, receipts = chains(2)
    report = DurableSequenceIndexOperator().inspect(
        {
            "z-receipts": receipts,
            "a-journal": journal,
        }
    )
    assert [
        item.chain_id
        for item in report.chains
    ] == ["a-journal", "z-receipts"]


def test_missing_journal_index_is_classified_repairable():
    backend, journal, receipts = chains(4)
    key = journal._sequence_key(2)
    record = backend.get("journal", key)
    backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    report = DurableSequenceIndexOperator().inspect(
        {"journal": journal, "receipts": receipts}
    )
    journal_report = next(
        item
        for item in report.chains
        if item.chain_id == "journal"
    )
    assert journal_report.state is DurableSequenceIndexState.MISSING
    assert journal_report.repairable
    assert not journal_report.healthy
    assert journal_report.missing == 1
    assert journal_report.first_missing_sequence == 2
    assert any(
        item.code == "index.missing"
        for item in journal_report.findings
    )


def test_missing_receipt_index_is_classified_repairable():
    backend, journal, receipts = chains(4)
    key = receipts._sequence_key(3)
    record = backend.get("receipts", key)
    backend.delete(
        "receipts",
        key,
        expected_revision=record.revision,
    )
    report = DurableSequenceIndexOperator().inspect(
        {"journal": journal, "receipts": receipts}
    )
    receipt_report = next(
        item
        for item in report.chains
        if item.chain_id == "receipts"
    )
    assert receipt_report.state is DurableSequenceIndexState.MISSING
    assert receipt_report.repairable
    assert receipt_report.missing == 1
    assert receipt_report.first_missing_sequence == 3


def test_repair_restores_missing_journal_index():
    backend, journal, receipts = chains(5)
    key = journal._sequence_key(4)
    record = backend.get("journal", key)
    backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    operator = DurableSequenceIndexOperator()
    report = operator.repair(
        {"journal": journal, "receipts": receipts}
    )
    assert report.ok
    journal_report = next(
        item
        for item in report.chains
        if item.chain_id == "journal"
    )
    assert journal_report.healthy
    assert journal_report.repaired
    assert journal.inspect_sequence_indexes().healthy


def test_repair_restores_missing_receipt_index():
    backend, journal, receipts = chains(5)
    key = receipts._sequence_key(4)
    record = backend.get("receipts", key)
    backend.delete(
        "receipts",
        key,
        expected_revision=record.revision,
    )
    operator = DurableSequenceIndexOperator()
    report = operator.repair(
        {"journal": journal, "receipts": receipts}
    )
    assert report.ok
    receipt_report = next(
        item
        for item in report.chains
        if item.chain_id == "receipts"
    )
    assert receipt_report.healthy
    assert receipt_report.repaired
    assert receipts.inspect_sequence_indexes().healthy


def test_repair_can_fix_multiple_chains_in_one_pass():
    backend, journal, receipts = chains(5)
    for namespace, chain, sequence in (
        ("journal", journal, 2),
        ("receipts", receipts, 3),
    ):
        key = chain._sequence_key(sequence)
        record = backend.get(namespace, key)
        backend.delete(
            namespace,
            key,
            expected_revision=record.revision,
        )
    report = DurableSequenceIndexOperator().repair(
        {"journal": journal, "receipts": receipts}
    )
    assert report.ok
    assert report.repaired == 2
    assert all(item.repaired for item in report.chains)


def test_corrupt_journal_index_is_not_repaired():
    backend, journal, receipts = chains(4)
    events = journal.snapshot()
    key = journal._sequence_key(1)
    record = backend.get("journal", key)
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            events[1].event_hash,
        ),
    )
    operator = DurableSequenceIndexOperator()
    report = operator.repair(
        {"journal": journal, "receipts": receipts}
    )
    journal_report = next(
        item
        for item in report.chains
        if item.chain_id == "journal"
    )
    assert journal_report.state is DurableSequenceIndexState.CORRUPT
    assert not journal_report.repaired
    assert not report.ok


def test_corrupt_receipt_index_is_not_repaired():
    backend, journal, receipts = chains(4)
    items = receipts.snapshot()
    key = receipts._sequence_key(1)
    record = backend.get("receipts", key)
    backend.compare_and_swap(
        "receipts",
        key,
        expected_revision=record.revision,
        value=DistributedReceiptSequenceIndex(
            1,
            items[1].receipt_hash,
        ),
    )
    report = DurableSequenceIndexOperator().repair(
        {"journal": journal, "receipts": receipts}
    )
    receipt_report = next(
        item
        for item in report.chains
        if item.chain_id == "receipts"
    )
    assert receipt_report.state is DurableSequenceIndexState.CORRUPT
    assert not receipt_report.repaired
    assert not report.ok


def test_require_healthy_accepts_healthy_fleet():
    _, journal, receipts = chains(3)
    report = DurableSequenceIndexOperator().require_healthy(
        {"journal": journal, "receipts": receipts}
    )
    assert report.ok


def test_require_healthy_rejects_missing_index_without_repair():
    backend, journal, receipts = chains(3)
    key = journal._sequence_key(2)
    record = backend.get("journal", key)
    backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DurableSequenceIndexError,
        match="not healthy",
    ):
        DurableSequenceIndexOperator().require_healthy(
            {"journal": journal, "receipts": receipts}
        )


def test_require_healthy_can_repair_missing_index():
    backend, journal, receipts = chains(3)
    key = journal._sequence_key(2)
    record = backend.get("journal", key)
    backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    report = DurableSequenceIndexOperator().require_healthy(
        {"journal": journal, "receipts": receipts},
        repair_missing=True,
    )
    assert report.ok
    assert report.repaired == 1


def test_require_healthy_never_repairs_corruption():
    backend, journal, receipts = chains(3)
    events = journal.snapshot()
    key = journal._sequence_key(1)
    record = backend.get("journal", key)
    backend.compare_and_swap(
        "journal",
        key,
        expected_revision=record.revision,
        value=DistributedJournalSequenceIndex(
            1,
            events[1].event_hash,
        ),
    )
    with pytest.raises(
        DurableSequenceIndexError,
        match="not healthy",
    ):
        DurableSequenceIndexOperator().require_healthy(
            {"journal": journal, "receipts": receipts},
            repair_missing=True,
        )


def test_repair_disabled_by_policy():
    _, journal, receipts = chains(2)
    operator = DurableSequenceIndexOperator(
        DurableSequenceIndexPolicy(
            allow_missing_repair=False,
        )
    )
    with pytest.raises(
        DurableSequenceIndexError,
        match="disabled",
    ):
        operator.repair(
            {"journal": journal, "receipts": receipts}
        )


def test_require_healthy_can_be_advisory():
    backend, journal, receipts = chains(3)
    key = journal._sequence_key(2)
    record = backend.get("journal", key)
    backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    operator = DurableSequenceIndexOperator(
        DurableSequenceIndexPolicy(
            require_healthy=False,
        )
    )
    report = operator.require_healthy(
        {"journal": journal, "receipts": receipts}
    )
    assert not report.ok
    assert report.missing == 1


def test_chain_count_bound():
    _, journal, _ = chains(1)
    operator = DurableSequenceIndexOperator(
        DurableSequenceIndexPolicy(
            max_chains=1,
        )
    )
    with pytest.raises(
        DurableSequenceIndexError,
        match="count",
    ):
        operator.inspect(
            {
                "one": journal,
                "two": journal,
            }
        )


def test_item_bound_classifies_bounded_out():
    _, journal, receipts = chains(5)
    operator = DurableSequenceIndexOperator(
        DurableSequenceIndexPolicy(
            max_items_per_chain=4,
        )
    )
    report = operator.inspect(
        {"journal": journal, "receipts": receipts}
    )
    assert report.bounded_out == 2
    assert not report.ok
    assert all(
        item.state is DurableSequenceIndexState.BOUNDED_OUT
        for item in report.chains
    )


class MissingSurface:
    def head(self):
        return type("Head", (), {
            "sequence": 0,
            "root_hash": fp("a"),
        })()


def test_missing_chain_surface_becomes_type_error():
    operator = DurableSequenceIndexOperator()
    with pytest.raises(TypeError, match="inspect_sequence_indexes"):
        operator.inspect({"bad": MissingSurface()})


class ExplodingInspectChain:
    def head(self):
        return type("Head", (), {
            "sequence": 2,
            "root_hash": fp("a"),
        })()

    def inspect_sequence_indexes(self, *, max_items):
        raise RuntimeError("backend unavailable")

    def repair_sequence_indexes(self, *, max_items):
        raise RuntimeError("backend unavailable")

    def root_for_sequence(self, sequence, *, repair_missing=True):
        return fp("a")

    def snapshot_range(
        self,
        start_sequence,
        end_sequence,
        *,
        max_items,
        repair_missing=True,
    ):
        return ()


def test_unexpected_inspection_failure_is_error_state():
    report = DurableSequenceIndexOperator().inspect(
        {"bad": ExplodingInspectChain()}
    )
    assert report.errors == 1
    item = report.chains[0]
    assert item.state is DurableSequenceIndexState.ERROR
    assert any(
        finding.code == "index.inspect_failed"
        for finding in item.findings
    )


class SampleFailureChain:
    class Health:
        inspected = 3
        indexed = 3
        missing = 0
        corrupt = 0
        first_missing_sequence = None
        first_corrupt_sequence = None
        healthy = True

    def head(self):
        return type("Head", (), {
            "sequence": 3,
            "root_hash": fp("a"),
        })()

    def inspect_sequence_indexes(self, *, max_items):
        return self.Health()

    def repair_sequence_indexes(self, *, max_items):
        return self.Health()

    def root_for_sequence(self, sequence, *, repair_missing=True):
        return fp("a")

    def snapshot_range(
        self,
        start_sequence,
        end_sequence,
        *,
        max_items,
        repair_missing=True,
    ):
        raise RuntimeError("sample failure")


def test_sample_window_failure_marks_corrupt():
    report = DurableSequenceIndexOperator().inspect(
        {"sample": SampleFailureChain()}
    )
    item = report.chains[0]
    assert item.state is DurableSequenceIndexState.CORRUPT
    assert any(
        finding.code == "index.sample_failed"
        for finding in item.findings
    )


def test_sample_verification_can_be_disabled():
    report = DurableSequenceIndexOperator(
        DurableSequenceIndexPolicy(
            verify_sample_windows=False,
        )
    ).inspect(
        {"sample": SampleFailureChain()}
    )
    assert report.ok
    assert report.chains[0].sample_windows_verified == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_items_per_chain", 0),
        ("max_chains", 0),
        ("sample_window_items", 0),
        ("max_items_per_chain", True),
    ],
)
def test_policy_positive_integer_validation(field, value):
    values = {
        "max_items_per_chain": 100,
        "max_chains": 4,
        "allow_missing_repair": True,
        "require_healthy": True,
        "verify_sample_windows": True,
        "sample_window_items": 4,
    }
    values[field] = value
    with pytest.raises(ValueError):
        DurableSequenceIndexPolicy(**values)


@pytest.mark.parametrize(
    "field",
    [
        "allow_missing_repair",
        "require_healthy",
        "verify_sample_windows",
    ],
)
def test_policy_bool_validation(field):
    values = {
        "allow_missing_repair": True,
        "require_healthy": True,
        "verify_sample_windows": True,
    }
    values[field] = "yes"
    with pytest.raises(ValueError, match="bool"):
        DurableSequenceIndexPolicy(**values)


def test_policy_digest_is_deterministic():
    first = DurableSequenceIndexPolicy()
    second = DurableSequenceIndexPolicy()
    assert first.digest == second.digest
    assert len(first.digest) == 64


def test_policy_digest_changes_with_behavior():
    first = DurableSequenceIndexPolicy()
    second = DurableSequenceIndexPolicy(
        sample_window_items=32,
    )
    assert first.digest != second.digest


def test_policy_to_dict():
    policy = DurableSequenceIndexPolicy(
        max_items_per_chain=10,
        max_chains=2,
        allow_missing_repair=False,
        require_healthy=False,
        verify_sample_windows=False,
        sample_window_items=3,
    )
    assert policy.to_dict() == {
        "max_items_per_chain": 10,
        "max_chains": 2,
        "allow_missing_repair": False,
        "require_healthy": False,
        "verify_sample_windows": False,
        "sample_window_items": 3,
    }


def test_finding_validation():
    with pytest.raises(ValueError, match="code"):
        DurableSequenceIndexFinding("", "message")
    with pytest.raises(ValueError, match="message"):
        DurableSequenceIndexFinding("code", "")


def test_finding_to_dict():
    finding = DurableSequenceIndexFinding(
        "index.missing",
        "one locator missing",
    )
    assert finding.to_dict() == {
        "code": "index.missing",
        "message": "one locator missing",
    }


def chain_report(
    state=DurableSequenceIndexState.HEALTHY,
    *,
    chain_id="chain",
    repaired=False,
):
    return DurableSequenceIndexChainReport(
        chain_id,
        state,
        3,
        fp("a"),
        3,
        3 if state is DurableSequenceIndexState.HEALTHY else 2,
        1 if state is DurableSequenceIndexState.MISSING else 0,
        1 if state is DurableSequenceIndexState.CORRUPT else 0,
        2 if state is DurableSequenceIndexState.MISSING else None,
        2 if state is DurableSequenceIndexState.CORRUPT else None,
        2,
        repaired,
        fp("p"),
        (),
    )


def test_chain_report_properties():
    healthy = chain_report()
    assert healthy.healthy
    assert not healthy.repairable

    missing = chain_report(
        DurableSequenceIndexState.MISSING
    )
    assert not missing.healthy
    assert missing.repairable

    corrupt = chain_report(
        DurableSequenceIndexState.CORRUPT
    )
    assert not corrupt.healthy
    assert not corrupt.repairable


def test_chain_report_digest_is_stable():
    first = chain_report()
    second = chain_report()
    assert first.digest == second.digest
    assert len(first.digest) == 64


def test_chain_report_to_dict():
    report = chain_report(
        DurableSequenceIndexState.MISSING,
        repaired=False,
    )
    data = report.to_dict()
    assert data["chain_id"] == "chain"
    assert data["state"] == "missing"
    assert data["healthy"] is False
    assert data["repairable"] is True
    assert data["digest"] == report.digest


def test_chain_report_validates_chain_id():
    with pytest.raises(ValueError, match="chain_id"):
        replace(chain_report(), chain_id="")


def test_chain_report_validates_head_root():
    with pytest.raises(ValueError, match="head_root"):
        replace(chain_report(), head_root="bad")


def test_chain_report_validates_policy_digest():
    with pytest.raises(ValueError, match="policy_digest"):
        replace(chain_report(), policy_digest="bad")


def test_fleet_report_aggregates_states():
    reports = (
        chain_report(
            DurableSequenceIndexState.HEALTHY,
            chain_id="healthy",
            repaired=True,
        ),
        chain_report(
            DurableSequenceIndexState.MISSING,
            chain_id="missing",
        ),
        chain_report(
            DurableSequenceIndexState.CORRUPT,
            chain_id="corrupt",
        ),
        chain_report(
            DurableSequenceIndexState.BOUNDED_OUT,
            chain_id="bounded",
        ),
        chain_report(
            DurableSequenceIndexState.ERROR,
            chain_id="error",
        ),
    )
    fleet = DurableSequenceIndexFleetReport(
        reports,
        fp("p"),
    )
    assert fleet.healthy == 1
    assert fleet.missing == 1
    assert fleet.corrupt == 1
    assert fleet.bounded_out == 1
    assert fleet.errors == 1
    assert fleet.repaired == 1
    assert not fleet.ok


def test_fleet_report_rejects_duplicate_chain_ids():
    with pytest.raises(ValueError, match="duplicate"):
        DurableSequenceIndexFleetReport(
            (
                chain_report(chain_id="same"),
                chain_report(chain_id="same"),
            ),
            fp("p"),
        )


def test_fleet_report_digest_is_stable():
    fleet = DurableSequenceIndexFleetReport(
        (
            chain_report(chain_id="a"),
            chain_report(chain_id="b"),
        ),
        fp("p"),
    )
    same = DurableSequenceIndexFleetReport(
        (
            chain_report(chain_id="a"),
            chain_report(chain_id="b"),
        ),
        fp("p"),
    )
    assert fleet.digest == same.digest


def test_fleet_to_dict():
    fleet = DurableSequenceIndexFleetReport(
        (chain_report(),),
        fp("p"),
    )
    data = fleet.to_dict()
    assert data["ok"] is True
    assert data["healthy"] == 1
    assert data["digest"] == fleet.digest
    assert len(data["chains"]) == 1


def test_inspect_requires_mapping():
    with pytest.raises(TypeError, match="mapping"):
        DurableSequenceIndexOperator().inspect([])


def test_inspect_requires_at_least_one_chain():
    with pytest.raises(ValueError, match="at least one"):
        DurableSequenceIndexOperator().inspect({})


def test_operator_policy_type_validation():
    with pytest.raises(TypeError, match="policy"):
        DurableSequenceIndexOperator(object())


def test_empty_chains_remain_healthy():
    backend = InMemoryFencedStore()
    journal = DistributedAIDecisionJournal(
        backend,
        namespace="journal",
    )
    receipts = DistributedReceiptChain(
        backend,
        namespace="receipts",
    )
    report = DurableSequenceIndexOperator().inspect(
        {"journal": journal, "receipts": receipts}
    )
    assert report.ok
    assert all(
        item.head_sequence == 0
        for item in report.chains
    )
    assert all(
        item.sample_windows_verified == 0
        for item in report.chains
    )


def test_sample_windows_cover_head_and_prefix_for_large_chain():
    _, journal, _ = chains(30)
    report = DurableSequenceIndexOperator(
        DurableSequenceIndexPolicy(
            sample_window_items=4,
        )
    ).inspect({"journal": journal})
    assert report.ok
    assert report.chains[0].sample_windows_verified == 3


def test_repair_leaves_healthy_chain_unmodified():
    backend, journal, _ = chains(3)
    before = tuple(
        backend.get(
            "journal",
            journal._sequence_key(sequence),
        ).revision
        for sequence in range(1, 4)
    )
    report = DurableSequenceIndexOperator().repair(
        {"journal": journal}
    )
    after = tuple(
        backend.get(
            "journal",
            journal._sequence_key(sequence),
        ).revision
        for sequence in range(1, 4)
    )
    assert before == after
    assert report.ok
    assert report.repaired == 0


def test_repair_result_records_policy_digest():
    backend, journal, _ = chains(3)
    key = journal._sequence_key(1)
    record = backend.get("journal", key)
    backend.delete(
        "journal",
        key,
        expected_revision=record.revision,
    )
    policy = DurableSequenceIndexPolicy(
        sample_window_items=2,
    )
    report = DurableSequenceIndexOperator(
        policy
    ).repair({"journal": journal})
    assert report.policy_digest == policy.digest
    assert report.chains[0].policy_digest == policy.digest


def test_require_healthy_error_names_bad_chain():
    backend, journal, receipts = chains(3)
    key = receipts._sequence_key(2)
    record = backend.get("receipts", key)
    backend.delete(
        "receipts",
        key,
        expected_revision=record.revision,
    )
    with pytest.raises(
        DurableSequenceIndexError,
        match="receipts=missing",
    ):
        DurableSequenceIndexOperator().require_healthy(
            {"journal": journal, "receipts": receipts}
        )
