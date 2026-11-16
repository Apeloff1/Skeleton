"""Regression tests for encrypted, bounded, journal-compatible offline results."""
from __future__ import annotations

import os
import sqlite3

import pytest

from skeleton.ai.model_runtime.fair_stream_execution_journal import (
    ExecutionOutcomeUnknown, FairStreamExecutionJournal, JournaledExecutionOwner,
)
from skeleton.ai.model_runtime.fair_stream_result_vault import (
    MAX_RESULT_BYTES, SealedFairStreamResultVault, SealedResultUnavailable,
)
from skeleton.ai.model_runtime.fair_stream_session import DispatchPermit
from skeleton.ai.model_runtime.private_sqlite import open_private_sqlite

SESSION = "a" * 32
MODEL = "b" * 64
TOKENIZER = "c" * 64
CHECKPOINT = "d" * 64
LEASE = "e" * 64
RESULT_KEY = b"r" * 32
EXECUTION_KEY = b"x" * 32


def permit(lease=LEASE):
    return DispatchPermit(lease, "request-1", 2, CHECKPOINT, 16, 4096)


def state(p=None):
    p = p or permit()
    return {
        "session_id": SESSION,
        "generation": p.generation,
        "checkpoint_digest": p.checkpoint_digest,
        "checkpoint": {
            "pending": [{
                "lease_id": p.lease_id, "request_id": p.request_id,
                "tenant_id": "tenant-a",
                "tokens": p.tokens, "bytes_reserved": p.bytes_reserved,
            }],
            "requests": [{
                "request_id": p.request_id, "tenant_id": "tenant-a",
                "bytes_per_token": p.bytes_reserved // p.tokens,
            }],
        },
    }


class Backend:
    def __init__(self, payload=b"private offline output", consumed=8, fail=False):
        self.payload = payload
        self.consumed = consumed
        self.fail = fail
        self.calls = 0

    def generate(self, permit, state):
        self.calls += 1
        if self.fail:
            raise OSError("backend may have executed")
        return self.consumed, self.payload


@pytest.fixture
def vault_dir(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    os.chmod(directory, 0o700)
    return str(directory)


def open_vault(directory, backend=None, *, key=RESULT_KEY, create=True):
    handle = open_private_sqlite(
        directory, filename="sealed-results.db", create=create,
    )
    try:
        vault = SealedFairStreamResultVault(
            handle, session_id=SESSION, model_digest=MODEL,
            tokenizer_digest=TOKENIZER, result_key=key,
            backend=backend or Backend(),
        )
    except BaseException:
        handle.close()
        raise
    return handle, vault


def test_result_is_encrypted_and_restart_readable(vault_dir):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    consumed, digest = vault.run_and_commit(permit(), state())
    assert consumed == 8 and len(digest) == 64
    row = handle.connection.execute(
        "SELECT ciphertext, nonce FROM local_fair_stream_sealed_results"
    ).fetchone()
    assert b"private offline output" not in row[0]
    assert len(row[1]) == 12
    assert vault.read_committed(permit(), expected_result_digest=digest) == backend.payload
    handle.close()
    next_handle, restarted = open_vault(vault_dir, create=False)
    try:
        assert restarted.read_committed(permit(), expected_result_digest=digest) == backend.payload
    finally:
        next_handle.close()


def test_journal_executes_backend_once_and_signs_result(vault_dir):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    journal_connection = sqlite3.connect(":memory:", isolation_level=None)
    journal = FairStreamExecutionJournal(
        journal_connection, session_id=SESSION, execution_key=EXECUTION_KEY,
    )
    owner = JournaledExecutionOwner(journal, vault)
    receipt = owner.execute_and_commit(permit(), state())
    assert receipt["result_digest"] and receipt["consumed_tokens"] == 8
    assert vault.read_committed(
        permit(), expected_result_digest=receipt["result_digest"],
    ) == backend.payload
    assert journal.recover_committed_receipt(permit()) == receipt
    with pytest.raises(ExecutionOutcomeUnknown, match="already"):
        owner.execute_and_commit(permit(), state())
    assert backend.calls == 1
    handle.close()
    journal_connection.close()


def test_backend_failure_keeps_running_journal_intent(vault_dir):
    backend = Backend(fail=True)
    handle, vault = open_vault(vault_dir, backend)
    journal = FairStreamExecutionJournal(
        sqlite3.connect(":memory:", isolation_level=None),
        session_id=SESSION, execution_key=EXECUTION_KEY,
    )
    owner = JournaledExecutionOwner(journal, vault)
    with pytest.raises(OSError, match="may have executed"):
        owner.execute_and_commit(permit(), state())
    with pytest.raises(ExecutionOutcomeUnknown, match="already"):
        owner.execute_and_commit(permit(), state())
    with pytest.raises(SealedResultUnavailable, match="not committed"):
        vault.read_committed(permit(), expected_result_digest="f" * 64)
    assert backend.calls == 1
    handle.close()


@pytest.mark.parametrize("consumed,payload", [
    (-1, b"ok"), (17, b"ok"), (True, b"ok"),
    (1, "not bytes"), (1, b"x" * (MAX_RESULT_BYTES + 1)),
])
def test_invalid_backend_result_not_published(vault_dir, consumed, payload):
    handle, vault = open_vault(vault_dir, Backend(payload, consumed))
    with pytest.raises(SealedResultUnavailable, match="unbounded"):
        vault.run_and_commit(permit(), state())
    assert handle.connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_sealed_results"
    ).fetchone()[0] == 0
    handle.close()


