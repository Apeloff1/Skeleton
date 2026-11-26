"""One-use operator read grants over journaled encrypted offline outputs."""
from __future__ import annotations

import os
import sqlite3

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from skeleton.ai.model_runtime.fair_stream_execution_journal import (
    FairStreamExecutionJournal, JournaledExecutionOwner,
)
from skeleton.ai.model_runtime.fair_stream_result_access import (
    AuthorizedSealedResultReader, ResultReadDenied, issue_result_read_grant,
    verify_result_read_grant,
)
from skeleton.ai.model_runtime.fair_stream_result_vault import (
    SealedFairStreamResultVault, SealedResultUnavailable,
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
NONCE = "f" * 32


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
    def __init__(self):
        self.calls = 0

    def generate(self, permit, state):
        self.calls += 1
        return 8, b"secret offline generated text"


@pytest.fixture
def setup(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    os.chmod(directory, 0o700)
    result_handle = open_private_sqlite(
        str(directory), filename="result.db", create=True,
    )
    grant_handle = open_private_sqlite(
        str(directory), filename="grant.db", create=True,
    )
    backend = Backend()
    vault = SealedFairStreamResultVault(
        result_handle, session_id=SESSION, model_digest=MODEL,
        tokenizer_digest=TOKENIZER, result_key=RESULT_KEY,
        backend=backend,
    )
    journal_conn = sqlite3.connect(":memory:", isolation_level=None)
    journal = FairStreamExecutionJournal(
        journal_conn, session_id=SESSION, execution_key=EXECUTION_KEY,
    )
    owner = JournaledExecutionOwner(journal, vault)
    receipt = owner.execute_and_commit(permit(), state())
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    reader = AuthorizedSealedResultReader(
        journal=journal, vault=vault, grant_handle=grant_handle,
        operator_public_key=public,
    )
    yield {
        "reader": reader, "key": key, "receipt": receipt,
        "journal": journal, "vault": vault, "backend": backend,
        "grant_handle": grant_handle, "result_handle": result_handle,
        "directory": str(directory), "public": public,
    }
    grant_handle.close()
    result_handle.close()
    journal_conn.close()


def grant(ctx, *, nonce=NONCE, result_digest=None, lease=LEASE):
    return issue_result_read_grant(
        signing_key=ctx["key"], session_id=SESSION, generation=2,
        checkpoint_digest=CHECKPOINT, lease_id=lease,
        result_digest=result_digest or ctx["receipt"]["result_digest"],
        nonce=nonce,
    )


def test_exact_operator_grant_releases_one_verified_result(setup):
    g = grant(setup)
    result = setup["reader"].read_once(permit(), operator_grant=g)
    assert result == b"secret offline generated text"
    assert setup["backend"].calls == 1
    with pytest.raises(ResultReadDenied, match="already consumed"):
        setup["reader"].read_once(permit(), operator_grant=g)


def test_grant_is_bound_to_exact_result_digest(setup):
    g = grant(setup, result_digest="0" * 64)
    with pytest.raises(ResultReadDenied, match="bind"):
        setup["reader"].read_once(permit(), operator_grant=g)
    assert setup["grant_handle"].connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_result_read_grants"
    ).fetchone()[0] == 0


def test_grant_signature_tamper_fails_before_consumption(setup):
    g = grant(setup)
    g["signature"] = "0" * 128
    with pytest.raises(ResultReadDenied, match="signature"):
        setup["reader"].read_once(permit(), operator_grant=g)
    assert setup["grant_handle"].connection.execute(
        "SELECT COUNT(*) FROM local_fair_stream_result_read_grants"
    ).fetchone()[0] == 0


def test_wrong_operator_key_cannot_authorize(setup):
    other = Ed25519PrivateKey.generate()
    g = issue_result_read_grant(
        signing_key=other, session_id=SESSION, generation=2,
        checkpoint_digest=CHECKPOINT, lease_id=LEASE,
        result_digest=setup["receipt"]["result_digest"], nonce=NONCE,
    )
    with pytest.raises(ResultReadDenied, match="signature"):
        setup["reader"].read_once(permit(), operator_grant=g)


def test_missing_or_uncommitted_journal_cannot_authorize(setup):
    unknown = permit("1" * 64)
    g = grant(setup, lease=unknown.lease_id)
    with pytest.raises(ResultReadDenied, match="journal"):
        setup["reader"].read_once(unknown, operator_grant=g)


def test_read_grant_survives_restart_as_consumed(setup):
    g = grant(setup)
    setup["reader"].read_once(permit(), operator_grant=g)
    handle = setup["grant_handle"]
    handle.close()
    next_handle = open_private_sqlite(
        setup["directory"], filename="grant.db", create=False,
    )
    try:
        restarted = AuthorizedSealedResultReader(
            journal=setup["journal"], vault=setup["vault"],
            grant_handle=next_handle, operator_public_key=setup["public"],
        )
        with pytest.raises(ResultReadDenied, match="already consumed"):
            restarted.read_once(permit(), operator_grant=g)
    finally:
        next_handle.close()


def test_bad_ciphertext_burns_valid_grant(setup):
    g = grant(setup)
    setup["result_handle"].connection.execute(
        "UPDATE local_fair_stream_sealed_results SET ciphertext=?",
        (b"bad ciphertext",),
    )
    with pytest.raises(SealedResultUnavailable):
        setup["reader"].read_once(permit(), operator_grant=g)
    with pytest.raises(ResultReadDenied, match="already consumed"):
        setup["reader"].read_once(permit(), operator_grant=g)


def test_wrong_nonce_reuse_for_second_grant_is_denied(setup):
    first = grant(setup)
    setup["reader"].read_once(permit(), operator_grant=first)
    duplicate = grant(setup)
    with pytest.raises(ResultReadDenied, match="already consumed"):
        setup["reader"].read_once(permit(), operator_grant=duplicate)


def test_invalid_grant_shape_rejected(setup):
    g = grant(setup)
    g["unexpected"] = "ignored"
    with pytest.raises(ResultReadDenied, match="fields"):
        setup["reader"].read_once(permit(), operator_grant=g)


def test_boolean_generation_and_malformed_nonce_rejected(setup):
    with pytest.raises(ResultReadDenied, match="generation"):
        issue_result_read_grant(
            signing_key=setup["key"], session_id=SESSION, generation=True,
            checkpoint_digest=CHECKPOINT, lease_id=LEASE,
            result_digest=setup["receipt"]["result_digest"], nonce=NONCE,
        )
    with pytest.raises(ResultReadDenied, match="nonce"):
        grant(setup, nonce="not-hex")


def test_closed_grant_ledger_denies_read(setup):
    setup["grant_handle"].close()
    with pytest.raises(ResultReadDenied, match="unavailable"):
        setup["reader"].read_once(permit(), operator_grant=grant(setup))


def test_consumed_grant_capacity_is_bounded(setup, monkeypatch):
    import skeleton.ai.model_runtime.fair_stream_result_access as module
    monkeypatch.setattr(module, "MAX_USED_GRANTS", 0)
    with pytest.raises(ResultReadDenied, match="capacity"):
        setup["reader"].read_once(permit(), operator_grant=grant(setup))


def test_wrong_session_cannot_construct_reader(setup):
    different = FairStreamExecutionJournal(
        sqlite3.connect(":memory:", isolation_level=None),
        session_id="9" * 32, execution_key=EXECUTION_KEY,
    )
    with pytest.raises(ValueError, match="session"):
        AuthorizedSealedResultReader(
            journal=different, vault=setup["vault"],
            grant_handle=setup["grant_handle"],
            operator_public_key=setup["public"],
        )


def test_invalid_grant_ledger_schema_rejected(setup):
    handle = open_private_sqlite(
        setup["directory"], filename="other-grants.db", create=True,
    )
    try:
        handle.connection.execute(
            "CREATE TABLE local_fair_stream_result_read_grants (nonce TEXT)"
        )
        with pytest.raises(ResultReadDenied, match="schema"):
            AuthorizedSealedResultReader(
                journal=setup["journal"], vault=setup["vault"],
                grant_handle=handle, operator_public_key=setup["public"],
            )
    finally:
        handle.close()

def test_same_result_handle_cannot_serve_as_grant_ledger(setup):
    with pytest.raises(ValueError, match="independent"):
        AuthorizedSealedResultReader(
            journal=setup["journal"], vault=setup["vault"],
            grant_handle=setup["result_handle"],
            operator_public_key=setup["public"],
        )


def test_distinct_handle_to_same_result_inode_rejected(setup):
    second = open_private_sqlite(
        setup["directory"], filename="result.db", create=False,
    )
    try:
        with pytest.raises(ValueError, match="distinct database inode"):
            AuthorizedSealedResultReader(
                journal=setup["journal"], vault=setup["vault"],
                grant_handle=second, operator_public_key=setup["public"],
            )
    finally:
        second.close()
