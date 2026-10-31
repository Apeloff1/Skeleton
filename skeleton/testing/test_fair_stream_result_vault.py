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
        "checkpoint": {"pending": [{
            "lease_id": p.lease_id, "request_id": p.request_id,
            "tokens": p.tokens, "bytes_reserved": p.bytes_reserved,
        }]},
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
    with pytest.raises(SealedResultUnavailable, match="closed"):
        vault.run_and_commit(permit(), state())


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
    second = permit("f" * 64)
    with pytest.raises(SealedResultUnavailable, match="capacity"):
        vault.run_and_commit(second, state(second))
    # Capacity is checked after backend generation. Journal still prevents
    # automatic retry; no second ciphertext row was published.
    assert backend.calls == 2
    assert handle.connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_sealed_results"
    ).fetchone()[0] == 1
    handle.close()
