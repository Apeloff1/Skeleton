"""Durable, owner-scoped revision-review receipts with optimistic fencing.

Maintains an append-only hash chain of deterministic Crawl RevisionRevalidation
reports; does not ingest content, fetch URLs or auto-promote model knowledge.

The connection is caller-owned and should not be shared concurrently across
transactions. SQLite BEGIN IMMEDIATE fences competing writers on the same DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Mapping
import json
import sqlite3

from .dragon_crawl_revision import RevisionRevalidation, revision_report_fingerprint


_ZERO = "0" * 64


def _digest(value: object) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def _identifier(value: object, what: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise ValueError(f"invalid {what}")
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"invalid {what}")
    return value


@dataclass(frozen=True)
class RevisionEntry:
    owner: str
    claim_id: str
    sequence: int
    review_fingerprint: str
    prior_custody: str
    current_custody: str
    previous_hash: str
    event_hash: str
    observed_at: float
    reusable: bool
    invalidated_readings: int
    missing_sources: tuple[str, ...]
    added_sources: tuple[str, ...]


class RevisionJournal:
    """Append-only custody review history with integrity and replay checks."""

    def __init__(self, connection: sqlite3.Connection, *, max_per_claim: int = 100000):
        if not isinstance(max_per_claim, int) or isinstance(max_per_claim, bool) or not (
            1 <= max_per_claim <= 1000000
        ):
            raise ValueError("invalid journal capacity")
        self.db = connection
        self.max_per_claim = max_per_claim
        self.db.execute("""
          CREATE TABLE IF NOT EXISTS crawler_revision_events (
            owner TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            review_fingerprint TEXT NOT NULL,
            prior_custody TEXT NOT NULL,
            current_custody TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            observed_at REAL NOT NULL,
            reusable INTEGER NOT NULL,
            invalidated_readings INTEGER NOT NULL,
            missing_sources TEXT NOT NULL,
            added_sources TEXT NOT NULL,
            PRIMARY KEY(owner, claim_id, sequence)
          )
        """)
        self.db.execute("""
          CREATE TABLE IF NOT EXISTS crawler_revision_heads (
            owner TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            event_hash TEXT NOT NULL,
            PRIMARY KEY(owner, claim_id)
          )
        """)
        self.db.commit()

    @staticmethod
    def _receipt_hash(entry: RevisionEntry) -> str:
        return _digest([
            "skeleton.crawler.revision_journal.v1",
            entry.owner, entry.claim_id, entry.sequence,
            entry.review_fingerprint, entry.prior_custody, entry.current_custody,
            entry.previous_hash, entry.observed_at,
            entry.reusable, entry.invalidated_readings,
            entry.missing_sources, entry.added_sources,
        ])

    @staticmethod
    def _make_entry(
        owner: str, review: RevisionRevalidation, *,
        sequence: int, previous_hash: str, observed_at: float,
    ) -> RevisionEntry:
        entry = RevisionEntry(
            owner, review.claim_id, sequence, review.fingerprint,
            review.original_custody_fingerprint,
            review.current_custody_fingerprint, previous_hash,
            "", observed_at, review.prior_readings_reusable,
            review.invalidated_readings,
            tuple(review.missing_sources), tuple(review.added_sources),
        )
        from dataclasses import replace
        return replace(entry, event_hash=RevisionJournal._receipt_hash(entry))

    @staticmethod
    def _from_row(owner: str, claim_id: str, row: tuple) -> RevisionEntry:
        (seq, review_fp, prior, current, previous_hash, event_hash, timestamp,
         reuse, invalidated, missing_json, added_json) = row
        return RevisionEntry(
            owner, claim_id, seq, review_fp, prior, current, previous_hash,
            event_hash, timestamp, bool(reuse), invalidated,
            tuple(json.loads(missing_json)), tuple(json.loads(added_json)),
        )

    def _latest_unchecked(self, owner: str, claim_id: str) -> RevisionEntry | None:
        row = self.db.execute("""
          SELECT sequence,review_fingerprint,prior_custody,current_custody,
                 previous_hash,event_hash,observed_at,reusable,
                 invalidated_readings,missing_sources,added_sources
          FROM crawler_revision_events
          WHERE owner=? AND claim_id=?
          ORDER BY sequence DESC LIMIT 1
        """, (owner, claim_id)).fetchone()
        return self._from_row(owner, claim_id, row) if row else None

    @staticmethod
    def _validate_review(review: RevisionRevalidation) -> None:
        if not isinstance(review, RevisionRevalidation):
            raise ValueError("revision revalidation report required")
        _identifier(review.claim_id, "claim id")
        for field in (
            review.fingerprint, review.original_custody_fingerprint,
            review.current_custody_fingerprint,
        ):
            if not _valid_digest(field):
                raise ValueError("invalid review fingerprint")
        if not isinstance(review.prior_readings_reusable, bool):
            raise ValueError("invalid reuse decision")
        if not isinstance(review.invalidated_readings, int) or isinstance(
            review.invalidated_readings, bool
        ) or review.invalidated_readings < 0:
            raise ValueError("invalid invalidation count")
        for values in (review.missing_sources, review.added_sources):
            if not isinstance(values, tuple) or len(values) > 100000:
                raise ValueError("invalid source dispositions")
            for value in values:
                _identifier(value, "source identity")
            if len(values) != len(set(values)):
                raise ValueError("duplicate source dispositions")
        if set(review.missing_sources) & set(review.added_sources):
            raise ValueError("incompatible source dispositions")
        if review.prior_readings_reusable and (
            review.invalidated_readings or review.missing_sources or review.added_sources
        ):
            raise ValueError("inconsistent revalidation decision")
        if review.fingerprint != revision_report_fingerprint(review):
            raise ValueError("revision review fingerprint mismatch")

    def append(
        self, owner: str, review: RevisionRevalidation, *,
        observed_at: float, expected_sequence: int, authorized: bool,
    ) -> RevisionEntry:
        if not authorized:
            raise PermissionError("revision journal append requires authorization")
        _identifier(owner, "owner")
        self._validate_review(review)
        if not isinstance(observed_at, (int, float)) or isinstance(
            observed_at, bool
        ) or not isfinite(observed_at) or observed_at < 0:
            raise ValueError("invalid journal timestamp")
        if not isinstance(expected_sequence, int) or isinstance(
            expected_sequence, bool
        ) or expected_sequence < 0:
            raise ValueError("invalid expected revision")
        if self.db.in_transaction:
            raise RuntimeError("journal cannot write within an existing transaction")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            latest = self._latest_unchecked(owner, review.claim_id)
            current = latest.sequence if latest else 0
            head = self.db.execute("""
              SELECT sequence,event_hash FROM crawler_revision_heads
              WHERE owner=? AND claim_id=?
            """, (owner, review.claim_id)).fetchone()
            if (head is None) != (latest is None) or (
                latest is not None and head != (latest.sequence, latest.event_hash)
            ):
                raise RuntimeError("revision journal head mismatch")
            if latest and observed_at < latest.observed_at:
                raise ValueError("journal time cannot move backwards")
            if latest and latest.sequence == expected_sequence + 1:
                # Network retry after a successful acknowledged commit.
                # A replay with different timestamp or report is a conflict.
                if (
                    latest.review_fingerprint == review.fingerprint
                    and latest.prior_custody == review.original_custody_fingerprint
                    and latest.current_custody == review.current_custody_fingerprint
                    and latest.observed_at == observed_at
                ):
                    if latest.event_hash != self._receipt_hash(latest):
                        raise RuntimeError("tampered journal head")
                    self.db.execute("COMMIT")
                    return latest
            if current != expected_sequence:
                raise RuntimeError("stale revision journal sequence")
            if current >= self.max_per_claim:
                raise ValueError("revision journal capacity exceeded")
            previous = latest.event_hash if latest else _ZERO
            if latest and latest.event_hash != self._receipt_hash(latest):
                raise RuntimeError("tampered journal head")
            entry = self._make_entry(
                owner, review, sequence=current + 1,
                previous_hash=previous, observed_at=float(observed_at),
            )
            self.db.execute("""
              INSERT INTO crawler_revision_events(
                owner,claim_id,sequence,review_fingerprint,prior_custody,
                current_custody,previous_hash,event_hash,observed_at,reusable,
                invalidated_readings,missing_sources,added_sources
              ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                owner, review.claim_id, entry.sequence, entry.review_fingerprint,
                entry.prior_custody, entry.current_custody,
                entry.previous_hash, entry.event_hash, entry.observed_at,
                int(entry.reusable), entry.invalidated_readings,
                json.dumps(entry.missing_sources),
                json.dumps(entry.added_sources),
            ))
            self.db.execute("""
              INSERT INTO crawler_revision_heads(owner,claim_id,sequence,event_hash)
              VALUES(?,?,?,?)
              ON CONFLICT(owner,claim_id) DO UPDATE SET
                sequence=excluded.sequence,event_hash=excluded.event_hash
            """, (owner, review.claim_id, entry.sequence, entry.event_hash))
            self.db.execute("COMMIT")
            return entry
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def latest(self, owner: str, claim_id: str, *, authorized: bool) -> RevisionEntry | None:
        if not authorized:
            raise PermissionError("revision journal read requires authorization")
        _identifier(owner, "owner")
        _identifier(claim_id, "claim id")
        return self._latest_unchecked(owner, claim_id)

    def entries(
        self, owner: str, claim_id: str, *,
        authorized: bool, limit: int = 1000,
    ) -> tuple[RevisionEntry, ...]:
        if not authorized:
            raise PermissionError("revision journal read requires authorization")
        _identifier(owner, "owner")
        _identifier(claim_id, "claim id")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10000:
            raise ValueError("invalid query budget")
        rows = self.db.execute("""
          SELECT sequence,review_fingerprint,prior_custody,current_custody,
                 previous_hash,event_hash,observed_at,reusable,
                 invalidated_readings,missing_sources,added_sources
          FROM crawler_revision_events WHERE owner=? AND claim_id=?
          ORDER BY sequence DESC LIMIT ?
        """, (owner, claim_id, limit)).fetchall()
        return tuple(self._from_row(owner, claim_id, row) for row in rows)

    def verify(self, owner: str, claim_id: str, *,
               authorized: bool, max_events: int = 100000) -> bool:
        if not authorized:
            raise PermissionError("revision journal verification requires authorization")
        _identifier(owner, "owner")
        _identifier(claim_id, "claim id")
        if not isinstance(max_events, int) or isinstance(
            max_events, bool
        ) or not 1 <= max_events <= 1000000:
            raise ValueError("invalid verification limit")
        rows = self.db.execute("""
          SELECT sequence,review_fingerprint,prior_custody,current_custody,
                 previous_hash,event_hash,observed_at,reusable,
                 invalidated_readings,missing_sources,added_sources
          FROM crawler_revision_events WHERE owner=? AND claim_id=?
          ORDER BY sequence LIMIT ?
        """, (owner, claim_id, max_events + 1)).fetchall()
        if len(rows) > max_events:
            raise ValueError("revision verification budget exceeded")
        previous = _ZERO
        for sequence, row in enumerate(rows, 1):
            try:
                entry = self._from_row(owner, claim_id, row)
                valid = (
                    entry.sequence == sequence
                    and entry.previous_hash == previous
                    and _valid_digest(entry.event_hash)
                    and entry.event_hash == self._receipt_hash(entry)
                )
            except (TypeError, ValueError, OverflowError, KeyError):
                return False
            if not valid:
                return False
            previous = entry.event_hash
        head = self.db.execute("""
          SELECT sequence,event_hash FROM crawler_revision_heads
          WHERE owner=? AND claim_id=?
        """, (owner, claim_id)).fetchone()
        return (
            (head is None and not rows)
            or bool(head and rows and head == (len(rows), previous))
        )

    def erase(self, owner: str, *, authorized: bool) -> int:
        if not authorized:
            raise PermissionError("revision journal erasure requires authorization")
        _identifier(owner, "owner")
        with self.db:
            count = self.db.execute(
                "DELETE FROM crawler_revision_events WHERE owner=?",
                (owner,),
            ).rowcount
            self.db.execute(
                "DELETE FROM crawler_revision_heads WHERE owner=?",
                (owner,),
            )
        return count
