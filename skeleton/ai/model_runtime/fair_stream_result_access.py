"""One-use Ed25519 operator grants for reading sealed offline inference results.

A verified journal receipt proves that the backend already committed a result.
A separately provisioned operator signing key grants ONE read of that result.
The private SQLite grant ledger consumes authorization before decrypting, so
a crash cannot silently replay the grant. No prompt or plaintext is logged.
"""
from __future__ import annotations

from contextlib import contextmanager
import hmac
import json
import os
import sqlite3
from threading import RLock
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from .fair_stream_execution_journal import (
    FairStreamExecutionJournal, _validate_permit,
)
from .fair_stream_result_vault import (
    MAX_RESULT_BYTES, SealedFairStreamResultVault,
)
from .fair_stream_session import DispatchPermit
from .private_sqlite import PrivateSQLiteHandle, PrivateSQLiteUnavailable
from .sqlite_custody_schema import CustodySchemaError, assert_custody_schema

SCHEMA = "skeleton.ai.fair-stream-result-read-grant.v1"
MAX_GRANT_BYTES = 1024
MAX_USED_GRANTS = 10_000
_TABLE = "local_fair_stream_result_read_grants"
_FIELDS = (
    "schema", "session_id", "generation", "checkpoint_digest",
    "lease_id", "result_digest", "nonce",
)


class ResultReadDenied(RuntimeError):
    """Missing, stale, forged, replayed or unverified operator approval."""


def _hex(value: object, size: int, label: str) -> str:
    if type(value) is not str or len(value) != size or any(
        c not in "0123456789abcdef" for c in value
    ):
        raise ResultReadDenied("invalid " + label)
    return value


def _body(
    *, session_id: str, generation: int, checkpoint_digest: str,
    lease_id: str, result_digest: str, nonce: str,
) -> dict[str, object]:
    _hex(session_id, 32, "session")
    _hex(checkpoint_digest, 64, "checkpoint")
    _hex(lease_id, 64, "lease")
    _hex(result_digest, 64, "result")
    _hex(nonce, 32, "nonce")
    if type(generation) is not int or not 0 <= generation < (1 << 63):
        raise ResultReadDenied("invalid generation")
    return {
        "schema": SCHEMA,
        "session_id": session_id,
        "generation": generation,
        "checkpoint_digest": checkpoint_digest,
        "lease_id": lease_id,
        "result_digest": result_digest,
        "nonce": nonce,
    }


