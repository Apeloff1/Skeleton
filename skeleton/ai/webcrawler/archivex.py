"""ArchiveX: bounded, content-addressed research evidence archive.

This is a local archival index, not a remote archival service. Snapshot bodies
are provided by an authorized caller; no fetching, scraping or bypassing access
controls occurs here. Digests bind immutable source metadata to bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Iterable
import json
import sqlite3

from .dragon_video_history import canonical_video_url


@dataclass(frozen=True)
class ArchiveXPolicy:
    max_snapshot_bytes: int = 1_000_000
    max_snapshots_per_owner: int = 10000
    max_batch: int = 32
    max_age_seconds: float = 10 * 365 * 86400


@dataclass(frozen=True)
class ArchiveXSnapshot:
    owner: str
    snapshot_id: str
    source_url: str
    observed_at: float
    content_digest: str
    content_length: int
    media_type: str
    license_note: str


class ArchiveX:
    def __init__(self, db: sqlite3.Connection, *,
                 policy: ArchiveXPolicy = ArchiveXPolicy()):
        if not 1 <= policy.max_snapshot_bytes <= 50_000_000:
            raise ValueError("invalid snapshot budget")
        if not 1 <= policy.max_snapshots_per_owner <= 1_000_000:
            raise ValueError("invalid archive capacity")
        if not 1 <= policy.max_batch <= 1000:
            raise ValueError("invalid batch capacity")
        if not isfinite(policy.max_age_seconds) or policy.max_age_seconds <= 0:
            raise ValueError("invalid archive retention")
        self.db = db
        self.policy = policy
        db.execute("""
            CREATE TABLE IF NOT EXISTS archivex_snapshots (
                owner TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                source_url TEXT NOT NULL,
                observed_at REAL NOT NULL,
                content_digest TEXT NOT NULL,
                content_length INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                license_note TEXT NOT NULL,
                body BLOB NOT NULL,
                PRIMARY KEY (owner, snapshot_id)
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS archivex_source_time
            ON archivex_snapshots(owner, source_url, observed_at)
        """)
        db.commit()

    @staticmethod
    def _owner(owner: str) -> str:
        if not isinstance(owner, str) or not owner or len(owner) > 128:
            raise ValueError("invalid archive owner")
        return owner

    @staticmethod
    def _identity(source_url: str, observed_at: float, digest: str) -> str:
        # SQLite REAL round-trips integer epoch seconds as floating-point.
        # Keep snapshot IDs invariant between initial capture and DB reads,
        # without weakening byte/digest/identity verification.
        if not isinstance(observed_at, (int, float)) or isinstance(observed_at, bool) or not isfinite(observed_at):
            raise ValueError("invalid archival observation timestamp")
        normalized_at = float(observed_at)
        canonical = json.dumps(
            [source_url, normalized_at, digest],
            separators=(",", ":"), ensure_ascii=True, allow_nan=False,
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _legacy_integer_identity(source_url: str, observed_at: float, digest: str) -> str | None:
        # Older snapshots accepted integer timestamps but SQLite persisted
        # them as REAL. Match only that historically exact encoding.
        if not isfinite(observed_at) or not float(observed_at).is_integer():
            return None
        canonical = json.dumps(
            [source_url, int(observed_at), digest],
            separators=(",", ":"), ensure_ascii=True, allow_nan=False,
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    def capture(self, owner: str, *, source_url: str, body: bytes,
                observed_at: float, now: float, media_type: str = "text/plain",
                license_note: str, authorized: bool) -> ArchiveXSnapshot:
        owner = self._owner(owner)
        if not authorized:
            raise PermissionError("archival capture requires authorization")
        if not isinstance(body, bytes) or not 0 < len(body) <= self.policy.max_snapshot_bytes:
            raise ValueError("invalid snapshot body")
        if not isfinite(now) or not isfinite(observed_at):
            raise ValueError("invalid archive clock")
        if observed_at > now or now - observed_at > self.policy.max_age_seconds:
            raise ValueError("snapshot outside retention window")
        if not isinstance(media_type, str) or not 1 <= len(media_type) <= 128:
            raise ValueError("invalid media type")
        if not isinstance(license_note, str) or not 1 <= len(license_note) <= 256:
            raise ValueError("license provenance is required")
        source_url = canonical_video_url(source_url)
        digest = sha256(body).hexdigest()
        snapshot_id = self._identity(source_url, observed_at, digest)
        with self.db:
            count = self.db.execute(
                "SELECT COUNT(*) FROM archivex_snapshots WHERE owner=?",
                (owner,),
            ).fetchone()[0]
            existing = self.db.execute("""
                SELECT 1 FROM archivex_snapshots WHERE owner=? AND snapshot_id=?
            """, (owner, snapshot_id)).fetchone()
            if not existing and count >= self.policy.max_snapshots_per_owner:
                raise ValueError("archive capacity exceeded")
            self.db.execute("""
                INSERT OR IGNORE INTO archivex_snapshots
                (owner, snapshot_id, source_url, observed_at, content_digest,
                 content_length, media_type, license_note, body)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (owner, snapshot_id, source_url, observed_at, digest,
                  len(body), media_type, license_note, body))
        return ArchiveXSnapshot(owner, snapshot_id, source_url, observed_at,
                                digest, len(body), media_type, license_note)

    def read(self, owner: str, snapshot_id: str, *,
             authorized: bool) -> tuple[ArchiveXSnapshot, bytes] | None:
        owner = self._owner(owner)
        if not authorized:
            raise PermissionError("archive access requires authorization")
        row = self.db.execute("""
            SELECT source_url, observed_at, content_digest, content_length,
                   media_type, license_note, body
            FROM archivex_snapshots WHERE owner=? AND snapshot_id=?
        """, (owner, snapshot_id)).fetchone()
        if row is None:
            return None
        source, observed, digest, length, media, license_note, body = row
        identities = {self._identity(source, observed, digest)}
        legacy = self._legacy_integer_identity(source, observed, digest)
        if legacy is not None:
            identities.add(legacy)
        if (len(body) != length or sha256(body).hexdigest() != digest or
                snapshot_id not in identities):
            raise ValueError("archive integrity violation")
        return ArchiveXSnapshot(owner, snapshot_id, source, observed,
                                digest, length, media, license_note), body

    def timeline(self, owner: str, source_url: str, *,
                 authorized: bool, limit: int = 100) -> tuple[ArchiveXSnapshot, ...]:
        owner = self._owner(owner)
        if not authorized:
            raise PermissionError("archive timeline requires authorization")
        if not 1 <= limit <= 1000:
            raise ValueError("invalid timeline limit")
        source = canonical_video_url(source_url)
        rows = self.db.execute("""
            SELECT snapshot_id FROM archivex_snapshots
            WHERE owner=? AND source_url=?
            ORDER BY observed_at DESC, snapshot_id LIMIT ?
        """, (owner, source, limit)).fetchall()
        return tuple(self.read(owner, row[0], authorized=True)[0] for row in rows)

    def prune(self, owner: str, *, now: float) -> int:
        owner = self._owner(owner)
        if not isfinite(now):
            raise ValueError("invalid clock")
        with self.db:
            cursor = self.db.execute("""
                DELETE FROM archivex_snapshots WHERE owner=? AND observed_at<?
            """, (owner, now - self.policy.max_age_seconds))
            return cursor.rowcount

    def erase(self, owner: str) -> int:
        """Erase archive bytes and known dependent owner-scoped records.

        Legacy installations may not have every downstream table. Query the
        schema first rather than creating optional stores during erasure.
        """
        owner = self._owner(owner)
        dependent = (
            "archivex_dependencies",
            "archivex_evidence_anchors",
            "archivex_knowledge",
            "archivex_promotions",
            "archivex_research_signals",
        )
        with self.db:
            existing = {
                row[0] for row in self.db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            for table in dependent:
                if table in existing:
                    self.db.execute(
                        "DELETE FROM " + table + " WHERE owner=?", (owner,)
                    )
            cursor = self.db.execute(
                "DELETE FROM archivex_snapshots WHERE owner=?", (owner,))
            return cursor.rowcount
