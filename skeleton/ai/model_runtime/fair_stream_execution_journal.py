"""Durable execution-intent journal for the canonical offline fair-stream owner.

The SQLite journal is a separate, caller-owned connection. A RUNNING lease is
never automatically retried, including after a process crash. Backend results
must already be durable before a signed completion receipt is persisted.
This module stores no prompts, token bytes, model weights or key material.
"""
from __future__ import annotations

import hmac
import json
import sqlite3
from threading import RLock
from typing import Mapping, Protocol

from .fair_stream_custody import sign_execution_result
from .fair_stream_session import DispatchPermit

SCHEMA = "skeleton.ai.fair-stream-execution-journal.v1"
MAX_JOURNAL_ROWS = 10_000
MAX_RECEIPT_BYTES = 2048
_REQUEST_INDEX = "local_fair_stream_execution_request_identity"


class ExecutionOutcomeUnknown(RuntimeError):
    """A lease may have executed; automatic retry is forbidden."""


class DurableResultBackend(Protocol):
    """App-owned backend that commits result BEFORE returning its digest."""

    def run_and_commit(
        self, permit: DispatchPermit, state: Mapping[str, object],
    ) -> tuple[int, str]: ...


def _hex(value: object, length: int, name: str) -> str:
    if type(value) is not str or len(value) != length or any(
        ch not in "0123456789abcdef" for ch in value
    ):
        raise ValueError("invalid " + name)
    return value


def _receipt_bytes(receipt: Mapping[str, object]) -> bytes:
    payload = json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ensure_ascii=True,
    ).encode("ascii")
    if len(payload) > MAX_RECEIPT_BYTES:
        raise ValueError("execution receipt exceeds byte budget")
    return payload