def test_duplicate_lease_never_reexecutes(vault_dir):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    vault.run_and_commit(permit(), state())
    with pytest.raises(SealedResultUnavailable, match="already"):
        vault.run_and_commit(permit(), state())
    assert backend.calls == 1
    handle.close()


def test_distinct_lease_cannot_replay_same_request_after_restart(vault_dir):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    vault.run_and_commit(permit(), state())
    handle.close()
    restarted_handle, restarted = open_vault(vault_dir, backend, create=False)
    try:
        second_lease = permit("f" * 64)
        with pytest.raises(SealedResultUnavailable, match="request already published"):
            restarted.run_and_commit(second_lease, state(second_lease))
        assert backend.calls == 1
    finally:
        restarted_handle.close()


def test_distinct_request_identity_remains_admissible(vault_dir):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    try:
        vault.run_and_commit(permit(), state())
        second = DispatchPermit("f" * 64, "request-2", 2, CHECKPOINT, 16, 4096)
        vault.run_and_commit(second, state(second))
        assert backend.calls == 2
    finally:
        handle.close()


def test_tampered_nonunique_replay_index_is_rejected(vault_dir):
    handle, vault = open_vault(vault_dir)
    handle.connection.execute(
        "DROP INDEX local_fair_stream_result_request_identity"
    )
    handle.connection.execute(
        "CREATE INDEX local_fair_stream_result_request_identity "
        "ON local_fair_stream_sealed_results (session_id, request_id)"
    )
    handle.close()
    with pytest.raises(SealedResultUnavailable, match="request replay index"):
        reopened, _ = open_vault(vault_dir, create=False)
        reopened.close()


def test_wrong_state_never_executes(vault_dir):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    invalid = state()
    invalid["checkpoint"]["pending"][0]["tokens"] = 99
    with pytest.raises(SealedResultUnavailable, match="pending"):
        vault.run_and_commit(permit(), invalid)
    invalid = state()
    invalid["generation"] = 3
    with pytest.raises(SealedResultUnavailable, match="bind"):
        vault.run_and_commit(permit(), invalid)
    assert backend.calls == 0
    handle.close()


def test_vault_rejects_cross_tenant_pending_lease_before_backend(vault_dir):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    forged = state()
    forged["checkpoint"]["pending"][0]["tenant_id"] = "tenant-b"
    with pytest.raises(SealedResultUnavailable, match="tenant or memory"):
        vault.run_and_commit(permit(), forged)
    assert backend.calls == 0
    handle.close()


def test_vault_rejects_duplicate_request_identity_before_backend(vault_dir):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    forged = state()
    forged["checkpoint"]["requests"].append(
        dict(forged["checkpoint"]["requests"][0])
    )
    with pytest.raises(SealedResultUnavailable, match="unique checkpoint"):
        vault.run_and_commit(permit(), forged)
    assert backend.calls == 0
    handle.close()


def test_vault_rejects_boolean_pending_token_count(vault_dir):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    p = DispatchPermit(LEASE, "request-1", 2, CHECKPOINT, 1, 256)
    forged = state(p)
    forged["checkpoint"]["pending"][0]["tokens"] = True
    with pytest.raises(SealedResultUnavailable, match="pending lease"):
        vault.run_and_commit(p, forged)
    assert backend.calls == 0
    handle.close()


