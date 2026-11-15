"""Transactional SQLite custody for canonical offline fair-stream execution.

The caller owns a securely opened SQLite connection and a separate trusted
high-watermark. SQLite is a transactional state store, NOT an anti-rollback
anchor, key vault, model executor, or proof of hardware qualification.
"""
from __future__ import annotations

import hmac
import json
import os
import sqlite3
from threading import RLock
from typing import Mapping

from .fair_stream_custody import (
    AuthenticatedFairStreamCustody, MAX_BYTES,
)

from .fair_stream_queue import FairStreamScheduler
from .private_sqlite import PrivateSQLiteHandle, PrivateSQLiteUnavailable
from .sqlite_custody_schema import assert_custody_schema

SCHEMA = "skeleton.ai.fair-stream-sqlite-cas.v1"
MAX_GENERATION = (1 << 63) - 1
_TABLE = "local_fair_stream_custody"


def _digest(value: object, name: str, size: int = 64) -> str:
    if type(value) is not str or len(value) != size or any(
        c not in "0123456789abcdef" for c in value
    ):
        raise ValueError("invalid " + name)
    return value


def _generation(value: object) -> int:
    if type(value) is not int or not 0 <= value <= MAX_GENERATION:
        raise ValueError("invalid expected generation")
    return value


def _encode(envelope: Mapping[str, object]) -> bytes:
    try:
        payload = json.dumps(
            envelope, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("invalid durable custody envelope") from exc
    if len(payload) > MAX_BYTES:
        raise ValueError("durable custody envelope exceeds byte budget")
    return payload


def _decode(payload: object) -> Mapping[str, object]:
    if not isinstance(payload, bytes) or len(payload) > MAX_BYTES:
        raise ValueError("invalid durable custody payload")
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate durable custody JSON key")
            result[key] = value
        return result
    def reject_constant(value: str) -> None:
        raise ValueError("non-finite durable custody value")
    try:
        envelope = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=unique, parse_constant=reject_constant,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("malformed durable custody JSON") from exc
    if type(envelope) is not dict:
        raise ValueError("durable custody envelope must be an object")
    return envelope


class DurableFairStreamStore:
    """Single-session transactional CAS adapter.

    Construct with a *trusted*, already-open SQLite connection; this class
    deliberately does not resolve filesystem paths or open attacker-controlled
    databases. The connection must not be shared outside this adapter, and
    SQLite file permissions, symlink-resistant opening, encryption at rest,
    and key lifecycle remain responsibilities of the local app bootstrap.

    Every load/transition requires the caller's independently trusted
    generation+digest. After a successful commit the caller MUST advance its
    independent high-watermark before dispatch. A crash in that gap requires
    explicit reconciliation, never silent re-execution.
    """

    def __init__(
        self, connection: sqlite3.Connection, *,
        custody_key: bytes, execution_key: bytes, session_id: str,
        whole_request: bool = False,
        private_handle: PrivateSQLiteHandle | None = None,
    ) -> None:
        if not isinstance(connection, sqlite3.Connection):
            raise ValueError("trusted SQLite connection required")
        if connection.in_transaction:
            raise ValueError("connection must have no active transaction")
        if type(custody_key) is not bytes or type(execution_key) is not bytes:
            raise ValueError("typed custody keys required")
        if type(whole_request) is not bool:
            raise ValueError("explicit whole-request policy required")
        self._whole_request = whole_request
        # Reuse the canonical key and identity validation.
        self._empty = AuthenticatedFairStreamCustody(
            custody_key=custody_key, execution_key=execution_key,
            session_id=session_id,
            scheduler=FairStreamScheduler(whole_request=whole_request),
        )
        if private_handle is not None:
            if type(private_handle) is not PrivateSQLiteHandle or private_handle.connection is not connection:
                raise ValueError("exact private custody handle required")
            private_handle.assert_current()
        self._private_handle = private_handle
        self._owner_pid = os.getpid()
        self._connection = connection
        self._custody_key = custody_key
        self._execution_key = execution_key
        self.session_id = session_id
        self._lock = RLock()
        # A preexisting table with a different shape fails at first read/write.
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS local_fair_stream_custody ("
            "session_id TEXT PRIMARY KEY NOT NULL,"
            "generation INTEGER NOT NULL CHECK(generation >= 0),"
            "digest TEXT NOT NULL,"
            "payload BLOB NOT NULL"
            ") WITHOUT ROWID"
        )
        self._assert_schema()

    @property
    def whole_request(self) -> bool:
        return self._whole_request

    def _assert_schema(self) -> None:
        assert_custody_schema(
            self._connection, table=_TABLE,
            columns=("session_id", "generation", "digest", "payload"),
            primary_key="session_id",
        )

    def _require_owner_process(self) -> None:
        if os.getpid() != self._owner_pid:
            raise PrivateSQLiteUnavailable("inherited stream custody requires reopening")

    def _assert_private(self) -> None:
        self._require_owner_process()
        if self._private_handle is not None:
            self._private_handle.assert_current()

    def _begin(self) -> None:
        self._assert_private()
        if self._connection.in_transaction:
            raise ValueError("shared or active SQLite transaction forbidden")
        self._connection.execute("BEGIN IMMEDIATE")

    def _read(self) -> tuple[int, str, bytes] | None:
        self._assert_private()
        self._assert_schema()
        row = self._connection.execute(
            "SELECT generation, CASE WHEN typeof(digest)='text' AND length(CAST(digest AS BLOB))=64"
            " THEN digest END, CASE WHEN typeof(payload)='blob' AND length(payload)<=?"
            " THEN payload END FROM " + _TABLE + " WHERE session_id = ?",
            (MAX_BYTES, self.session_id),
        ).fetchone()
        if row is None:
            return None
        generation, digest, payload = row
        _generation(generation)
        _digest(digest, "stored digest")
        if type(payload) is not bytes or len(payload) > MAX_BYTES:
            raise ValueError("invalid stored custody bytes")
        return generation, digest, payload

    def _restore(
        self, row: tuple[int, str, bytes], *,
        expected_generation: int, expected_digest: str,
    ) -> AuthenticatedFairStreamCustody:
        generation, digest, payload = row
        if generation != expected_generation or not hmac.compare_digest(
            digest, expected_digest
        ):
            raise ValueError("durable custody high-watermark conflict")
        envelope = _decode(payload)
        if _encode(envelope) != payload:
            raise ValueError("noncanonical durable custody encoding")
        owner = AuthenticatedFairStreamCustody.restore(
            envelope, custody_key=self._custody_key,
            execution_key=self._execution_key,
            expected_generation=expected_generation,
            expected_digest=expected_digest,
        )
        if owner.session_id != self.session_id:
            raise ValueError("durable custody session mismatch")
        if owner.whole_request != self._whole_request:
            raise ValueError("durable execution policy mismatch")
        return owner

    def initialize(self) -> dict[str, object]:
        """Initialize exactly once; never overwrite a preexisting session."""
        self._require_owner_process()
        with self._lock:
            envelope = self._empty.export()
            payload = _encode(envelope)
            self._begin()
            try:
                if self._read() is not None:
                    raise ValueError("durable custody already initialized")
                self._connection.execute(
                    "INSERT INTO " + _TABLE +
                    " (session_id, generation, digest, payload)"
                    " VALUES (?, ?, ?, ?)",
                    (self.session_id, 0, envelope["digest"], payload),
                )
                if self._read() != (0, envelope["digest"], payload):
                    raise ValueError("durable initialization readback mismatch")
                self._assert_private()
                self._connection.commit()
                return envelope
            except BaseException:
                self._connection.rollback()
                raise

    def load(
        self, *, expected_generation: int, expected_digest: str,
    ) -> AuthenticatedFairStreamCustody:
        """Read only with an independent high-watermark; no silent fallback."""
        generation = _generation(expected_generation)
        digest = _digest(expected_digest, "trusted high-watermark")
        self._require_owner_process()
        with self._lock:
            self._assert_private()
            if self._connection.in_transaction:
                raise ValueError("shared or active SQLite transaction forbidden")
            # Read schema and payload in a single SQLite snapshot. Otherwise
            # another connection could change schema between verification and SELECT.
            self._connection.execute("BEGIN")
            try:
                row = self._read()
                if row is None:
                    raise ValueError("durable custody session missing")
                owner = self._restore(
                    row, expected_generation=generation, expected_digest=digest,
                )
                self._assert_private()
                return owner
            finally:
                self._connection.rollback()

    def transition(
        self, *, expected_generation: int, expected_digest: str,
        action: str, **kwargs: object,
    ) -> tuple[object | None, dict[str, object]]:
        """Atomically publish a canonical transition or leave state unchanged.

        No live scheduler is mutated before COMMIT. On CAS/SQLite failure,
        the speculative owner is discarded and the previous row survives.
        The returned state is not permission to dispatch until the trusted
        external high-watermark has been advanced.
        """
        generation = _generation(expected_generation)
        digest = _digest(expected_digest, "trusted high-watermark")
        self._require_owner_process()
        with self._lock:
            self._begin()
            try:
                row = self._read()
                if row is None:
                    raise ValueError("durable custody session missing")
                owner = self._restore(
                    row, expected_generation=generation, expected_digest=digest,
                )
                plan, envelope = owner.transition(
                    expected_generation=generation, action=action, **kwargs,
                )
                payload = _encode(envelope)
                next_generation = _generation(envelope["generation"])
                next_digest = _digest(envelope["digest"], "next digest")
                changed = self._connection.execute(
                    "UPDATE " + _TABLE +
                    " SET generation = ?, digest = ?, payload = ?"
                    " WHERE session_id = ? AND generation = ? AND digest = ?",
                    (next_generation, next_digest, payload,
                     self.session_id, generation, digest),
                ).rowcount
                if changed != 1:
                    raise ValueError("durable custody CAS rejected")
                if self._read() != (next_generation, next_digest, payload):
                    raise ValueError("durable custody transition readback mismatch")
                self._assert_private()
                self._connection.commit()
                return plan, envelope
            except BaseException:
                self._connection.rollback()
                raise