class FairStreamExecutionJournal:
    """One-use, fail-closed RUNNING -> COMMITTED lease intent.

    A journal database alone is not an independent anti-rollback anchor.
    The canonical custody session still requires its external high-watermark.
    The caller supplies a separate, secure SQLite connection and owns its
    lifecycle. No connection may be shared with another transaction owner.
    """

    def __init__(
        self, connection: sqlite3.Connection, *,
        session_id: str, execution_key: bytes,
    ) -> None:
        if not isinstance(connection, sqlite3.Connection) or connection.in_transaction:
            raise ValueError("exclusive idle SQLite journal connection required")
        self.session_id = _hex(session_id, 32, "session ID")
        if type(execution_key) is not bytes or not 32 <= len(execution_key) <= 128:
            raise ValueError("independent execution key required")
        self._connection = connection
        self._key = execution_key
        self._lock = RLock()
        connection.execute(
            "CREATE TABLE IF NOT EXISTS local_fair_stream_execution_journal ("
            "lease_id TEXT PRIMARY KEY NOT NULL,"
            "session_id TEXT NOT NULL,"
            "generation INTEGER NOT NULL CHECK(generation >= 0),"
            "checkpoint_digest TEXT NOT NULL,"
            "request_id TEXT NOT NULL,"
            "state TEXT NOT NULL CHECK(state IN ('running','committed')),"
            "consumed_tokens INTEGER,"
            "result_digest TEXT,"
            "receipt BLOB"
            ") WITHOUT ROWID"
        )
        expected = (
            "lease_id", "session_id", "generation", "checkpoint_digest",
            "request_id", "state", "consumed_tokens", "result_digest", "receipt",
        )
        actual = tuple(row[1] for row in connection.execute(
            "PRAGMA table_info(local_fair_stream_execution_journal)"
        ))
        if actual != expected:
            raise ValueError("untrusted execution journal schema")
        # RUNNING is already outcome-uncertain. A new lease identifier must
        # never allow the same request to execute again after a crash.
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS " + _REQUEST_INDEX
            + " ON local_fair_stream_execution_journal"
            + " (session_id, request_id)"
        )
        matches = [
            row for row in connection.execute(
                "PRAGMA index_list(local_fair_stream_execution_journal)"
            ) if row[1] == _REQUEST_INDEX
        ]
        if (
            len(matches) != 1 or matches[0][2] != 1
            or matches[0][4] != 0
            or tuple(row[2] for row in connection.execute(
                "PRAGMA index_info(" + _REQUEST_INDEX + ")"
            )) != ("session_id", "request_id")
        ):
            raise ValueError("untrusted journal request replay index")

    def _begin(self) -> None:
        if self._connection.in_transaction:
            raise ExecutionOutcomeUnknown("journal connection has active transaction")
        self._connection.execute("BEGIN IMMEDIATE")

    def _row(self, lease_id: str) -> tuple[object, ...] | None:
        return self._connection.execute(
            "SELECT session_id, generation, checkpoint_digest, request_id,"
            " state, consumed_tokens, result_digest, receipt"
            " FROM local_fair_stream_execution_journal WHERE lease_id = ?",
            (lease_id,),
        ).fetchone()

    def begin(self, permit: DispatchPermit) -> None:
        """Persist intent before any backend call; reject ALL prior lease IDs."""
        if type(permit) is not DispatchPermit or permit.device_qualified:
            raise ValueError("canonical CPU-only dispatch permit required")
        _hex(permit.lease_id, 64, "lease ID")
        _hex(permit.checkpoint_digest, 64, "checkpoint digest")
        if type(permit.generation) is not int or not 0 <= permit.generation < (1 << 63):
            raise ValueError("invalid dispatch generation")
        if type(permit.request_id) is not str or not permit.request_id:
            raise ValueError("bounded request identity required")
        if len(permit.request_id.encode("utf-8")) > 128:
            raise ValueError("bounded request identity required")
        with self._lock:
            self._begin()
            try:
                if self._row(permit.lease_id) is not None:
                    raise ExecutionOutcomeUnknown("lease already executed or reserved")
                if self._connection.execute(
                    "SELECT 1 FROM local_fair_stream_execution_journal"
                    " WHERE session_id=? AND request_id=? LIMIT 1",
                    (self.session_id, permit.request_id),
                ).fetchone() is not None:
                    raise ExecutionOutcomeUnknown("request already executed or reserved")
                count = self._connection.execute(
                    "SELECT COUNT(*) FROM local_fair_stream_execution_journal"
                ).fetchone()[0]
                if count >= MAX_JOURNAL_ROWS:
                    raise ExecutionOutcomeUnknown("execution journal capacity exhausted")
                self._connection.execute(
                    "INSERT INTO local_fair_stream_execution_journal"
                    " (lease_id, session_id, generation, checkpoint_digest,"
                    " request_id, state) VALUES (?, ?, ?, ?, ?, 'running')",
                    (permit.lease_id, self.session_id, permit.generation,
                     permit.checkpoint_digest, permit.request_id),
                )
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise

    def commit(
        self, permit: DispatchPermit, *,
        consumed_tokens: int, result_digest: str,
    ) -> dict[str, object]:
        """Commit signed receipt only after backend durable result publication."""
        if type(permit) is not DispatchPermit:
            raise ValueError("canonical permit required")
        if (
            type(consumed_tokens) is not int
            or not 0 <= consumed_tokens <= permit.tokens
        ):
            raise ValueError("invalid consumed token count")
        _hex(result_digest, 64, "result digest")
        receipt = sign_execution_result(
            execution_key=self._key, session_id=self.session_id,
            generation=permit.generation,
            checkpoint_digest=permit.checkpoint_digest,
            lease_id=permit.lease_id, consumed_tokens=consumed_tokens,
            result_digest=result_digest,
        )
        payload = _receipt_bytes(receipt)
        with self._lock:
            self._begin()
            try:
                row = self._row(permit.lease_id)
                if (
                    row is None
                    or row[:5] != (
                        self.session_id, permit.generation,
                        permit.checkpoint_digest, permit.request_id, "running",
                    )
                    or row[5:] != (None, None, None)
                ):
                    raise ExecutionOutcomeUnknown("journal intent missing or stale")
                changed = self._connection.execute(
                    "UPDATE local_fair_stream_execution_journal"
                    " SET state = 'committed', consumed_tokens = ?,"
                    " result_digest = ?, receipt = ?"
                    " WHERE lease_id = ? AND state = 'running'",
                    (consumed_tokens, result_digest, payload, permit.lease_id),
                ).rowcount
                if changed != 1:
                    raise ExecutionOutcomeUnknown("journal completion CAS failed")
                self._connection.commit()
                return receipt
            except BaseException:
                self._connection.rollback()
                raise

    def recover_committed_receipt(
        self, permit: DispatchPermit,
    ) -> dict[str, object]:
        """Read signed committed receipt for explicit external reconciliation.

        This never dispatches the backend. The operator must separately verify
        canonical custody generation and the independent external anchor.
        """
        if type(permit) is not DispatchPermit:
            raise ValueError("canonical permit required")
        with self._lock:
            row = self._row(permit.lease_id)
            if (
                row is None or row[:5] != (
                    self.session_id, permit.generation,
                    permit.checkpoint_digest, permit.request_id, "committed",
                )
            ):
                raise ExecutionOutcomeUnknown("no committed receipt to reconcile")
            consumed, result_digest, payload = row[5:]
            if (
                type(consumed) is not int
                or not 0 <= consumed <= permit.tokens
                or type(payload) is not bytes
                or len(payload) > MAX_RECEIPT_BYTES
            ):
                raise ExecutionOutcomeUnknown("invalid stored execution receipt")
            _hex(result_digest, 64, "result digest")
            expected = sign_execution_result(
                execution_key=self._key, session_id=self.session_id,
                generation=permit.generation,
                checkpoint_digest=permit.checkpoint_digest,
                lease_id=permit.lease_id, consumed_tokens=consumed,
                result_digest=result_digest,
            )
            if not hmac.compare_digest(_receipt_bytes(expected), payload):
                raise ExecutionOutcomeUnknown("stored execution receipt authentication failed")
            return expected