def test_tampered_ciphertext_fails_closed(vault_dir):
    handle, vault = open_vault(vault_dir)
    _, digest = vault.run_and_commit(permit(), state())
    ciphertext = handle.connection.execute(
        "SELECT ciphertext FROM local_fair_stream_sealed_results"
    ).fetchone()[0]
    tampered = bytes([ciphertext[0] ^ 1]) + ciphertext[1:]
    handle.connection.execute(
        "UPDATE local_fair_stream_sealed_results SET ciphertext=?",
        (tampered,),
    )
    with pytest.raises(SealedResultUnavailable, match="digest"):
        vault.read_committed(permit(), expected_result_digest=digest)
    handle.close()


def test_wrong_key_fails_authenticated_read(vault_dir):
    handle, vault = open_vault(vault_dir)
    _, digest = vault.run_and_commit(permit(), state())
    handle.close()
    next_handle, wrong = open_vault(vault_dir, key=b"w" * 32, create=False)
    try:
        with pytest.raises(SealedResultUnavailable, match="authentication"):
            wrong.read_committed(permit(), expected_result_digest=digest)
    finally:
        next_handle.close()


def test_wrong_model_or_tokenizer_fails_read(vault_dir):
    handle, vault = open_vault(vault_dir)
    _, digest = vault.run_and_commit(permit(), state())
    handle.close()
    next_handle = open_private_sqlite(
        vault_dir, filename="sealed-results.db", create=False,
    )
    try:
        other = SealedFairStreamResultVault(
            next_handle, session_id=SESSION, model_digest="f" * 64,
            tokenizer_digest=TOKENIZER, result_key=RESULT_KEY,
            backend=Backend(),
        )
        with pytest.raises(SealedResultUnavailable, match="binding"):
            other.read_committed(permit(), expected_result_digest=digest)
    finally:
        next_handle.close()


def test_wrong_receipt_digest_never_releases_plaintext(vault_dir):
    handle, vault = open_vault(vault_dir)
    vault.run_and_commit(permit(), state())
    with pytest.raises(SealedResultUnavailable, match="digest"):
        vault.read_committed(permit(), expected_result_digest="f" * 64)
    handle.close()


def test_closed_handle_is_not_reused(vault_dir):
    handle, vault = open_vault(vault_dir)
    handle.close()
    with pytest.raises(SealedResultUnavailable, match="custody changed") as error:
        vault.run_and_commit(permit(), state())
    assert "closed" in str(error.value.__cause__)


def test_unauthorized_gpu_permit_rejected(vault_dir):
    handle, vault = open_vault(vault_dir)
    gpu = DispatchPermit(LEASE, "request-1", 2, CHECKPOINT, 16, 4096, True)
    with pytest.raises(ValueError, match="CPU-only"):
        vault.run_and_commit(gpu, state(gpu))
    handle.close()


def test_untrusted_existing_schema_rejected(vault_dir):
    handle = open_private_sqlite(
        vault_dir, filename="sealed-results.db", create=True,
    )
    handle.connection.execute(
        "CREATE TABLE local_fair_stream_sealed_results (lease_id TEXT)"
    )
    with pytest.raises(SealedResultUnavailable, match="schema"):
        SealedFairStreamResultVault(
            handle, session_id=SESSION, model_digest=MODEL,
            tokenizer_digest=TOKENIZER, result_key=RESULT_KEY,
            backend=Backend(),
        )
    handle.close()


def test_capacity_rejects_new_lease_without_backend_execution(vault_dir, monkeypatch):
    import skeleton.ai.model_runtime.fair_stream_result_vault as module
    monkeypatch.setattr(module, "MAX_RESULT_ROWS", 1)
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    vault.run_and_commit(permit(), state())
    second = DispatchPermit("f" * 64, "request-capacity", 2, CHECKPOINT, 16, 4096)
    with pytest.raises(SealedResultUnavailable, match="capacity"):
        vault.run_and_commit(second, state(second))
    # Known capacity exhaustion is denied before the backend executes.
    assert backend.calls == 1
    assert handle.connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_sealed_results"
    ).fetchone()[0] == 1
    handle.close()

