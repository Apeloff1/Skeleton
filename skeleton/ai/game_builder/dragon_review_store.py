"""Owner-bound, authenticated advisory snapshots for the companion boundary.

Only a trusted forge worker publishes typed completed reviews. There is no
browser write API. A MAC protects persisted snapshots; it does not certify
their legal or empirical truth. Expired snapshots disappear from the product.
"""
from __future__ import annotations

import hmac
import json
import sqlite3
from hashlib import sha256

from .contracts import canonical_digest
from .dragon_wisdom import SquareReview


class DragonReviewStore:
    def __init__(self, db: sqlite3.Connection, *, signing_key: bytes):
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("dedicated review signing key required")
        self.db, self.key = db, signing_key
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_wisdom_snapshots (
            owner TEXT NOT NULL, review_digest TEXT NOT NULL,
            issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
            body TEXT NOT NULL, signature TEXT NOT NULL,
            PRIMARY KEY(owner, review_digest))""")

    @staticmethod
    def _scope(owner: str, now: int) -> None:
        if not isinstance(owner, str) or not owner.strip() or owner != owner.strip() or len(owner) > 192:
            raise ValueError("bounded authenticated owner required")
        if type(now) is not int or now < 0:
            raise ValueError("explicit integer snapshot time required")

    def _signature(self, body: str) -> str:
        return hmac.new(self.key, body.encode(), sha256).hexdigest()

    def publish(self, owner: str, review: SquareReview, *, now: int,
                expires_at: int, trusted_worker: bool) -> str:
        self._scope(owner, now)
        if trusted_worker is not True:
            raise PermissionError("review publication requires the trusted forge worker")
        if not isinstance(review, SquareReview) or not review.terminal or review.completed_rounds != review.planned_rounds or review.planned_rounds not in (100, 1000, 10000):
            raise ValueError("only completed refinement reviews may be published")
        if type(expires_at) is not int or not now < expires_at <= now + 86400:
            raise ValueError("snapshot expires within one day; policy may require earlier expiry")
        payload = review.to_payload()
        envelope = {"owner": owner, "issued_at": now, "expires_at": expires_at, "review": payload}
        body = json.dumps(envelope, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(body.encode()) > 256000:
            raise ValueError("bounded companion snapshot required")
        signature = self._signature(body)
        with self.db:
            existing = self.db.execute("SELECT body,signature FROM dragon_wisdom_snapshots WHERE owner=? AND review_digest=?",
                (owner, payload["review_digest"])).fetchone()
            if existing:
                if existing != (body, signature):
                    raise ValueError("snapshot identity cannot be rewritten")
                return payload["review_digest"]
            self.db.execute("DELETE FROM dragon_wisdom_snapshots WHERE owner=? AND expires_at<=?", (owner, now))
            count = self.db.execute("SELECT COUNT(*) FROM dragon_wisdom_snapshots WHERE owner=?", (owner,)).fetchone()[0]
            if count >= 1000:
                raise ValueError("companion snapshot retention budget exceeded")
            self.db.execute("INSERT INTO dragon_wisdom_snapshots VALUES (?,?,?,?,?,?)",
                (owner, payload["review_digest"], now, expires_at, body, signature))
        return payload["review_digest"]

    def latest(self, owner: str, *, now: int, authorized: bool) -> dict | None:
        self._scope(owner, now)
        if authorized is not True:
            raise PermissionError("private companion snapshot requires authentication")
        row = self.db.execute("""SELECT review_digest,issued_at,expires_at,body,signature
            FROM dragon_wisdom_snapshots WHERE owner=?
            ORDER BY issued_at DESC, rowid DESC LIMIT 1""", (owner,)).fetchone()
        if row is None:
            return None
        digest, issued, expires, body, signature = row
        if not hmac.compare_digest(self._signature(body), signature):
            raise ValueError("companion snapshot integrity check failed")
        envelope = json.loads(body)
        payload = envelope["review"]
        if (envelope["owner"], envelope["issued_at"], envelope["expires_at"]) != (owner, issued, expires):
            raise ValueError("companion snapshot scope was rebound")
        if payload.get("review_digest") != digest or canonical_digest({k: v for k, v in payload.items() if k != "review_digest"}) != digest:
            raise ValueError("companion review digest mismatch")
        if not issued <= now < expires:
            return None
        return {"review": payload, "issued_at": issued, "expires_at": expires}
