"""Encrypted versioned Academy state custody with atomic CAS publication.

Private app-owned SQLite connection and key are required. This adapter restores
typed learner state for a NEW session, not suspended native execution. Revisions
are immutable, bounded and individually authenticated. Trusted external head
receipts are needed to detect a whole-database rollback or tail deletion.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import os
import secrets
import sqlite3
import threading

from skeleton.ai.model_runtime.private_sqlite import PrivateSQLiteHandle

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from skeleton.learning.school.checkpoint_codec import (
    AcademyState, MAX_CHECKPOINT_BYTES, decode_state, encode_state, identity,
)

_TABLE = "academy_checkpoint_v1"
_FIELDS = ("owner", "learner", "revision", "previous", "digest",
           "request", "nonce", "ciphertext", "receipt")
_GENESIS = "0" * 64


class AcademyConflict(RuntimeError):
    """Stale revision, different request content or missing authority."""


class AcademyIntegrityError(RuntimeError):
    """Durable checkpoint failed its authenticated identity checks."""


class AcademyCapacity(RuntimeError):
    """A bounded checkpoint budget has been exhausted."""


@dataclass(frozen=True, slots=True)
class AcademyReceipt:
    learner: str
    revision: int
    previous: str
    state_digest: str
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class AcademyRevision:
    receipt: AcademyReceipt
    state: AcademyState


def _sha(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid Academy SHA-256 identity")
    return value


def _revision(value, *, genesis=False):
    if type(value) is not int or not (0 if genesis else 1) <= value < 1 << 63:
        raise ValueError("invalid Academy revision")
    return value


def _canonical(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("ascii")


class AcademyCheckpointStore:
    """Caller owns the trusted connection, its permissions and the key lifecycle."""

    def __init__(self, connection: sqlite3.Connection, *, owner: str, key: bytes,
                 max_revisions: int = 256, max_total_bytes: int = 64 << 20,
                 private_handle: PrivateSQLiteHandle | None = None,
                 initialize: bool = True):
        if not isinstance(connection, sqlite3.Connection) or connection.in_transaction:
            raise ValueError("exclusive idle SQLite connection required")
        if type(key) is not bytes or len(key) != 32:
            raise ValueError("independent 256-bit checkpoint key required")
        if type(max_revisions) is not int or not 1 <= max_revisions <= 4096:
            raise ValueError("invalid checkpoint revision budget")
        if type(max_total_bytes) is not int or not 4096 <= max_total_bytes <= 512 << 20:
            raise ValueError("invalid checkpoint storage budget")
        if type(initialize) is not bool:
            raise ValueError("explicit initialization policy required")
        if private_handle is not None:
            if type(private_handle) is not PrivateSQLiteHandle or private_handle.connection is not connection:
                raise ValueError("private SQLite handle must own the exact connection")
            private_handle.assert_current()
        self._private_handle = private_handle
        self._db = connection
        self._key = key
        self._cipher = AESGCM(hmac.new(key, b"academy.checkpoint.aead.v1", sha256).digest())
        self._owner_id = self._opaque("owner", identity(owner))
        self._max_revisions = max_revisions
        self._max_bytes = max_total_bytes
        self._pid = os.getpid()
        self._thread = threading.get_ident()
        self._closed = False
        with self._tx(check=False):
            if initialize:
                connection.execute(
                    f"CREATE TABLE IF NOT EXISTS {_TABLE} ("
                    "owner TEXT NOT NULL, learner TEXT NOT NULL, revision INTEGER NOT NULL,"
                    "previous TEXT NOT NULL, digest TEXT NOT NULL, request TEXT NOT NULL,"
                    "nonce BLOB NOT NULL, ciphertext BLOB NOT NULL, receipt TEXT NOT NULL,"
                    "PRIMARY KEY(owner,learner,revision), UNIQUE(owner,learner,request)) WITHOUT ROWID"
                )
            self._schema()

    def _opaque(self, *parts):
        return hmac.new(self._key, b"academy.identity.v1\0" + _canonical(parts), sha256).hexdigest()

    def _learner(self, student_id):
        return self._opaque("learner", self._owner_id, identity(student_id))

    def _schema(self):
        rows = self._db.execute(f"PRAGMA table_info({_TABLE})").fetchall()
        if (tuple(x[1] for x in rows) != _FIELDS
                or tuple(x[2].upper() for x in rows) !=
                ("TEXT", "TEXT", "INTEGER", "TEXT", "TEXT", "TEXT", "BLOB", "BLOB", "TEXT")
                or tuple(x[3] for x in rows) != (1,) * len(_FIELDS)
                or tuple(x[5] for x in rows) != (1, 2, 3) + (0,) * 6):
            raise AcademyIntegrityError("unexpected Academy checkpoint schema")
        if self._db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
                            (_TABLE,)).fetchone():
            raise AcademyIntegrityError("checkpoint table triggers forbidden")
        indexes = self._db.execute(f"PRAGMA index_list({_TABLE})").fetchall()
        unique = False
        for index in indexes:
            if index[2] != 1 or index[4] != 0:
                continue
            # SQLite-created autoindexes have restricted names; never
            # interpolate unchecked schema-controlled identifiers.
            name = index[1]
            if type(name) is not str or not name.isidentifier():
                continue
            columns = tuple(row[2] for row in self._db.execute(
                "SELECT * FROM pragma_index_info(?)", (name,)
            ))
            if columns == ("owner", "learner", "request"):
                unique = True
        if not unique:
            raise AcademyIntegrityError("request uniqueness constraint missing")

    def _require_owner(self):
        if self._closed or self._pid != os.getpid() or self._thread != threading.get_ident():
            raise RuntimeError("Academy storage owner closed or changed")
        if self._private_handle is not None:
            self._private_handle.assert_current()
        if self._db.in_transaction:
            raise RuntimeError("Academy requires exclusive transaction ownership")

    @contextmanager
    def _tx(self, *, check=True):
        self._require_owner()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            if self._private_handle is not None:
                self._private_handle.assert_current()
            if check:
                self._schema()
            yield
            if self._private_handle is not None:
                self._private_handle.assert_current()
            self._db.commit()
        except BaseException:
            self._db.rollback()
            raise

    def _header(self, learner, revision, previous, digest, request):
        return _canonical(["academy.checkpoint.v1", self._owner_id,
                           learner, revision, previous, digest, request])

    def _receipt(self, header, nonce, ciphertext):
        # Receipt binds the actual encrypted bytes as well as the logical state.
        return sha256(b"academy.receipt.v1\0" + header + nonce + ciphertext).hexdigest()

    def _read(self, row, student_id, learner):
        try:
            owner, stored_learner, revision, previous, digest, request, nonce, ciphertext, receipt = tuple(row)
            if owner != self._owner_id or stored_learner != learner:
                raise ValueError("foreign Academy record")
            revision = _revision(revision)
            for item in (previous, digest, request, receipt):
                _sha(item)
            if type(nonce) is not bytes or len(nonce) != 12 or type(ciphertext) is not bytes:
                raise ValueError("invalid checkpoint envelope")
            if not 17 <= len(ciphertext) <= MAX_CHECKPOINT_BYTES + 16:
                raise ValueError("checkpoint ciphertext exceeds budget")
            header = self._header(learner, revision, previous, digest, request)
            if not hmac.compare_digest(receipt, self._receipt(header, nonce, ciphertext)):
                raise ValueError("checkpoint receipt does not bind bytes")
            raw = self._cipher.decrypt(nonce, ciphertext, header)
            if not hmac.compare_digest(sha256(raw).hexdigest(), digest):
                raise ValueError("checkpoint content identity mismatch")
            state = decode_state(raw)
            if state.student.student_id != student_id:
                raise ValueError("checkpoint learner identity mismatch")
            return AcademyRevision(AcademyReceipt(learner, revision, previous, digest, receipt), state)
        except (InvalidTag, TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise AcademyIntegrityError("Academy checkpoint authentication failed") from exc

    def _bounds(self, learner):
        count = self._db.execute(
            f"SELECT COUNT(*) FROM {_TABLE} WHERE owner=? AND learner=?",
            (self._owner_id, learner),
        ).fetchone()[0]
        total = self._db.execute(
            f"SELECT COALESCE(SUM(length(ciphertext)+512),0) FROM {_TABLE}"
        ).fetchone()[0]
        if count > self._max_revisions or total > self._max_bytes:
            raise AcademyCapacity("existing Academy storage exceeds configured budget")
        oversized = self._db.execute(
            f"SELECT 1 FROM {_TABLE} WHERE owner=? AND learner=? AND "
            "(length(ciphertext)>? OR length(nonce)<>12 OR length(previous)<>64 "
            "OR length(digest)<>64 OR length(request)<>64 OR length(receipt)<>64) LIMIT 1",
            (self._owner_id, learner, MAX_CHECKPOINT_BYTES + 16),
        ).fetchone()
        if oversized:
            raise AcademyIntegrityError("checkpoint envelope length invalid")
        return count, total

    def _history(self, student_id, learner):
        """Verify every retained link, returning compact receipts and latest state."""
        self._bounds(learner)
        cursor = self._db.execute(
            f"SELECT {','.join(_FIELDS)} FROM {_TABLE} WHERE owner=? AND learner=? ORDER BY revision",
            (self._owner_id, learner),
        )
        previous = _GENESIS
        receipts = []
        latest = None
        for index, row in enumerate(cursor, 1):
            latest = self._read(row, student_id, learner)
            receipt = latest.receipt
            if receipt.revision != index or receipt.previous != previous:
                raise AcademyIntegrityError("checkpoint history is gapped or reordered")
            previous = receipt.receipt_digest
            receipts.append(receipt)
        return tuple(receipts), latest

    @staticmethod
    def _check_head(latest, expected):
        if expected is None:
            return
        if type(expected) is not AcademyReceipt:
            raise TypeError("trusted AcademyReceipt required")
        if latest is None or latest.receipt != expected:
            raise AcademyConflict("stored Academy head differs from trusted receipt")

    def load(self, student_id: str, *, trusted_head: AcademyReceipt | None = None) -> AcademyRevision | None:
        learner = self._learner(student_id)
        with self._tx():
            _, latest = self._history(student_id, learner)
            self._check_head(latest, trusted_head)
            return latest

    def history(self, student_id: str, *, trusted_head: AcademyReceipt | None = None):
        learner = self._learner(student_id)
        with self._tx():
            receipts, latest = self._history(student_id, learner)
            self._check_head(latest, trusted_head)
            return receipts

    def load_revision(self, student_id: str, revision: int, *,
                      trusted_head: AcademyReceipt | None = None) -> AcademyRevision:
        learner = self._learner(student_id)
        _revision(revision)
        with self._tx():
            receipts, latest = self._history(student_id, learner)
            self._check_head(latest, trusted_head)
            if revision > len(receipts):
                raise KeyError("Academy revision unavailable")
            row = self._db.execute(
                f"SELECT {','.join(_FIELDS)} FROM {_TABLE} WHERE owner=? AND learner=? AND revision=?",
                (self._owner_id, learner, revision),
            ).fetchone()
            return self._read(row, student_id, learner)

    def save(self, state: AcademyState, *, expected_revision: int, request_id: str,
             trusted_head: AcademyReceipt | None = None) -> AcademyReceipt:
        expected_revision = _revision(expected_revision, genesis=True)
        request_id = identity(request_id)
        raw = encode_state(state)
        student_id = decode_state(raw).student.student_id
        learner = self._learner(student_id)
        request = self._opaque("request", self._owner_id, learner, request_id)
        digest = sha256(raw).hexdigest()
        with self._tx():
            count, total = self._bounds(learner)
            receipts, latest = self._history(student_id, learner)
            self._check_head(latest, trusted_head)
            old = self._db.execute(
                f"SELECT {','.join(_FIELDS)} FROM {_TABLE} WHERE owner=? AND learner=? AND request=?",
                (self._owner_id, learner, request),
            ).fetchone()
            if old is not None:
                result = self._read(old, student_id, learner).receipt
                if result.state_digest != digest or result.revision != expected_revision + 1:
                    raise AcademyConflict("checkpoint request identity conflict")
                return result
            if expected_revision != count or len(receipts) != count:
                raise AcademyConflict("stale Academy revision")
            if count >= self._max_revisions or total + len(raw) + 528 > self._max_bytes:
                raise AcademyCapacity("checkpoint retention budget exhausted")
            previous = latest.receipt.receipt_digest if latest is not None else _GENESIS
            revision = count + 1
            header = self._header(learner, revision, previous, digest, request)
            nonce = secrets.token_bytes(12)
            ciphertext = self._cipher.encrypt(nonce, raw, header)
            receipt = self._receipt(header, nonce, ciphertext)
            self._db.execute(
                f"INSERT INTO {_TABLE} VALUES (?,?,?,?,?,?,?,?,?)",
                (self._owner_id, learner, revision, previous, digest, request, nonce, ciphertext, receipt),
            )
            return AcademyReceipt(learner, revision, previous, digest, receipt)

    def close(self):
        self._require_owner()
        self._closed = True
