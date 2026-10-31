"""Encrypted, bounded offline result custody for journaled fair-stream inference.

The trusted app supplies a private SQLite handle, an independent 256-bit result
key, an exact model/tokenizer identity and a synchronous inference callback.
No plaintext, prompt, model weights or key bytes are written to SQLite.
The journal must persist RUNNING before invoking this backend. A failure after
the callback begins is outcome-uncertain and MUST NOT cause an automatic retry.
This is CPU-only plumbing; it is not hardware or provider qualification.
"""
from __future__ import annotations

from hashlib import sha256
import hmac
import json
import secrets
import sqlite3
from threading import RLock
from typing import Mapping, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .fair_stream_session import DispatchPermit
from .private_sqlite import PrivateSQLiteHandle

SCHEMA = "skeleton.ai.fair-stream-result-vault.v1"
MAX_RESULT_BYTES = 1 << 20
MAX_RESULT_ROWS = 1_000
MAX_CIPHERTEXT_BYTES = 64 << 20
MAX_TOKENS = 1 << 24
_TABLE = "local_fair_stream_sealed_results"
_COLUMNS = (
    "lease_id", "session_id", "generation", "checkpoint_digest",
    "request_id", "model_digest", "tokenizer_digest", "tokens",
    "bytes_reserved", "consumed_tokens", "plaintext_bytes",
    "nonce", "ciphertext", "result_digest",
)


class SealedResultUnavailable(RuntimeError):
    """Result absent, untrusted, tampered, over budget or not safely readable."""


class OfflineInferenceBackend(Protocol):
    """Trusted synchronous CPU backend; no implicit streaming retry."""

    def generate(
        self, permit: DispatchPermit, state: Mapping[str, object],
    ) -> tuple[int, bytes]: ...


def _hex(value: object, length: int, label: str) -> str:
    if type(value) is not str or len(value) != length or any(
        c not in "0123456789abcdef" for c in value
    ):
        raise ValueError("invalid " + label)
    return value


def _identity(permit: DispatchPermit) -> None:
    if type(permit) is not DispatchPermit or permit.device_qualified:
        raise ValueError("canonical CPU-only permit required")
    _hex(permit.lease_id, 64, "lease")
    _hex(permit.checkpoint_digest, 64, "checkpoint")
    if (
        type(permit.request_id) is not str
        or not permit.request_id
        or len(permit.request_id.encode("utf-8")) > 128
        or type(permit.generation) is not int
        or not 0 <= permit.generation < (1 << 63)
        or type(permit.tokens) is not int
        or not 1 <= permit.tokens <= MAX_TOKENS
        or type(permit.bytes_reserved) is not int
        or not 0 < permit.bytes_reserved < (1 << 63)
    ):
        raise ValueError("invalid bounded dispatch permit")


def _aad(
    *, permit: DispatchPermit, session_id: str, model_digest: str,
    tokenizer_digest: str, consumed_tokens: int, plaintext_bytes: int,
) -> bytes:
    body = {
        "schema": SCHEMA,
        "session_id": session_id,
        "lease_id": permit.lease_id,
        "generation": permit.generation,
        "checkpoint_digest": permit.checkpoint_digest,
        "request_id": permit.request_id,
        "model_digest": model_digest,
        "tokenizer_digest": tokenizer_digest,
        "tokens": permit.tokens,
        "bytes_reserved": permit.bytes_reserved,
        "consumed_tokens": consumed_tokens,
        "plaintext_bytes": plaintext_bytes,
    }
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