def test_published_result_verification_returns_only_authenticated_metadata(vault_dir):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    try:
        consumed, digest = vault.run_and_commit(permit(), state())
        assert vault.verify_published_result(permit(), state()) == (consumed, digest)
        assert backend.calls == 1
        # Alter ciphertext and its unkeyed digest together. AEAD must reject.
        from hashlib import sha256
        ciphertext = handle.connection.execute(
            "SELECT ciphertext FROM local_fair_stream_sealed_results"
        ).fetchone()[0]
        tampered = bytes([ciphertext[0] ^ 1]) + ciphertext[1:]
        handle.connection.execute(
            "UPDATE local_fair_stream_sealed_results SET ciphertext=?,result_digest=?",
            (tampered, sha256(tampered).hexdigest()),
        )
        with pytest.raises(SealedResultUnavailable, match="authentication"):
            vault.verify_published_result(permit(), state())
        assert backend.calls == 1
    finally:
        handle.close()


@pytest.mark.parametrize("temporary", [False, True])
def test_late_result_trigger_denies_before_backend(vault_dir, temporary):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    try:
        trigger = "CREATE TEMP TRIGGER" if temporary else "CREATE TRIGGER"
        handle.connection.execute(
            trigger + " erase_result AFTER INSERT ON local_fair_stream_sealed_results "
            "BEGIN DELETE FROM local_fair_stream_sealed_results WHERE lease_id=NEW.lease_id; END"
        )
        # Temporary SQLite objects are denied at the lower handle boundary;
        # public error text deliberately does not reveal internal DB details.
        expected = "custody changed" if temporary else "schema"
        with pytest.raises(SealedResultUnavailable, match=expected) as error:
            vault.run_and_commit(permit(), state())
        if temporary:
            assert "temporary objects" in str(error.value.__cause__)
        assert backend.calls == 0
        assert handle.connection.execute(
            "SELECT COUNT(*) FROM main.local_fair_stream_sealed_results"
        ).fetchone()[0] == 0
    finally:
        handle.close()


def test_late_result_replay_index_replacement_denies_read_and_execution(vault_dir):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    try:
        _, digest = vault.run_and_commit(permit(), state())
        handle.connection.execute("DROP INDEX local_fair_stream_result_request_identity")
        handle.connection.execute(
            "CREATE INDEX local_fair_stream_result_request_identity "
            "ON local_fair_stream_sealed_results(session_id, request_id)"
        )
        with pytest.raises(SealedResultUnavailable, match="schema"):
            vault.read_committed(permit(), expected_result_digest=digest)
        other = DispatchPermit("f" * 64, "request-2", 3, CHECKPOINT, 16, 4096)
        with pytest.raises(SealedResultUnavailable, match="schema"):
            vault.run_and_commit(other, state(other))
        assert backend.calls == 1
    finally:
        handle.close()


def test_inherited_result_vault_refuses_before_lock(vault_dir, monkeypatch):
    handle, vault = open_vault(vault_dir)
    try:
        class ForbiddenLock:
            def __enter__(self):
                pytest.fail("inherited vault reached process-local lock")
        monkeypatch.setattr(vault, "_lock", ForbiddenLock())
        pid = os.getpid()
        with monkeypatch.context() as patch:
            patch.setattr(os, "getpid", lambda: pid + 1)
            with pytest.raises(SealedResultUnavailable, match="custody"):
                vault.run_and_commit(permit(), state())
            with pytest.raises(SealedResultUnavailable, match="custody"):
                vault.read_committed(permit(), expected_result_digest="f" * 64)
            with pytest.raises(SealedResultUnavailable, match="custody"):
                vault.assert_request_admissible("request-2")
    finally:
        handle.close()


def test_admission_reserves_worst_case_queued_capacity(vault_dir, monkeypatch):
    import skeleton.ai.model_runtime.fair_stream_result_vault as module
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    try:
        monkeypatch.setattr(module, "MAX_RESULT_ROWS", 2)
        vault.assert_request_admissible("request-1", queued_count=1)
        with pytest.raises(SealedResultUnavailable, match="capacity"):
            vault.assert_request_admissible("request-1", queued_count=2)
        assert backend.calls == 0
        _, digest = vault.run_and_commit(permit(), state())
        assert vault.read_committed(permit(), expected_result_digest=digest) == backend.payload
        with pytest.raises(SealedResultUnavailable, match="already published"):
            vault.assert_request_admissible("request-1")
    finally:
        handle.close()