class JournaledExecutionOwner:
    """Bridge trusted durable backend to canonical signed-receipt protocol."""

    def __init__(
        self, journal: FairStreamExecutionJournal,
        backend: DurableResultBackend,
    ) -> None:
        if not isinstance(journal, FairStreamExecutionJournal):
            raise ValueError("canonical execution journal required")
        if not callable(getattr(backend, "run_and_commit", None)):
            raise ValueError("trusted durable result backend required")
        self._journal = journal
        self._backend = backend
        self._lock = RLock()

    def execute_and_commit(
        self, permit: DispatchPermit, state: Mapping[str, object],
    ) -> Mapping[str, object]:
        if not isinstance(state, Mapping) or type(permit) is not DispatchPermit:
            raise ValueError("canonical pending lease state required")
        if (
            state.get("generation") != permit.generation
            or state.get("checkpoint_digest") != permit.checkpoint_digest
            or state.get("session_id") != self._journal.session_id
        ):
            raise ExecutionOutcomeUnknown("execution state does not bind permit")
        checkpoint = state.get("checkpoint")
        if not isinstance(checkpoint, Mapping):
            raise ExecutionOutcomeUnknown("pending checkpoint required")
        pending = checkpoint.get("pending")
        if (
            type(pending) is not list or len(pending) != 1
            or not isinstance(pending[0], Mapping)
            or pending[0].get("lease_id") != permit.lease_id
            or pending[0].get("request_id") != permit.request_id
            or pending[0].get("tokens") != permit.tokens
            or pending[0].get("bytes_reserved") != permit.bytes_reserved
        ):
            raise ExecutionOutcomeUnknown("pending lease differs from execution permit")
        with self._lock:
            self._journal.begin(permit)
            # Any backend error leaves RUNNING intent durable. No automatic
            # retry, even if the backend committed before its response failed.
            consumed, digest = self._backend.run_and_commit(permit, state)
            return self._journal.commit(
                permit, consumed_tokens=consumed, result_digest=digest,
            )
