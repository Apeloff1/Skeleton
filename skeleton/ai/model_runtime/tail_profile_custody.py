"""Authenticated append-only custody for offline inference timing profiles.

This store requires an independent durable generation/digest CAS anchor. SQLite
alone is NOT an anti-rollback fence, and a digest alone is NOT authentication.
No model text, weights, tokens, or provider credentials are persisted here.
"""
from __future__ import annotations

from hashlib import sha256
import hmac
import json
import sqlite3
from threading import RLock
from typing import Mapping, Protocol

from .tail_latency_profile import LocalTailProfiler, ProfileIdentity

SCHEMA = "skeleton.ai.tail-profile-durable.v1"
MAX_PAYLOAD_BYTES = 4 << 20
MAX_GENERATION = (1 << 63) - 1
TABLE = "local_tail_profile_custody"


class TailCustodyQuarantined(RuntimeError):
    """Tail profile storage or its independent rollback anchor is uncertain."""


class TailProfileAnchor(Protocol):
    """External durable monotonic CAS; MUST NOT share this SQLite database."""

    def initialize(self, *, generation: int, digest: str) -> None: ...

    def read(self) -> tuple[int, str]: ...

    def advance(
        self, *, expected_generation: int, expected_digest: str,
        generation: int, digest: str,
    ) -> None: ...