def _encode(body: Mapping[str, object]) -> bytes:
    try:
        raw = json.dumps(
            body, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ResultReadDenied("invalid grant serialization") from exc
    if len(raw) > MAX_GRANT_BYTES:
        raise ResultReadDenied("grant exceeds byte budget")
    return raw


def issue_result_read_grant(
    *, signing_key: Ed25519PrivateKey, session_id: str, generation: int,
    checkpoint_digest: str, lease_id: str, result_digest: str, nonce: str,
) -> dict[str, object]:
    """Trusted OPERATOR side only; never expose private key to model process.

    The caller is responsible for independent operator authentication,
    signing-key protection and cryptographically random, unique nonces.
    """
    if not isinstance(signing_key, Ed25519PrivateKey):
        raise ValueError("canonical Ed25519 operator signing key required")
    body = _body(
        session_id=session_id, generation=generation,
        checkpoint_digest=checkpoint_digest, lease_id=lease_id,
        result_digest=result_digest, nonce=nonce,
    )
    return {**body, "signature": signing_key.sign(_encode(body)).hex()}


def verify_result_read_grant(
    grant: Mapping[str, object], *, public_key: Ed25519PublicKey,
    permit: DispatchPermit, session_id: str, result_digest: str,
) -> str:
    """Verify exact signed lease, model-result receipt and one-use nonce."""
    if not isinstance(public_key, Ed25519PublicKey):
        raise ResultReadDenied("trusted operator verification key required")
    try:
        _validate_permit(permit)
    except ValueError as exc:
        raise ResultReadDenied("canonical CPU-only permit required") from exc
    if (type(grant) is not dict or len(grant) != len(_FIELDS) + 1
            or set(grant) != set(_FIELDS) | {"signature"}):
        raise ResultReadDenied("invalid grant fields")
    if type(grant["schema"]) is not str or grant["schema"] != SCHEMA:
        raise ResultReadDenied("unsupported result read grant schema")
    _hex(session_id, 32, "session")
    _hex(result_digest, 64, "result")
    body = _body(
        session_id=grant["session_id"], generation=grant["generation"],
        checkpoint_digest=grant["checkpoint_digest"],
        lease_id=grant["lease_id"], result_digest=grant["result_digest"],
        nonce=grant["nonce"],
    )
    signature = _hex(grant["signature"], 128, "signature")
    if (
        body["session_id"] != session_id
        or body["generation"] != permit.generation
        or body["checkpoint_digest"] != permit.checkpoint_digest
        or body["lease_id"] != permit.lease_id
        or not hmac.compare_digest(body["result_digest"], result_digest)
    ):
        raise ResultReadDenied("grant does not bind signed result receipt")
    try:
        public_key.verify(bytes.fromhex(signature), _encode(body))
    except InvalidSignature as exc:
        raise ResultReadDenied("operator signature invalid") from exc
    return body["nonce"]


class AuthorizedSealedResultReader:
    """Trusted app adapter; signed journal receipt + one-use operator grant.

    The caller supplies a THIRD private SQLite handle exclusively for the
    consumed-grant ledger. The result vault, execution journal and grant ledger
    must use separate handles; no automatic retry follows uncertain commits.
    The caller owns connection lifetime and external rollback protection.
    """

    def __init__(
        self, *, journal: FairStreamExecutionJournal,
        vault: SealedFairStreamResultVault, grant_handle: PrivateSQLiteHandle,
        operator_public_key: bytes,
    ) -> None:
        if type(journal) is not FairStreamExecutionJournal:
            raise ValueError("canonical signed execution journal required")
        if type(vault) is not SealedFairStreamResultVault:
            raise ValueError("canonical encrypted result vault required")
        if type(grant_handle) is not PrivateSQLiteHandle or grant_handle._closed:
            raise ValueError("live private grant-ledger handle required")
        if type(operator_public_key) is not bytes or len(operator_public_key) != 32:
            raise ValueError("pinned Ed25519 operator public key required")
        journal._require_owner_process()
        vault._require_owner()
        if journal.session_id != vault.session_id:
            raise ValueError("journal and vault session mismatch")
        if journal._connection is vault._connection:
            raise ValueError("independent journal and result connections required")
        if hmac.compare_digest(operator_public_key, journal._key):
            raise ValueError("independent operator verification key required")
        if (
            grant_handle is vault._handle
            or grant_handle.connection is vault._connection
            or grant_handle.connection is journal._connection
        ):
            raise ValueError("independent grant ledger required")
        grant_handle.assert_current()
        vault._handle.assert_current()
        if journal._private_handle is None:
            # In-memory journal is retained for deterministic test composition.
            # Real disk custody cannot be certified by connection identity alone.
            databases = journal._connection.execute("PRAGMA database_list").fetchall()
            main = [row for row in databases if row[1] == "main"]
            if (len(main) != 1 or main[0][2] != ""
                    or any(row[1] not in {"main", "temp"} for row in databases)):
                raise ValueError("disk journal requires an exact private handle")
        else:
            journal._private_handle.assert_current()
            journal_inode = os.fstat(journal._private_handle._file_fd)
            for handle in (grant_handle, vault._handle):
                identity = os.fstat(handle._file_fd)
                if (journal_inode.st_dev, journal_inode.st_ino) == (identity.st_dev, identity.st_ino):
                    raise ValueError("grant and result ledgers must use a distinct journal inode")
        result_inode = os.fstat(vault._handle._file_fd)
        grant_inode = os.fstat(grant_handle._file_fd)
        if (result_inode.st_dev, result_inode.st_ino) == (
            grant_inode.st_dev, grant_inode.st_ino
        ):
            raise ValueError("grant ledger must use a distinct database inode")
        self._public_key = Ed25519PublicKey.from_public_bytes(
            operator_public_key,
        )
        self._journal = journal
        self._vault = vault
        self._handle = grant_handle
        self._connection = grant_handle.connection
        self._lock = RLock()
        self._active = False
        self._invalidated = False
        if self._connection.in_transaction:
            raise ValueError("idle grant-ledger connection required")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS " + _TABLE + " ("
            "nonce TEXT PRIMARY KEY NOT NULL,"
            "lease_id TEXT NOT NULL,"
            "receipt_digest TEXT NOT NULL"
            ") WITHOUT ROWID"
        )
        columns = tuple(
            row[1] for row in self._connection.execute(
                "PRAGMA table_info(" + _TABLE + ")"
            )
        )
        if columns != ("nonce", "lease_id", "receipt_digest"):
            raise ResultReadDenied("untrusted consumed-grant table schema")
        if self._connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'"
            " AND tbl_name=?", (_TABLE,),
        ).fetchone()[0]:
            raise ResultReadDenied("untrusted grant-ledger trigger")
        self._assert_schema()

    def _assert_schema(self) -> None:
        try:
            assert_custody_schema(
                self._connection, table=_TABLE,
                columns=("nonce", "lease_id", "receipt_digest"), primary_key="nonce",
            )
        except CustodySchemaError as exc:
            raise ResultReadDenied("grant ledger schema changed") from exc

    def _consumed_identity(self, nonce: str) -> tuple[str, str] | None:
        """Bound the SQL projection; malformed existent rows never mean absence."""
        row = self._connection.execute(
            "SELECT CASE WHEN typeof(lease_id)='text' AND length(CAST(lease_id AS BLOB))=64"
            " THEN lease_id END, CASE WHEN typeof(receipt_digest)='text'"
            " AND length(CAST(receipt_digest AS BLOB))=64 THEN receipt_digest END"
            " FROM " + _TABLE + " WHERE nonce=?", (nonce,),
        ).fetchone()
        if row is None:
            return None
        return (_hex(row[0], 64, "consumed lease identity"),
                _hex(row[1], 64, "consumed receipt digest"))

    def _confirm_consumption(self, *, nonce: str, lease_id: str, digest: str) -> None:
        """Recheck committed consumption within an independent read snapshot."""
        try:
            self._handle.assert_current()
            if self._connection.in_transaction:
                raise ResultReadDenied("grant ledger has unexpected transaction")
            self._connection.execute("BEGIN")
            try:
                self._assert_schema()
                row = self._consumed_identity(nonce)
                if row != (lease_id, digest):
                    raise ResultReadDenied("committed grant consumption unavailable")
                self._handle.assert_current()
            finally:
                self._connection.rollback()
        except (PrivateSQLiteUnavailable, sqlite3.Error) as exc:
            raise ResultReadDenied("grant ledger unavailable after consumption") from exc

    def _confirm_receipt(self, permit: DispatchPermit, expected: dict[str, object]) -> None:
        try:
            current = self._journal.recover_committed_receipt(permit)
        except (ValueError, RuntimeError, sqlite3.Error) as exc:
            raise ResultReadDenied("committed journal authority changed during read") from exc
        if type(current) is not dict or current != expected:
            raise ResultReadDenied("committed journal authority changed during read")

    @contextmanager
    def _read_operation(self):
        # Process checks must precede any potentially inherited Python lock.
        try:
            self._handle.require_owner_process()
            self._journal._require_owner_process()
            self._vault._require_owner()
        except (PrivateSQLiteUnavailable, RuntimeError) as exc:
            raise ResultReadDenied("grant ledger unavailable") from exc
        with self._lock:
            if self._active:
                self._invalidated = True
                raise ResultReadDenied("recursive result read denied")
            self._active = True
            self._invalidated = False
            try:
                yield
                if self._invalidated:
                    raise ResultReadDenied("recursive result read invalidated authorization")
            finally:
                self._active = False

    def read_once(
        self, permit: DispatchPermit, *,
        operator_grant: Mapping[str, object],
    ) -> bytes:
        """Return plaintext in RAM only after consuming the exact grant.

        The caller must enforce app user authorization before invoking this
        method. A consumed grant remains consumed if decryption later fails.
        """
        with self._read_operation():
            try:
                _validate_permit(permit)
            except ValueError as exc:
                raise ResultReadDenied("canonical CPU-only permit required") from exc
            try:
                self._assert_schema()
                self._handle.assert_current()
                if self._connection.in_transaction:
                    raise ResultReadDenied("grant ledger unavailable")
            except (PrivateSQLiteUnavailable, sqlite3.Error) as exc:
                raise ResultReadDenied("grant ledger unavailable or inode custody changed") from exc
            try:
                receipt = self._journal.recover_committed_receipt(permit)
            except (ValueError, RuntimeError, sqlite3.Error) as exc:
                raise ResultReadDenied("authenticated journal receipt unavailable") from exc
            if (
                type(receipt) is not dict
                or receipt.get("lease_id") != permit.lease_id
                or receipt.get("generation") != permit.generation
                or receipt.get("checkpoint_digest") != permit.checkpoint_digest
            ):
                raise ResultReadDenied("journal receipt does not bind permit")
            digest = _hex(receipt.get("result_digest"), 64, "receipt digest")
            consumed = receipt.get("consumed_tokens")
            if type(consumed) is not int or not 0 <= consumed <= permit.tokens:
                raise ResultReadDenied("invalid signed consumed token count")
            nonce = verify_result_read_grant(
                operator_grant, public_key=self._public_key,
                permit=permit, session_id=self._journal.session_id,
                result_digest=digest,
            )
            if self._invalidated:
                raise ResultReadDenied("recursive result read invalidated authorization")
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._assert_schema()
                count = self._connection.execute(
                    "SELECT COUNT(*) FROM " + _TABLE
                ).fetchone()[0]
                if count >= MAX_USED_GRANTS:
                    raise ResultReadDenied("consumed grant capacity exhausted")
                if self._connection.execute(
                    "SELECT 1 FROM " + _TABLE + " WHERE nonce=?",
                    (nonce,),
                ).fetchone() is not None:
                    raise ResultReadDenied("operator grant already consumed")
                self._connection.execute(
                    "INSERT INTO " + _TABLE
                    + " (nonce, lease_id, receipt_digest) VALUES (?, ?, ?)",
                    (nonce, permit.lease_id, digest),
                )
                self._handle.assert_current()
                self._assert_schema()
                row = self._consumed_identity(nonce)
                if row != (permit.lease_id, digest):
                    raise ResultReadDenied("grant consumption readback mismatch")
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise
            # No decrypt before durable grant consumption. A crash between
            # COMMIT and decrypt burns the grant; the operator must issue a
            # different signed nonce after reviewing the uncertain read.
            # Check the durable grant and signed journal again before AND
            # after decrypting. Never release plaintext on a detected custody
            # change. Independent rollback protection remains caller-owned.
            self._confirm_consumption(nonce=nonce, lease_id=permit.lease_id, digest=digest)
            self._confirm_receipt(permit, receipt)
            if self._invalidated:
                raise ResultReadDenied("recursive result read invalidated authorization")
            plaintext = self._vault.read_committed(
                permit, expected_result_digest=digest, expected_consumed_tokens=consumed,
            )
            if type(plaintext) is not bytes or len(plaintext) > MAX_RESULT_BYTES:
                raise ResultReadDenied("unbounded result plaintext")
            self._confirm_receipt(permit, receipt)
            self._confirm_consumption(nonce=nonce, lease_id=permit.lease_id, digest=digest)
            return plaintext