class SealedFairStreamResultVault:
    """App-owned encrypted result store implementing DurableResultBackend.

    The caller MUST keep the private handle alive and exclusive, and supply a
    distinct execution-journal connection. AES-GCM authenticity is independent
    of the journal MAC. Database rollback resistance still depends on the
    external custody high-watermark and platform backup/restore controls.
    The app is responsible for authentication before calling read_committed.
    """

    def __init__(
        self, handle: PrivateSQLiteHandle, *, session_id: str,
        model_digest: str, tokenizer_digest: str, result_key: bytes,
        backend: OfflineInferenceBackend,
    ) -> None:
        if type(handle) is not PrivateSQLiteHandle or handle._closed:
            raise ValueError("live canonical private SQLite handle required")
        self.session_id = _hex(session_id, 32, "session")
        self.model_digest = _hex(model_digest, 64, "model")
        self.tokenizer_digest = _hex(tokenizer_digest, 64, "tokenizer")
        if type(result_key) is not bytes or len(result_key) != 32:
            raise ValueError("independent 256-bit result encryption key required")
        if not callable(getattr(backend, "generate", None)):
            raise ValueError("trusted synchronous inference backend required")
        self._handle = handle
        self._connection = handle.connection
        self._cipher = AESGCM(result_key)
        self._backend = backend
        self._lock = RLock()
        if self._connection.in_transaction:
            raise ValueError("exclusive idle SQLite result connection required")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS " + _TABLE + " ("
            "lease_id TEXT PRIMARY KEY NOT NULL,"
            "session_id TEXT NOT NULL,"
            "generation INTEGER NOT NULL CHECK(generation >= 0),"
            "checkpoint_digest TEXT NOT NULL,"
            "request_id TEXT NOT NULL,"
            "model_digest TEXT NOT NULL,"
            "tokenizer_digest TEXT NOT NULL,"
            "tokens INTEGER NOT NULL CHECK(tokens > 0),"
            "bytes_reserved INTEGER NOT NULL CHECK(bytes_reserved > 0),"
            "consumed_tokens INTEGER NOT NULL CHECK(consumed_tokens >= 0),"
            "plaintext_bytes INTEGER NOT NULL CHECK(plaintext_bytes >= 0),"
            "nonce BLOB NOT NULL,"
            "ciphertext BLOB NOT NULL,"
            "result_digest TEXT NOT NULL"
            ") WITHOUT ROWID"
        )
        columns = tuple(
            row[1] for row in self._connection.execute(
                "PRAGMA table_info(" + _TABLE + ")"
            )
        )
        if columns != _COLUMNS:
            raise SealedResultUnavailable("untrusted result table schema")
        # Reject unexpected triggers that could copy encrypted payloads or
        # change durability semantics. The caller still owns the DB handle.
        if self._connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'"
            " AND tbl_name=?", (_TABLE,),
        ).fetchone()[0]:
            raise SealedResultUnavailable("untrusted result table trigger")

    def _require_open(self) -> None:
        if self._handle._closed:
            raise SealedResultUnavailable("result database handle closed")
        if self._connection.in_transaction:
            raise SealedResultUnavailable("shared SQLite transaction forbidden")

    def _row(self, lease_id: str) -> tuple[object, ...] | None:
        return self._connection.execute(
            "SELECT " + ", ".join(_COLUMNS) + " FROM " + _TABLE
            + " WHERE lease_id=?", (lease_id,),
        ).fetchone()

    def _validate_state(
        self, permit: DispatchPermit, state: Mapping[str, object],
    ) -> None:
        _identity(permit)
        if (
            not isinstance(state, Mapping)
            or state.get("session_id") != self.session_id
            or state.get("generation") != permit.generation
            or state.get("checkpoint_digest") != permit.checkpoint_digest
        ):
            raise SealedResultUnavailable("result state does not bind permit")
        checkpoint = state.get("checkpoint")
        pending = checkpoint.get("pending") if isinstance(checkpoint, Mapping) else None
        if (
            type(pending) is not list or len(pending) != 1
            or type(pending[0]) is not dict
            or pending[0].get("lease_id") != permit.lease_id
            or pending[0].get("request_id") != permit.request_id
            or pending[0].get("tokens") != permit.tokens
            or pending[0].get("bytes_reserved") != permit.bytes_reserved
        ):
            raise SealedResultUnavailable("pending lease does not bind permit")

    def run_and_commit(
        self, permit: DispatchPermit, state: Mapping[str, object],
    ) -> tuple[int, str]:
        """Commit encrypted output before returning a digest to the journal.

        The backend is called once only, after the journal has persisted RUNNING.
        Any exception, including SQLite commit uncertainty, propagates and must
        leave the execution journal in RUNNING. No replay is authorized.
        """
        self._validate_state(permit, state)
        with self._lock:
            self._require_open()
            if self._row(permit.lease_id) is not None:
                raise SealedResultUnavailable("result lease already published")
            # No database transaction spans inference; other SQLite readers
            # are not blocked by potentially long CPU inference.
            consumed, plaintext = self._backend.generate(permit, state)
            if (
                type(consumed) is not int
                or not 0 <= consumed <= permit.tokens
                or type(plaintext) is not bytes
                or not 0 <= len(plaintext) <= MAX_RESULT_BYTES
            ):
                raise SealedResultUnavailable("unbounded inference result")
            nonce = secrets.token_bytes(12)
            aad = _aad(
                permit=permit, session_id=self.session_id,
                model_digest=self.model_digest,
                tokenizer_digest=self.tokenizer_digest,
                consumed_tokens=consumed, plaintext_bytes=len(plaintext),
            )
            ciphertext = self._cipher.encrypt(nonce, plaintext, aad)
            digest = sha256(ciphertext).hexdigest()
            self._require_open()
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                if self._row(permit.lease_id) is not None:
                    raise SealedResultUnavailable("result lease already published")
                rows, total = self._connection.execute(
                    "SELECT COUNT(*), COALESCE(SUM(LENGTH(ciphertext)), 0)"
                    " FROM " + _TABLE
                ).fetchone()
                if (
                    rows >= MAX_RESULT_ROWS
                    or total + len(ciphertext) > MAX_CIPHERTEXT_BYTES
                ):
                    raise SealedResultUnavailable("result vault capacity exhausted")
                self._connection.execute(
                    "INSERT INTO " + _TABLE + " ("
                    + ", ".join(_COLUMNS) + ") VALUES ("
                    + ", ".join("?" for _ in _COLUMNS) + ")",
                    (
                        permit.lease_id, self.session_id, permit.generation,
                        permit.checkpoint_digest, permit.request_id,
                        self.model_digest, self.tokenizer_digest,
                        permit.tokens, permit.bytes_reserved, consumed,
                        len(plaintext), nonce, ciphertext, digest,
                    ),
                )
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise
            return consumed, digest

    def read_committed(
        self, permit: DispatchPermit, *, expected_result_digest: str,
    ) -> bytes:
        """Authorized in-process read bound to an already signed receipt.

        The application must first verify authorization and the journal's
        authenticated completion receipt; this method alone is not an ACL.
        """
        _identity(permit)
        expected = _hex(expected_result_digest, 64, "result receipt digest")
        with self._lock:
            self._require_open()
            row = self._row(permit.lease_id)
            if row is None:
                raise SealedResultUnavailable("result not committed")
            (
                lease_id, session_id, generation, checkpoint_digest, request_id,
                model_digest, tokenizer_digest, tokens, bytes_reserved,
                consumed, length, nonce, ciphertext, digest,
            ) = row
            if (
                (lease_id, session_id, generation, checkpoint_digest, request_id)
                != (permit.lease_id, self.session_id, permit.generation,
                    permit.checkpoint_digest, permit.request_id)
                or (model_digest, tokenizer_digest)
                != (self.model_digest, self.tokenizer_digest)
                or (tokens, bytes_reserved)
                != (permit.tokens, permit.bytes_reserved)
                or type(consumed) is not int
                or not 0 <= consumed <= permit.tokens
                or type(length) is not int
                or not 0 <= length <= MAX_RESULT_BYTES
                or type(nonce) is not bytes or len(nonce) != 12
                or type(ciphertext) is not bytes
                or len(ciphertext) != length + 16
                or type(digest) is not str
                or not hmac.compare_digest(digest, expected)
                or not hmac.compare_digest(sha256(ciphertext).hexdigest(), expected)
            ):
                raise SealedResultUnavailable("result binding or digest mismatch")
            aad = _aad(
                permit=permit, session_id=self.session_id,
                model_digest=self.model_digest,
                tokenizer_digest=self.tokenizer_digest,
                consumed_tokens=consumed, plaintext_bytes=length,
            )
            try:
                plaintext = self._cipher.decrypt(nonce, ciphertext, aad)
            except (InvalidTag, ValueError) as exc:
                raise SealedResultUnavailable("result authentication failed") from exc
            if len(plaintext) != length:
                raise SealedResultUnavailable("result length mismatch")
            return plaintext