def _hex(value: object, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise ValueError("invalid " + label)
    return value


def _payload(value: Mapping[str, object]) -> bytes:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid tail profile checkpoint encoding") from exc
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError("tail profile exceeds durable byte budget")
    return encoded


def _digest(generation: int, payload: bytes) -> str:
    return sha256(
        b"skeleton.tail-profile-custody.v1\0"
        + generation.to_bytes(8, "big") + payload
    ).hexdigest()


def _mac(key: bytes, generation: int, digest: str) -> str:
    return hmac.new(
        key, b"skeleton.tail-profile-custody.mac.v1\0"
        + generation.to_bytes(8, "big") + digest.encode("ascii"),
        sha256,
    ).hexdigest()


def _identity(profile: LocalTailProfiler) -> dict[str, str]:
    return profile.identity.to_dict()


def _records(profile: LocalTailProfiler) -> dict[str, dict[str, object]]:
    checkpoint = profile.checkpoint()
    return {record["request_id"]: record for record in checkpoint["records"]}


class DurableTailProfileStore:
    """Single-writer append-only profile checkpoint with external CAS.

    The caller owns an exclusive, securely opened SQLite connection and a
    distinct trusted anchor. No API silently recreates lost checkpoints.
    """

    def __init__(
        self, connection: sqlite3.Connection, anchor: TailProfileAnchor,
        *, key: bytes, identity: ProfileIdentity,
    ) -> None:
        if not isinstance(connection, sqlite3.Connection) or connection.in_transaction:
            raise ValueError("idle exclusive SQLite connection required")
        if type(key) is not bytes or not 32 <= len(key) <= 128:
            raise ValueError("independent tail custody key required")
        if not isinstance(identity, ProfileIdentity):
            raise ValueError("canonical tail profile identity required")
        if not all(callable(getattr(anchor, name, None)) for name in (
            "initialize", "read", "advance",
        )):
            raise ValueError("independent monotonic anchor required")
        self._connection = connection
        self._anchor = anchor
        self._key = key
        self._identity = identity
        self._lock = RLock()
        self._quarantined = False
        connection.execute(
            "CREATE TABLE IF NOT EXISTS " + TABLE + " ("
            "singleton INTEGER PRIMARY KEY CHECK(singleton = 1),"
            "generation INTEGER NOT NULL CHECK(generation >= 0),"
            "digest TEXT NOT NULL,"
            "mac TEXT NOT NULL,"
            "payload BLOB NOT NULL"
            ")"
        )
        columns = tuple(row[1] for row in connection.execute(
            "PRAGMA table_info(" + TABLE + ")"
        ))
        if columns != ("singleton", "generation", "digest", "mac", "payload"):
            raise ValueError("untrusted tail custody schema")

    @property
    def quarantined(self) -> bool:
        return self._quarantined

    def _guard(self) -> None:
        if self._quarantined:
            raise TailCustodyQuarantined("tail custody quarantined")

    def _begin(self) -> None:
        if self._connection.in_transaction:
            raise TailCustodyQuarantined("tail custody connection has active transaction")
        self._connection.execute("BEGIN IMMEDIATE")

    def _row(self) -> tuple[object, ...] | None:
        return self._connection.execute(
            "SELECT generation, digest, mac, payload FROM "
            + TABLE + " WHERE singleton = 1"
        ).fetchone()

    def bootstrap(self) -> LocalTailProfiler:
        """Create a single empty profile and anchor; never reset a prior one."""
        with self._lock:
            self._guard()
            profile = LocalTailProfiler(self._identity)
            payload = _payload(profile.checkpoint())
            digest = _digest(0, payload)
            mac = _mac(self._key, 0, digest)
            try:
                self._begin()
                if self._row() is not None:
                    raise ValueError("tail custody already initialized")
                self._connection.execute(
                    "INSERT INTO " + TABLE
                    + " (singleton, generation, digest, mac, payload)"
                    + " VALUES (1, ?, ?, ?, ?)",
                    (0, digest, mac, payload),
                )
                self._connection.commit()
                self._anchor.initialize(generation=0, digest=digest)
                return profile
            except BaseException as exc:
                if self._connection.in_transaction:
                    self._connection.rollback()
                self._quarantined = True
                raise TailCustodyQuarantined(
                    "tail custody bootstrap requires explicit reconciliation"
                ) from exc

    def load(self) -> LocalTailProfiler:
        """Verify both independent CAS and authenticated checkpoint before use."""
        with self._lock:
            self._guard()
            try:
                generation, digest = self._anchor.read()
                if type(generation) is not int or not 0 <= generation <= MAX_GENERATION:
                    raise ValueError("invalid anchor generation")
                _hex(digest, "anchor digest")
                row = self._row()
                if row is None or type(row[0]) is not int or row[0] != generation:
                    raise ValueError("tail custody generation mismatch")
                if type(row[1]) is not str or not hmac.compare_digest(
                    _hex(row[1], "stored digest"), digest
                ):
                    raise ValueError("tail custody anchor mismatch")
                if type(row[2]) is not str or not hmac.compare_digest(
                    _hex(row[2], "stored MAC"), _mac(self._key, generation, digest)
                ):
                    raise ValueError("tail custody authentication failed")
                payload = row[3]
                if type(payload) is not bytes or len(payload) > MAX_PAYLOAD_BYTES:
                    raise ValueError("invalid stored tail profile payload")
                if not hmac.compare_digest(_digest(generation, payload), digest):
                    raise ValueError("tail custody payload digest mismatch")
                decoded = json.loads(payload)
                profile = LocalTailProfiler.restore(decoded)
                if _identity(profile) != self._identity.to_dict():
                    raise ValueError("tail profile identity changed")
                return profile
            except BaseException as exc:
                self._quarantined = True
                raise TailCustodyQuarantined(
                    "tail profile or independent anchor unverifiable"
                ) from exc

    def verified_snapshot(self) -> tuple[LocalTailProfiler, int, str]:
        """Return a profile and the same independently verified CAS version.

        Re-read the external anchor after profile authentication. If another
        writer advanced it concurrently, never report a mixed-generation
        status or claim that the earlier profile is current.
        """
        with self._lock:
            try:
                # A second writer can advance the independent anchor and
                # SQLite between load() and this method's final read.
                # Pin the version BEFORE loading and require it to remain
                # identical after the authenticated payload is decoded.
                before_generation, before_digest = self._anchor.read()
                profile = self.load()
                generation, digest = self._anchor.read()
                row = self._row()
                if (
                    type(before_generation) is not int
                    or type(before_digest) is not str
                    or generation != before_generation
                    or digest != before_digest
                    or type(generation) is not int
                    or not 0 <= generation <= MAX_GENERATION
                    or type(digest) is not str
                    or row is None
                    or row[0] != generation
                    or row[1] != _hex(digest, "anchor digest")
                    or row[2] != _mac(self._key, generation, digest)
                    or _digest(generation, row[3]) != digest
                ):
                    raise ValueError("tail profile changed during status read")
                return profile, generation, digest
            except BaseException as exc:
                self._quarantined = True
                raise TailCustodyQuarantined(
                    "tail profile status cannot be independently verified"
                ) from exc

    def persist(self, profile: LocalTailProfiler) -> tuple[int, str]:
        """Append observations, then advance external anchor; no silent eviction."""
        if not isinstance(profile, LocalTailProfiler):
            raise ValueError("canonical tail profile required")
        if _identity(profile) != self._identity.to_dict():
            raise ValueError("tail profile source identity mismatch")
        payload = _payload(profile.checkpoint())
        with self._lock:
            previous, old_generation, old_digest = self.verified_snapshot()
            old = _records(previous)
            new = _records(profile)
            if not old.keys() <= new.keys() or any(
                new[request_id] != record for request_id, record in old.items()
            ):
                raise ValueError("tail profile history cannot be deleted or rewritten")
            if len(new) == len(old):
                raise ValueError("no new tail observations to persist")
            # Reuse the authenticated version paired with the old profile.
            # A newer concurrent writer must fail the SQL CAS, never allow
            # an old profile to overwrite an independently advanced history.
            if old_generation >= MAX_GENERATION:
                raise TailCustodyQuarantined("tail generation exhausted")
            generation = old_generation + 1
            digest = _digest(generation, payload)
            mac = _mac(self._key, generation, digest)
            try:
                self._begin()
                changed = self._connection.execute(
                    "UPDATE " + TABLE
                    + " SET generation = ?, digest = ?, mac = ?, payload = ?"
                    + " WHERE singleton = 1 AND generation = ? AND digest = ?",
                    (generation, digest, mac, payload, old_generation, old_digest),
                ).rowcount
                if changed != 1:
                    raise ValueError("tail custody compare-and-swap conflict")
                self._connection.commit()
                # A failed external CAS leaves a mismatch on restart. Never
                # retry the write or accept this as a successful profile.
                self._anchor.advance(
                    expected_generation=old_generation,
                    expected_digest=old_digest,
                    generation=generation, digest=digest,
                )
                return generation, digest
            except BaseException as exc:
                if self._connection.in_transaction:
                    self._connection.rollback()
                self._quarantined = True
                raise TailCustodyQuarantined(
                    "tail custody publication requires explicit reconciliation"
                ) from exc


__all__ = [
    "DurableTailProfileStore", "TailCustodyQuarantined", "TailProfileAnchor",
]