def test_batch_vault_admission_has_one_aggregate_scan_and_no_writes(vault_dir, monkeypatch):
    import skeleton.ai.model_runtime.fair_stream_result_vault as module
    handle, vault = open_vault(vault_dir)
    statements = []
    handle.connection.set_trace_callback(statements.append)
    try:
        monkeypatch.setattr(module, "MAX_RESULT_ROWS", 3)
        vault.assert_requests_admissible(("a", "b", "c"))
        assert sum("SUM(LENGTH(ciphertext))" in sql for sql in statements) == 1
        with pytest.raises(SealedResultUnavailable, match="capacity"):
            vault.assert_requests_admissible(("a", "b", "c", "d"))
        for invalid in ((), ("a", "a"), ("bad\x00id",), (True,), ["a"]):
            with pytest.raises(ValueError):
                vault.assert_requests_admissible(invalid)
        assert not handle.connection.in_transaction
        assert handle.connection.execute("SELECT COUNT(*) FROM local_fair_stream_sealed_results").fetchone() == (0,)
    finally:
        handle.connection.set_trace_callback(None)
        handle.close()

@pytest.mark.parametrize("overrides", [
    {"device_qualified": 0}, {"request_id": "bad\x00identity"},
    {"request_id": "\ud800"}, {"generation": True},
])
def test_vault_refuses_noncanonical_permit_before_backend(vault_dir, overrides):
    from dataclasses import replace
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    try:
        forged = replace(permit(), **overrides)
        with pytest.raises(ValueError):
            vault.run_and_commit(forged, state(forged))
        assert backend.calls == 0
    finally:
        handle.close()


def test_recursive_publication_invalidates_outer_result(vault_dir, monkeypatch):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    second = DispatchPermit("f" * 64, "second", 3, CHECKPOINT, 16, 4096)
    calls = []

    def recursive(p, s):
        calls.append(p.lease_id)
        with pytest.raises(SealedResultUnavailable, match="recursive"):
            vault.run_and_commit(second, state(second))
        return 8, b"must not publish"

    try:
        monkeypatch.setattr(backend, "generate", recursive)
        with pytest.raises(SealedResultUnavailable, match="invalidated"):
            vault.run_and_commit(permit(), state())
        assert calls == [LEASE]
        assert handle.connection.execute("SELECT COUNT(*) FROM local_fair_stream_sealed_results").fetchone() == (0,)
    finally:
        handle.close()


def test_duplicate_encryption_nonce_rejected_across_restart(vault_dir, monkeypatch):
    import skeleton.ai.model_runtime.fair_stream_result_vault as module
    monkeypatch.setattr(module.secrets, "token_bytes", lambda length: b"n" * length)
    handle, vault = open_vault(vault_dir)
    _, digest = vault.run_and_commit(permit(), state())
    handle.close()
    handle, vault = open_vault(vault_dir, create=False)
    try:
        second = DispatchPermit("f" * 64, "second", 3, CHECKPOINT, 16, 4096)
        with pytest.raises(SealedResultUnavailable, match="nonce already used"):
            vault.run_and_commit(second, state(second))
        assert vault.read_committed(permit(), expected_result_digest=digest) == b"private offline output"
        assert handle.connection.execute("SELECT COUNT(*) FROM local_fair_stream_sealed_results").fetchone() == (1,)
        assert not handle.connection.in_transaction
    finally:
        handle.close()


def test_backend_mutated_pending_state_cannot_publish(vault_dir, monkeypatch):
    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    def changed(p, s):
        s["checkpoint"]["pending"][0]["tokens"] = 1
        return 1, b"invalid"
    try:
        monkeypatch.setattr(backend, "generate", changed)
        with pytest.raises(SealedResultUnavailable, match="pending lease"):
            vault.run_and_commit(permit(), state())
        assert handle.connection.execute("SELECT COUNT(*) FROM local_fair_stream_sealed_results").fetchone() == (0,)
    finally:
        handle.close()

def test_oversized_ciphertext_preserves_existing_replay_fence(vault_dir, monkeypatch):
    import skeleton.ai.model_runtime.fair_stream_result_vault as module

    backend = Backend()
    handle, vault = open_vault(vault_dir, backend)
    try:
        _, digest = vault.run_and_commit(permit(), state())
        handle.connection.execute(
            "UPDATE local_fair_stream_sealed_results SET ciphertext=zeroblob(8192)",
        )
        monkeypatch.setattr(module, "MAX_RESULT_BYTES", 1024)
        with pytest.raises(SealedResultUnavailable, match="digest"):
            vault.read_committed(permit(), expected_result_digest=digest)
        with pytest.raises(SealedResultUnavailable, match="digest"):
            vault.run_and_commit(permit(), state())
        assert backend.calls == 1
        assert handle.connection.execute(
            "SELECT length(ciphertext) FROM local_fair_stream_sealed_results",
        ).fetchone() == (8192,)
        assert not handle.connection.in_transaction
    finally:
        handle.close()
