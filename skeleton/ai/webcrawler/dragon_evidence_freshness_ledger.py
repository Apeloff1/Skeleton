"""Independently signed freshness fencing for Jeeves retrieval weights.

A successful holdout and promotion does NOT imply eternal factual validity.
This append-only tenant-scoped, MAC-chained ledger binds the exact deployed
retrieval index and knowledge/source-set digests to a recent independent Wiki
review. Changed sources, revoked rights, expired receipts and tampering block
serving without altering neural parameters or bypassing approval workflows.
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac
import hashlib
import json
import re
import sqlite3
from threading import RLock

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from skeleton.ai.game_builder.contracts import canonical_json, canonical_digest

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_OWNER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:@-]{1,127}\Z")
_REASON = frozenset(("independent_review", "source_changed",
                     "source_superseded", "rights_revoked",
                     "contradiction", "review_expired", "operator_hold"))
_STATUS = frozenset(("fresh", "stale", "revoked"))
_ZERO = "0" * 64
_MAX_EVENTS = 256


def _digest(s: str) -> str:
    if type(s) is not str or not _HEX.fullmatch(s):
        raise ValueError("exact SHA-256 evidence digest required")
    return s


@dataclass(frozen=True)
class SignedKnowledgeFreshness:
    owner: str
    knowledge_digest: str
    source_set_digest: str
    index_digest: str
    status: str
    reason: str
    reviewer: str
    key_id: str
    reviewed_at: int
    expires_at: int
    signature_hex: str

    def body(self) -> dict:
        return {
            "schema": "skeleton.jeeves.signed_knowledge_freshness.v1",
            "owner": self.owner,
            "knowledge_digest": self.knowledge_digest,
            "source_set_digest": self.source_set_digest,
            "index_digest": self.index_digest,
            "status": self.status,
            "reason": self.reason,
            "reviewer": self.reviewer,
            "key_id": self.key_id,
            "reviewed_at": self.reviewed_at,
            "expires_at": self.expires_at,
        }


class DragonKnowledgeFreshnessLedger:
    """Separate reviewer authority, SQLite CAS and full genesis replay."""

    def __init__(self, db: sqlite3.Connection, *, owner: str,
                 signing_key: bytes, reviewer_public_key: bytes,
                 reviewer: str, key_id: str):
        if (not isinstance(db, sqlite3.Connection) or
            type(owner) is not str or not _OWNER.fullmatch(owner)
            or type(signing_key) is not bytes or len(signing_key) < 32
            or type(reviewer_public_key) is not bytes
            or len(reviewer_public_key) != 32
            or type(reviewer) is not str or not _OWNER.fullmatch(reviewer)
            or type(key_id) is not str or not _OWNER.fullmatch(key_id)):
            raise ValueError("operator-provisioned tenant and separate trust roots required")
        self.db, self.owner = db, owner
        self.key = signing_key
        self.reviewer_public_key = reviewer_public_key
        self.reviewer = reviewer
        self.key_id = key_id
        self._lock = RLock()
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_knowledge_freshness_v1(
            owner TEXT NOT NULL, knowledge_digest TEXT NOT NULL,
            sequence INTEGER NOT NULL, payload TEXT NOT NULL,
            signature_hex TEXT NOT NULL, previous_mac TEXT NOT NULL,
            event_mac TEXT NOT NULL,
            PRIMARY KEY(owner,knowledge_digest,sequence))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_knowledge_freshness_heads_v1(
            owner TEXT NOT NULL, knowledge_digest TEXT NOT NULL,
            sequence INTEGER NOT NULL, event_mac TEXT NOT NULL,
            PRIMARY KEY(owner,knowledge_digest))""")

    def _mac(self, knowledge: str, sequence: int,
             previous: str, payload: str, signature: str) -> str:
        material = canonical_json({
            "domain": "dragon-freshness-custody-v1",
            "owner": self.owner, "knowledge_digest": knowledge,
            "sequence": sequence, "previous_mac": previous,
            "payload": payload, "signature_hex": signature,
        })
        return hmac.new(self.key, material.encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def _validate(self, receipt: SignedKnowledgeFreshness) -> None:
        if not isinstance(receipt, SignedKnowledgeFreshness):
            raise TypeError("independently signed freshness receipt required")
        if (receipt.owner != self.owner or
            receipt.reviewer != self.reviewer or
            receipt.key_id != self.key_id or
            receipt.status not in _STATUS or
            receipt.reason not in _REASON or
            (receipt.status == "fresh") !=
                (receipt.reason == "independent_review") or
            type(receipt.reviewed_at) is not int or
            type(receipt.expires_at) is not int or
            not 0 <= receipt.reviewed_at < receipt.expires_at or
            receipt.expires_at - receipt.reviewed_at > 7 * 86400):
            raise PermissionError("independent knowledge freshness policy invalid")
        for v in (receipt.knowledge_digest, receipt.source_set_digest,
                  receipt.index_digest):
            _digest(v)
        try:
            signature = bytes.fromhex(receipt.signature_hex)
            if len(signature) != 64:
                raise ValueError("Ed25519 signature length invalid")
            Ed25519PublicKey.from_public_bytes(self.reviewer_public_key).verify(
                signature, canonical_json(receipt.body()).encode("utf-8"))
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise PermissionError("independent Wiki review signature invalid") from exc

    def _replay(self, knowledge_digest: str):
        _digest(knowledge_digest)
        rows = self.db.execute(
            "SELECT sequence,payload,signature_hex,previous_mac,event_mac "
            "FROM dragon_knowledge_freshness_v1 "
            "WHERE owner=? AND knowledge_digest=? ORDER BY sequence",
            (self.owner, knowledge_digest)).fetchall()
        if len(rows) > _MAX_EVENTS:
            raise ValueError("unbounded knowledge freshness history")
        previous = _ZERO
        latest = None
        for number, (seq, body, signature, prev, mac) in enumerate(rows, 1):
            if (type(seq) is not int or seq != number or
                prev != previous or type(body) is not str or
                not hmac.compare_digest(mac, self._mac(
                    knowledge_digest, seq, prev, body, signature))):
                raise ValueError("knowledge freshness journal corruption")
            try:
                decoded = json.loads(body)
                if canonical_json(decoded) != body:
                    raise ValueError("noncanonical freshness receipt")
                receipt = SignedKnowledgeFreshness(
                    **{k: v for k, v in decoded.items() if k != "schema"},
                    signature_hex=signature)
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError("invalid recorded knowledge receipt") from exc
            if decoded.get("schema") != "skeleton.jeeves.signed_knowledge_freshness.v1":
                raise ValueError("unknown freshness receipt schema")
            self._validate(receipt)
            if receipt.knowledge_digest != knowledge_digest:
                raise ValueError("knowledge receipt substituted across rows")
            if latest is not None:
                if receipt.reviewed_at <= latest.reviewed_at:
                    raise ValueError("nonmonotonic independent review timestamps")
                if latest.status == "revoked":
                    raise ValueError("revoked knowledge identity cannot be resurrected")
                if (latest.status == "stale" and receipt.status == "fresh" and
                    latest.source_set_digest == receipt.source_set_digest):
                    raise ValueError("stale evidence cannot be refreshed unchanged")
            latest = receipt
            previous = mac
        head = self.db.execute(
            "SELECT sequence,event_mac FROM dragon_knowledge_freshness_heads_v1 "
            "WHERE owner=? AND knowledge_digest=?",
            (self.owner, knowledge_digest)).fetchone()
        if (head is None and rows or head is not None and
            tuple(head) != (len(rows), previous)):
            raise ValueError("freshness ledger was truncated or head was forged")
        return len(rows), previous, latest

    def record(self, receipt: SignedKnowledgeFreshness, *, now: int,
               expected_revision: int, authorized: bool) -> dict:
        if authorized is not True:
            raise PermissionError("operator-side signed freshness custody required")
        self._validate(receipt)
        if (type(now) is not int or not receipt.reviewed_at <= now < receipt.expires_at
            or type(expected_revision) is not int or expected_revision < 0):
            raise PermissionError("future, expired or stale freshness write refused")
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                n, prev, old = self._replay(receipt.knowledge_digest)
                if n != expected_revision or n >= _MAX_EVENTS:
                    raise PermissionError("stale knowledge freshness generation")
                if old is not None:
                    if receipt.reviewed_at <= old.reviewed_at:
                        raise PermissionError("freshness review did not advance")
                    if old.status == "revoked":
                        raise PermissionError("revoked knowledge cannot reactivate")
                    if (old.status == "stale" and receipt.status == "fresh"
                        and old.source_set_digest == receipt.source_set_digest):
                        raise PermissionError("unchanged stale source set not renewed")
                body = canonical_json(receipt.body())
                mac = self._mac(receipt.knowledge_digest, n+1, prev,
                                body, receipt.signature_hex)
                self.db.execute(
                    "INSERT INTO dragon_knowledge_freshness_v1 VALUES(?,?,?,?,?,?,?)",
                    (self.owner, receipt.knowledge_digest,n+1,body,
                     receipt.signature_hex,prev,mac))
                self.db.execute(
                    "INSERT INTO dragon_knowledge_freshness_heads_v1 VALUES(?,?,?,?) "
                    "ON CONFLICT(owner,knowledge_digest) DO UPDATE SET "
                    "sequence=excluded.sequence,event_mac=excluded.event_mac",
                    (self.owner,receipt.knowledge_digest,n+1,mac))
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise
        return {"revision":n+1,"head_mac":mac,
                "freshness_status":receipt.status,"weights_modified":False}

    def state(self, knowledge_digest: str, *, now: int,
              index_digest: str, source_set_digest: str) -> dict:
        for v in (knowledge_digest, index_digest, source_set_digest):
            _digest(v)
        if type(now) is not int or now < 0:
            raise ValueError("bounded timestamp required")
        with self._lock:
            revision, mac, latest = self._replay(knowledge_digest)
        if latest is None:
            state = "unreviewed"
        elif latest.status == "revoked":
            state = "revoked"
        elif latest.status == "stale":
            state = "stale"
        elif now < latest.reviewed_at or now >= latest.expires_at:
            state = "expired_or_future"
        elif (latest.index_digest != index_digest or
              latest.source_set_digest != source_set_digest):
            state = "wrong_source_or_index"
        else:
            state = "fresh"
        return {
            "schema": "skeleton.jeeves.freshness_fence.v1",
            "owner": self.owner, "knowledge_digest":knowledge_digest,
            "index_digest": index_digest, "source_set_digest":source_set_digest,
            "revision":revision, "head_mac":mac, "state":state,
            "serve_permitted": state == "fresh",
            "read_only":True, "weights_modified":False,
            "independent_factual_truth_not_cryptographically_proved":True,
        }

    def require_current(self, knowledge_digest: str, *, now: int,
                        index_digest: str, source_set_digest: str) -> dict:
        result = self.state(knowledge_digest, now=now,
                            index_digest=index_digest,
                            source_set_digest=source_set_digest)
        if result["serve_permitted"] is not True:
            raise PermissionError("research evidence not current for this retrieval index: "
                                  + result["state"])
        return result
