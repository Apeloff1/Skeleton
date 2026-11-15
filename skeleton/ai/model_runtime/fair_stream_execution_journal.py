"""Durable execution-intent journal for the canonical offline fair-stream owner.

The SQLite journal is a separate, caller-owned connection. A RUNNING lease is
never automatically retried, including after a process crash. Backend results
must already be durable before a signed completion receipt is persisted.
This module stores no prompts, token bytes, model weights or key material.
"""
from __future__ import annotations

import hmac
import json
import os
import sqlite3
from contextlib import contextmanager
from threading import RLock
from typing import Mapping, Protocol

from .fair_stream_custody import sign_abandonment, sign_execution_result, sign_unstarted_cancellation
from .fair_stream_admission import validate_admission_batch, validate_request_identity
from .fair_stream_session import DispatchPermit
from .private_sqlite import PrivateSQLiteHandle
from .sqlite_custody_schema import assert_custody_schema

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


def _validate_permit(permit: DispatchPermit) -> None:
    """Canonical CPU-only typed identity; reject Python bool/int aliases."""
    if type(permit) is not DispatchPermit or permit.device_qualified is not False:
        raise ValueError("canonical CPU-only dispatch permit required")
    _hex(permit.lease_id, 64, "lease ID")
    _hex(permit.checkpoint_digest, 64, "checkpoint digest")
    if type(permit.generation) is not int or not 0 <= permit.generation < (1 << 63):
        raise ValueError("invalid dispatch generation")
    if (type(permit.request_id) is not str or not permit.request_id
            or any(ord(char) < 32 or ord(char) == 127 for char in permit.request_id)):
        raise ValueError("bounded request identity required")
    try:
        size = len(permit.request_id.encode("utf-8", errors="strict"))
    except UnicodeEncodeError as exc:
        raise ValueError("bounded request identity required") from exc
    if not 1 <= size <= 128:
        raise ValueError("bounded request identity required")
    if (type(permit.tokens) is not int or not 1 <= permit.tokens <= (1 << 24)
            or type(permit.bytes_reserved) is not int
            or not 1 <= permit.bytes_reserved < (1 << 63)):
        raise ValueError("invalid execution permit resource envelope")


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
        self._owner_pid = os.getpid()
        self._private_handle: PrivateSQLiteHandle | None = None
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
        connection.execute(
            "CREATE TABLE IF NOT EXISTS local_fair_stream_cancelled_intents ("
            "session_id TEXT NOT NULL, request_id TEXT NOT NULL,"
            "lease_id TEXT NOT NULL UNIQUE, receipt BLOB NOT NULL,"
            "PRIMARY KEY(session_id,request_id)) WITHOUT ROWID"
        )
        columns = tuple(row[1] for row in connection.execute(
            "PRAGMA table_info(local_fair_stream_cancelled_intents)"
        ))
        if columns != ("session_id", "request_id", "lease_id", "receipt"):
            raise ValueError("untrusted cancellation ledger schema")
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND "
            "tbl_name IN ('local_fair_stream_cancelled_intents','local_fair_stream_execution_journal') LIMIT 1"
        ).fetchone() is not None:
            raise ValueError("untrusted execution custody trigger")

        self._assert_schema()

    def _assert_schema(self) -> None:
        assert_custody_schema(
            self._connection, table="local_fair_stream_execution_journal",
            columns=("lease_id", "session_id", "generation", "checkpoint_digest",
                     "request_id", "state", "consumed_tokens", "result_digest", "receipt"),
            primary_key="lease_id", replay_index=_REQUEST_INDEX,
            replay_columns=("session_id", "request_id"),
        )
        assert_custody_schema(
            self._connection, table="local_fair_stream_cancelled_intents",
            columns=("session_id", "request_id", "lease_id", "receipt"),
            primary_key=("session_id", "request_id"), unique_keys=(("lease_id",),),
        )

    def _require_owner_process(self) -> None:
        if self._owner_pid != os.getpid():
            raise ExecutionOutcomeUnknown("inherited journal requires reopening")

    @contextmanager
    def _read_snapshot(self):
        self._require_owner_process()
        with self._lock:
            self._assert_private()
            if self._connection.in_transaction:
                raise ExecutionOutcomeUnknown("journal connection has active transaction")
            self._connection.execute("BEGIN")
            try:
                self._assert_schema()
                yield
                self._assert_private()
            finally:
                self._connection.rollback()

    def bind_private_handle(self, handle: PrivateSQLiteHandle) -> None:
        """Bind the exact owned journal inode for all later read/write operations."""
        self._require_owner_process()
        with self._lock:
            if (type(handle) is not PrivateSQLiteHandle
                    or handle.connection is not self._connection
                    or self._private_handle is not None):
                raise ValueError("journal private handle missing, mismatched or rebound")
            handle.assert_current()
            self._private_handle = handle

    def _assert_private(self) -> None:
        self._require_owner_process()
        if self._private_handle is not None:
            self._private_handle.assert_current()
        self._assert_schema()

    def _begin(self) -> None:
        self._assert_private()
        if self._connection.in_transaction:
            raise ExecutionOutcomeUnknown("journal connection has active transaction")
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._assert_schema()
        except BaseException:
            self._connection.rollback()
            raise

    def _row(self, lease_id: str) -> tuple[object, ...] | None:
        self._assert_private()
        row = self._connection.execute(
            "SELECT session_id, generation, checkpoint_digest, request_id,"
            " state, consumed_tokens, result_digest,"
            " CASE WHEN receipt IS NULL THEN NULL"
            " WHEN typeof(receipt)='blob' AND length(receipt)<=? THEN receipt"
            " ELSE X'FF' END"
            " FROM local_fair_stream_execution_journal WHERE lease_id = ?",
            (MAX_RECEIPT_BYTES, lease_id),
        ).fetchone()
        if row is not None and row[-1] == b"\xff":
            raise ExecutionOutcomeUnknown("invalid stored execution receipt")
        return row

    def request_exists(self, request_id: str) -> bool:
        """Observation only; begin() remains the atomic replay fence."""
        validate_request_identity(request_id)
        with self._read_snapshot():
            return self._request_fenced(request_id)

    def assert_request_admissible(self, request_id: str, *, queued_count: int = 0) -> None:
        """Observe capacity across both execution and cancellation fences."""
        self.assert_requests_admissible((request_id,), additional_queued=queued_count)

    def assert_requests_admissible(
        self, request_ids: tuple[str, ...], *, additional_queued: int = 0,
    ) -> None:
        """Verify the complete queued inventory in one read-only snapshot."""
        identities = validate_admission_batch(
            request_ids, additional_queued=additional_queued, maximum=MAX_JOURNAL_ROWS,
        )
        with self._read_snapshot():
            for request_id in identities:
                if self._request_fenced(request_id):
                    raise ExecutionOutcomeUnknown("request already executed, reserved or cancelled")
            # _capacity reserves one implicit incoming slot.
            self._capacity(queued_count=len(identities) + additional_queued - 1)

    def _request_fenced(self, request_id: str) -> bool:
        return self._connection.execute(
            "SELECT 1 FROM local_fair_stream_execution_journal"
            " WHERE session_id=? AND request_id=? UNION ALL "
            "SELECT 1 FROM local_fair_stream_cancelled_intents "
            "WHERE session_id=? AND request_id=? LIMIT 1",
            (self.session_id, request_id, self.session_id, request_id),
        ).fetchone() is not None

    def _capacity(self, *, queued_count: int = 0) -> None:
        count = self._connection.execute(
            "SELECT (SELECT COUNT(*) FROM local_fair_stream_execution_journal) + "
            "(SELECT COUNT(*) FROM local_fair_stream_cancelled_intents)"
        ).fetchone()[0]
        if count + queued_count >= MAX_JOURNAL_ROWS:
            raise ExecutionOutcomeUnknown("execution journal capacity exhausted")

    def fence_unstarted(self, permit: DispatchPermit) -> dict[str, object]:
        """Permanently deny begin() for an exact unstarted lease and request.

        The trusted dispatcher must prove it still owns an unstarted permit.
        A competing begin() wins or loses the same SQLite write transaction.
        This produces no execution result and cannot retire RUNNING intent.
        """
        _validate_permit(permit)
        receipt = sign_unstarted_cancellation(
            execution_key=self._key, session_id=self.session_id,
            generation=permit.generation, checkpoint_digest=permit.checkpoint_digest,
            lease_id=permit.lease_id, request_id=permit.request_id,
        )
        self._require_owner_process()
        with self._lock:
            self._begin()
            try:
                if (self._row(permit.lease_id) is not None
                        or self._request_fenced(permit.request_id)
                        or self._connection.execute(
                            "SELECT 1 FROM local_fair_stream_cancelled_intents WHERE lease_id=? LIMIT 1",
                            (permit.lease_id,),
                        ).fetchone() is not None):
                    raise ExecutionOutcomeUnknown("request already executed, reserved or cancelled")
                self._capacity()
                self._connection.execute(
                    "INSERT INTO local_fair_stream_cancelled_intents "
                    "(session_id,request_id,lease_id,receipt) VALUES (?,?,?,?)",
                    (self.session_id, permit.request_id, permit.lease_id, _receipt_bytes(receipt)),
                )
                self._assert_private()
                row = self._connection.execute(
                    "SELECT lease_id, receipt FROM local_fair_stream_cancelled_intents "
                    "WHERE session_id=? AND request_id=?",
                    (self.session_id, permit.request_id),
                ).fetchone()
                if row != (permit.lease_id, _receipt_bytes(receipt)):
                    raise ExecutionOutcomeUnknown("cancellation fence readback mismatch")
                self._connection.commit()
                return receipt
            except BaseException:
                self._connection.rollback()
                raise

    def recover_cancelled_receipt(self, permit: DispatchPermit) -> dict[str, object]:
        """Read an existing exact cancellation fence, never create one on recovery."""
        _validate_permit(permit)
        expected = sign_unstarted_cancellation(
            execution_key=self._key, session_id=self.session_id,
            generation=permit.generation, checkpoint_digest=permit.checkpoint_digest,
            lease_id=permit.lease_id, request_id=permit.request_id,
        )
        self._require_owner_process()
        with self._lock:
            self._begin()
            try:
                row = self._connection.execute(
                    "SELECT lease_id, CASE WHEN typeof(receipt)='blob' AND length(receipt)<=?"
                    " THEN receipt END FROM local_fair_stream_cancelled_intents "
                    "WHERE session_id=? AND request_id=?",
                    (MAX_RECEIPT_BYTES, self.session_id, permit.request_id),
                ).fetchone()
                if row is None or row[0] != permit.lease_id:
                    raise ExecutionOutcomeUnknown("no exact cancellation receipt to reconcile")
                if (type(row[1]) is not bytes or len(row[1]) > MAX_RECEIPT_BYTES
                        or not hmac.compare_digest(row[1], _receipt_bytes(expected))):
                    raise ExecutionOutcomeUnknown("stored cancellation authentication failed")
                if self._connection.execute(
                    "SELECT 1 FROM local_fair_stream_execution_journal "
                    "WHERE lease_id=? OR (session_id=? AND request_id=?) LIMIT 1",
                    (permit.lease_id, self.session_id, permit.request_id),
                ).fetchone() is not None:
                    raise ExecutionOutcomeUnknown("conflicting execution and cancellation custody")
                self._assert_private()
                self._connection.commit()
                return expected
            except BaseException:
                self._connection.rollback()
                raise

    def begin(self, permit: DispatchPermit) -> None:
        """Persist intent before any backend call; reject ALL prior lease IDs."""
        _validate_permit(permit)
        self._require_owner_process()
        with self._lock:
            self._begin()
            try:
                if self._row(permit.lease_id) is not None:
                    raise ExecutionOutcomeUnknown("lease already executed or reserved")
                if self._request_fenced(permit.request_id) or self._connection.execute(
                    "SELECT 1 FROM local_fair_stream_cancelled_intents WHERE lease_id=? LIMIT 1",
                    (permit.lease_id,),
                ).fetchone() is not None:
                    raise ExecutionOutcomeUnknown("request already executed, reserved or cancelled")
                self._capacity()
                self._connection.execute(
                    "INSERT INTO local_fair_stream_execution_journal"
                    " (lease_id, session_id, generation, checkpoint_digest,"
                    " request_id, state) VALUES (?, ?, ?, ?, ?, 'running')",
                    (permit.lease_id, self.session_id, permit.generation,
                     permit.checkpoint_digest, permit.request_id),
                )
                if self._row(permit.lease_id) != (
                    self.session_id, permit.generation, permit.checkpoint_digest,
                    permit.request_id, "running", None, None, None,
                ):
                    raise ExecutionOutcomeUnknown("execution intent readback mismatch")
                self._assert_private()
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise

    def commit(
        self, permit: DispatchPermit, *,
        consumed_tokens: int, result_digest: str,
    ) -> dict[str, object]:
        """Commit signed receipt only after backend durable result publication."""
        _validate_permit(permit)
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
        self._require_owner_process()
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
                if self._connection.execute(
                    "SELECT 1 FROM local_fair_stream_cancelled_intents "
                    "WHERE lease_id=? OR (session_id=? AND request_id=?) LIMIT 1",
                    (permit.lease_id, self.session_id, permit.request_id),
                ).fetchone() is not None:
                    raise ExecutionOutcomeUnknown("conflicting cancellation custody")
                changed = self._connection.execute(
                    "UPDATE local_fair_stream_execution_journal"
                    " SET state = 'committed', consumed_tokens = ?,"
                    " result_digest = ?, receipt = ?"
                    " WHERE lease_id = ? AND state = 'running'",
                    (consumed_tokens, result_digest, payload, permit.lease_id),
                ).rowcount
                if changed != 1:
                    raise ExecutionOutcomeUnknown("journal completion CAS failed")
                if self._row(permit.lease_id) != (
                    self.session_id, permit.generation, permit.checkpoint_digest,
                    permit.request_id, "committed", consumed_tokens, result_digest, payload,
                ):
                    raise ExecutionOutcomeUnknown("execution completion readback mismatch")
                self._assert_private()
                self._connection.commit()
                return receipt
            except BaseException:
                self._connection.rollback()
                raise

    def record_abandonment(self, permit: DispatchPermit, *, evidence_digest: str) -> dict[str, object]:
        """Permanently fence a drained uncertain request, without result credit.

        The caller must independently establish quiescence and absence of
        published output. A RUNNING row with a retirement receipt cannot be
        committed or retried. Repeating the exact approval is idempotent.
        """
        _validate_permit(permit)
        receipt = sign_abandonment(
            execution_key=self._key, session_id=self.session_id,
            generation=permit.generation, checkpoint_digest=permit.checkpoint_digest,
            lease_id=permit.lease_id, evidence_digest=evidence_digest,
        )
        payload = _receipt_bytes(receipt)
        identity = (self.session_id, permit.generation, permit.checkpoint_digest, permit.request_id)
        self._require_owner_process()
        with self._lock:
            self._begin()
            try:
                if self._connection.execute(
                    "SELECT 1 FROM local_fair_stream_cancelled_intents "
                    "WHERE lease_id=? OR (session_id=? AND request_id=?) LIMIT 1",
                    (permit.lease_id, self.session_id, permit.request_id),
                ).fetchone() is not None:
                    raise ExecutionOutcomeUnknown("existing cancellation requires its own recovery")
                row = self._row(permit.lease_id)
                if row is None:
                    if self._request_fenced(permit.request_id):
                        raise ExecutionOutcomeUnknown("existing request fence")
                    self._capacity()
                    self._connection.execute(
                        "INSERT INTO local_fair_stream_execution_journal "
                        "(lease_id, session_id, generation, checkpoint_digest, request_id, state, receipt) "
                        "VALUES (?, ?, ?, ?, ?, 'running', ?)",
                        (permit.lease_id, *identity, payload),
                    )
                elif row == (*identity, "running", None, None, None):
                    changed = self._connection.execute(
                        "UPDATE local_fair_stream_execution_journal SET receipt=? "
                        "WHERE lease_id=? AND state='running' AND receipt IS NULL",
                        (payload, permit.lease_id),
                    ).rowcount
                    if changed != 1:
                        raise ExecutionOutcomeUnknown("abandonment CAS rejected")
                elif row != (*identity, "running", None, None, payload):
                    raise ExecutionOutcomeUnknown("existing journal completion or incompatible abandonment")
                if self._row(permit.lease_id) != (*identity, "running", None, None, payload):
                    raise ExecutionOutcomeUnknown("abandonment readback mismatch")
                self._assert_private()
                self._connection.commit()
                return receipt
            except BaseException:
                self._connection.rollback()
                raise

    def require_running_intent(self, permit: DispatchPermit) -> None:
        """Check an exact RUNNING row before authenticating a sealed result.

        commit() repeats the intent comparison inside its write transaction.
        A missing or cancelled intent is never inferred from ciphertext.
        """
        _validate_permit(permit)
        with self._read_snapshot():
            row = self._row(permit.lease_id)
            if (row is None or row[:5] != (
                self.session_id, permit.generation, permit.checkpoint_digest,
                permit.request_id, "running",
            ) or row[5:] != (None, None, None)):
                raise ExecutionOutcomeUnknown("exact running intent unavailable")
            if self._connection.execute(
                "SELECT 1 FROM local_fair_stream_cancelled_intents "
                "WHERE lease_id=? OR (session_id=? AND request_id=?) LIMIT 1",
                (permit.lease_id, self.session_id, permit.request_id),
            ).fetchone() is not None:
                raise ExecutionOutcomeUnknown("conflicting cancellation custody")

    def recover_committed_receipt(
        self, permit: DispatchPermit,
    ) -> dict[str, object]:
        """Read signed committed receipt for explicit external reconciliation.

        This never dispatches the backend. The operator must separately verify
        canonical custody generation and the independent external anchor.
        """
        _validate_permit(permit)
        with self._read_snapshot():
            row = self._row(permit.lease_id)
            if (
                row is None or row[:5] != (
                    self.session_id, permit.generation,
                    permit.checkpoint_digest, permit.request_id, "committed",
                )
            ):
                raise ExecutionOutcomeUnknown("no committed receipt to reconcile")
            if self._connection.execute(
                "SELECT 1 FROM local_fair_stream_cancelled_intents "
                "WHERE lease_id=? OR (session_id=? AND request_id=?) LIMIT 1",
                (permit.lease_id, self.session_id, permit.request_id),
            ).fetchone() is not None:
                raise ExecutionOutcomeUnknown("conflicting cancellation custody")
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
        self._active = False
        self._invalidated = False

    def execute_and_commit(
        self, permit: DispatchPermit, state: Mapping[str, object],
    ) -> Mapping[str, object]:
        _validate_permit(permit)
        if not isinstance(state, Mapping):
            raise ValueError("canonical pending lease state required")
        if (
            type(state.get("generation")) is not int
            or state.get("generation") != permit.generation
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
            or type(pending[0].get("tokens")) is not int
            or pending[0].get("tokens") != permit.tokens
            or type(pending[0].get("bytes_reserved")) is not int
            or pending[0].get("bytes_reserved") != permit.bytes_reserved
        ):
            raise ExecutionOutcomeUnknown("pending lease differs from execution permit")
        self._journal._require_owner_process()
        with self._lock:
            if self._active:
                self._invalidated = True
                raise ExecutionOutcomeUnknown("recursive execution owner invocation denied")
            self._active = True
            self._invalidated = False
            try:
                self._journal.begin(permit)
                # Any backend error leaves RUNNING intent durable. No automatic
                # retry, even if the backend committed before its response failed.
                consumed, digest = self._backend.run_and_commit(permit, state)
                if self._invalidated:
                    raise ExecutionOutcomeUnknown("recursive execution invalidated owner")
                return self._journal.commit(
                    permit, consumed_tokens=consumed, result_digest=digest,
                )
            finally:
                self._active = False
