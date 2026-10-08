"""Durable causal inbox acceptance and adversarial restart/concurrency tests."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3

import pytest

from skeleton.ai.inbox_causality import (
    InboundMessage, InboxLedger, processing_receipt, quarantine_receipt,
)
from skeleton.ai.inbox_sqlite import SQLiteInboxLedger


def msg(
    seq: int, *, producer: str = "source", epoch: int = 1,
    payload: str = "payload", causes: tuple[str, ...] = (),
) -> InboundMessage:
    return InboundMessage.create(producer, epoch, seq, payload, causes)


def test_canonical_inbox_receipt_identity_matches_reference(tmp_path: Path):
    state = tmp_path / "inbox.sqlite"
    first, second = msg(0), msg(1)
    reference = InboxLedger()
    with SQLiteInboxLedger(state) as durable:
        assert durable.admit(first) is None
        receipt = durable.commit(first, "write-0", ("effect-a", "effect-b"))
        expected = reference.commit(first, "write-0", ("effect-b", "effect-a"))
        assert receipt == expected
        assert receipt == processing_receipt(first, "write-0", ("effect-a", "effect-b"))
        assert durable.admit(first) == receipt
        assert durable.commit(first, "write-0", ("effect-b", "effect-a")) == receipt
        assert durable.commit(second, "write-1") == reference.commit(second, "write-1")


def test_processed_receipts_survive_restart_and_are_not_replayed(tmp_path: Path):
    path = tmp_path / "inbox.sqlite"
    first = msg(0)
    with SQLiteInboxLedger(path) as inbox:
        receipt = inbox.commit(first, "write-a", ("effect-1",))
    with SQLiteInboxLedger(path) as reopened:
        assert reopened.admit(first) == receipt
        assert reopened.commit(first, "write-a", ("effect-1",)) == receipt
        with pytest.raises(PermissionError, match="changed processing effect"):
            reopened.commit(first, "write-b", ("effect-1",))
        assert reopened.commit(msg(1), "write-next").sequence == 1


def test_producer_sequence_gap_refused_without_mutating_highwater(tmp_path: Path):
    with SQLiteInboxLedger(tmp_path / "inbox.sqlite") as inbox:
        first = msg(0)
        inbox.commit(first, "write-a")
        with pytest.raises(PermissionError, match="sequence gap"):
            inbox.commit(msg(2), "write-invalid")
        assert inbox.commit(msg(1), "write-b").sequence == 1


def test_divergent_same_sequence_cannot_bypass_inbox(tmp_path: Path):
    with SQLiteInboxLedger(tmp_path / "inbox.sqlite") as inbox:
        inbox.commit(msg(0, payload="one"), "write-one")
        with pytest.raises(PermissionError, match="different identity"):
            inbox.commit(msg(0, payload="two"), "write-two")


def test_epoch_advancement_and_stale_replay_protection(tmp_path: Path):
    path = tmp_path / "inbox.sqlite"
    initial = msg(0, epoch=1)
    with SQLiteInboxLedger(path) as inbox:
        prior = inbox.commit(initial, "write-old")
        latest = inbox.commit(msg(0, epoch=2), "write-new")
        assert latest.producer_epoch == 2
    with SQLiteInboxLedger(path) as inbox:
        assert inbox.admit(initial) == prior
        with pytest.raises(PermissionError, match="stale producer epoch"):
            inbox.commit(msg(1, epoch=1), "late")
        assert inbox.commit(msg(1, epoch=2), "write-next").sequence == 1


def test_causal_dependency_requires_committed_predecessor(tmp_path: Path):
    parent = msg(0, producer="parent")
    child = msg(0, producer="child", causes=(parent.message_id,))
    with SQLiteInboxLedger(tmp_path / "inbox.sqlite") as inbox:
        with pytest.raises(PermissionError, match="causal predecessor"):
            inbox.commit(child, "write-child")
        inbox.commit(parent, "write-parent")
        assert inbox.commit(child, "write-child").message_id == child.message_id


def test_causal_barrier_survives_restart(tmp_path: Path):
    path = tmp_path / "inbox.sqlite"
    parent = msg(0, producer="parent")
    child = msg(0, producer="child", causes=(parent.message_id,))
    with SQLiteInboxLedger(path) as inbox:
        inbox.commit(parent, "write-parent")
    with SQLiteInboxLedger(path) as inbox:
        assert inbox.commit(child, "write-child").producer_id == "child"


def test_duplicate_effect_id_fails_before_transaction(tmp_path: Path):
    first = msg(0)
    with SQLiteInboxLedger(tmp_path / "inbox.sqlite") as inbox:
        with pytest.raises(ValueError, match="duplicate"):
            inbox.commit(first, "write", ("effect-a", "effect-a"))
        assert inbox.commit(first, "write", ("effect-a",)).sequence == 0


def test_bounded_effect_and_causal_contracts(tmp_path: Path):
    with SQLiteInboxLedger(tmp_path / "inbox.sqlite") as inbox:
        with pytest.raises(ValueError, match="effect receipt count"):
            inbox.commit(msg(0), "write", tuple(f"e{i}" for i in range(65)))
        oversize = msg(0, causes=tuple(f"id{i}" for i in range(65)))
        with pytest.raises(ValueError, match="causal IDs"):
            inbox.commit(oversize, "write")


def test_capacity_refusal_remains_atomic_and_existing_receipts_replay(tmp_path: Path):
    with SQLiteInboxLedger(tmp_path / "inbox.sqlite", max_receipts=2) as inbox:
        first = msg(0)
        expected = inbox.commit(first, "write-0")
        inbox.commit(msg(1), "write-1")
        with pytest.raises(PermissionError, match="capacity"):
            inbox.commit(msg(2), "write-2")
        assert inbox.commit(first, "write-0") == expected
        # Capacity is not a license to skip messages and advance sequences.
        with pytest.raises(PermissionError, match="sequence gap"):
            inbox.commit(msg(3), "write-3")


def test_quarantine_receipt_immutable_across_restart(tmp_path: Path):
    path = tmp_path / "inbox.sqlite"
    message = msg(0)
    with SQLiteInboxLedger(path) as inbox:
        receipt = inbox.quarantine(message, "malformed", "evidence")
        assert receipt == quarantine_receipt(message, "malformed", "evidence")
    with SQLiteInboxLedger(path) as inbox:
        assert inbox.quarantine(message, "malformed", "evidence") == receipt
        with pytest.raises(PermissionError, match="evidence changed"):
            inbox.quarantine(message, "other", "evidence")


def test_quarantine_budget_refused_without_erasing_previous(tmp_path: Path):
    path = tmp_path / "inbox.sqlite"
    with SQLiteInboxLedger(path, max_receipts=1) as inbox:
        first = msg(0)
        original = inbox.quarantine(first, "unsafe", "evidence")
        with pytest.raises(PermissionError, match="quarantine capacity"):
            inbox.quarantine(msg(1), "unsafe", "second")
        assert inbox.quarantine(first, "unsafe", "evidence") == original


def test_replay_policy_cannot_expand_on_reopen_without_migration(tmp_path: Path):
    path = tmp_path / "inbox.sqlite"
    with SQLiteInboxLedger(path, replay_window=4, max_receipts=10) as inbox:
        inbox.commit(msg(0), "write")
    with pytest.raises(ValueError, match="persisted inbox policy mismatch"):
        SQLiteInboxLedger(path, replay_window=100, max_receipts=10)
    with pytest.raises(ValueError, match="persisted inbox policy mismatch"):
        SQLiteInboxLedger(path, replay_window=4, max_receipts=11)
    with pytest.raises(ValueError, match="persisted inbox policy mismatch"):
        SQLiteInboxLedger(
            path, replay_window=4, max_receipts=10, require_causal_receipts=False,
        )
    with SQLiteInboxLedger(path, replay_window=4, max_receipts=10) as valid:
        assert valid.admit(msg(0)) is not None


def test_concurrent_process_connections_cannot_double_commit(tmp_path: Path):
    path = tmp_path / "shared.sqlite"
    message = msg(0)
    with SQLiteInboxLedger(path) as first, SQLiteInboxLedger(path) as second:
        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = list(workers.map(
                lambda inbox: inbox.commit(message, "stable", ("effect",)),
                (first, second),
            ))
        assert outcomes[0] == outcomes[1]
        assert first.admit(message) == outcomes[0]
        assert second.admit(message) == outcomes[0]
        assert first.commit(msg(1), "next").sequence == 1


def test_atomic_transaction_rollback_on_injected_write_failure(tmp_path: Path):
    path = tmp_path / "inbox.sqlite"
    with SQLiteInboxLedger(path) as inbox:
        inbox._db.execute(
            """
            CREATE TRIGGER abort_insert BEFORE INSERT ON ai_inbox_processed
            BEGIN SELECT RAISE(ABORT, 'injected disk failure'); END
            """
        )
        with pytest.raises(sqlite3.IntegrityError, match="injected disk failure"):
            inbox.commit(msg(0), "write-0")
        inbox._db.execute("DROP TRIGGER abort_insert")
        assert inbox.commit(msg(0), "write-0").sequence == 0
        assert inbox.commit(msg(1), "write-1").sequence == 1


def test_corrupt_processing_receipt_fails_closed(tmp_path: Path):
    with SQLiteInboxLedger(tmp_path / "inbox.sqlite") as inbox:
        message = msg(0)
        inbox.commit(message, "write")
        inbox._db.execute(
            "UPDATE ai_inbox_processed SET receipt_id='wrong' WHERE message_id=?",
            (message.message_id,),
        )
        with pytest.raises(ValueError, match="digest mismatch"):
            inbox.admit(message)
        with pytest.raises(ValueError, match="digest mismatch"):
            inbox.commit(message, "write")


def test_invalid_message_identity_and_surrogate_rejected(tmp_path: Path):
    with SQLiteInboxLedger(tmp_path / "inbox.sqlite") as inbox:
        original = msg(0)
        corrupted = InboundMessage(
            "wrong-id", original.producer_id, original.producer_epoch,
            original.sequence, original.payload_digest, original.causal_ids,
        )
        with pytest.raises(ValueError, match="noncanonical"):
            inbox.commit(corrupted, "write")
        with pytest.raises(ValueError, match="invalid"):
            inbox.commit(msg(0, producer="bad\\x00name"), "write")


def test_storage_path_rejects_symlink(tmp_path: Path):
    actual = tmp_path / "good.sqlite"
    with SQLiteInboxLedger(actual):
        pass
    link = tmp_path / "link.sqlite"
    try:
        link.symlink_to(actual)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="safe parent"):
        SQLiteInboxLedger(link)


def test_constructor_budget_and_policy_types_refused():
    for invalid in (0, True, -1, 1_000_001):
        with pytest.raises(ValueError):
            SQLiteInboxLedger(replay_window=invalid)
    with pytest.raises(ValueError, match="boolean"):
        SQLiteInboxLedger(require_causal_receipts=1)
