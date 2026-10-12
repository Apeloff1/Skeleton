"""Durable, per-owner Jeeves retrieval-weight generations.

Operator-owned SQLite and a separately provisioned HMAC secret are required.
An activation invokes the EXISTING independently signed 100-matrix,
cross-source, holdout and operator checks inside a transaction BEFORE any
new ledger event is committed. The journal is replayed from genesis on reads;
no user-provided snapshot may restore or approve neural/model weights.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import sqlite3
from threading import RLock

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from skeleton.ai.game_builder.contracts import canonical_json, canonical_digest
from .dragon_weight_tier_sandbox import JeevesWeightOverlay, WORD

ZERO = "0" * 64
HEX = re.compile(r"[0-9a-f]{64}\Z")
MAX_EVENTS = 512
MAX_ENTRIES = 512


@dataclass(frozen=True)
class SignedRollbackOrder:
    owner: str
    expected_generation: int
    current_digest: str
    restore_digest: str
    operator: str
    key_id: str
    issued_at: int
    expires_at: int
    reason_digest: str
    signature_hex: str

    def body(self) -> dict:
        return {
            "schema": "skeleton.jeeves.weight_rollback_order.v1",
            "owner": self.owner,
            "expected_generation": self.expected_generation,
            "current_digest": self.current_digest,
            "restore_digest": self.restore_digest,
            "operator": self.operator,
            "key_id": self.key_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "reason_digest": self.reason_digest,
        }


class DragonDurableWeightVault:
    """Signed activation, SQLite CAS, hash-chained replay and rollback."""

    def __init__(self, db: sqlite3.Connection, *, owner: str, signing_key: bytes):
        if (not isinstance(db, sqlite3.Connection)
            or type(owner) is not str or not 1 <= len(owner) <= 128
            or any(c in owner for c in "\r\n/\\")
            or type(signing_key) is not bytes or len(signing_key) < 32):
            raise ValueError("operator-controlled owner and custody key required")
        self.db = db
        self.owner = owner
        self.key = signing_key
        self._lock = RLock()
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_weight_vault_events_v1(
            owner TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            payload TEXT NOT NULL,
            digest TEXT NOT NULL,
            previous_digest TEXT NOT NULL,
            event_mac TEXT NOT NULL,
            PRIMARY KEY(owner,sequence))""")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_weight_vault_heads_v1(
            owner TEXT PRIMARY KEY,
            sequence INTEGER NOT NULL,
            digest TEXT NOT NULL,
            head_mac TEXT NOT NULL)""")

    def _mac(self, *, domain: str, payload: dict) -> str:
        return hmac.new(self.key, (domain + ":" + canonical_json(payload)).encode(),
                        hashlib.sha256).hexdigest()

    def _verify(self) -> tuple[int, str, list[tuple[str, tuple[str, ...]]], list[dict]]:
        rows = self.db.execute(
            "SELECT sequence,payload,digest,previous_digest,event_mac "
            "FROM dragon_weight_vault_events_v1 WHERE owner=? ORDER BY sequence",
            (self.owner,)).fetchall()
        if len(rows) > MAX_EVENTS:
            raise ValueError("weight-vault event capacity exceeded")
        current = ZERO
        items = []
        events = []
        for expected, (seq, raw, digest, previous, mac) in enumerate(rows, 1):
            try:
                event = json.loads(raw)
            except (ValueError, TypeError) as exc:
                raise ValueError("weight-vault event JSON corrupted") from exc
            if (type(seq) is not int or seq != expected
                or type(event) is not dict or canonical_json(event) != raw
                or canonical_digest(event) != digest
                or previous != current
                or event.get("owner") != self.owner
                or event.get("generation") != seq
                or event.get("previous_digest") != (
                    events[-1]["index_digest"] if events else ZERO)
                or not hmac.compare_digest(mac, self._mac(
                    domain="event", payload={
                        "owner": self.owner, "sequence": seq, "digest": digest,
                        "previous": previous,
                    }))):
                raise ValueError("weight-vault custody chain invalid")
            if event.get("action") not in ("activate", "rollback"):
                raise ValueError("unknown weight-vault event")
            entries = event.get("entries")
            if (not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ENTRIES
                or any(not isinstance(x, list) or len(x) != 2
                       or type(x[0]) is not str or not HEX.fullmatch(x[0])
                       or not isinstance(x[1], list)
                       or not 1 <= len(x[1]) <= 64
                       or any(type(term) is not str or not WORD.fullmatch(term)
                              for term in x[1])
                       or len(x[1]) != len(set(x[1]))
                       for x in entries)
                or len(entries) != len({x[0] for x in entries})
                or sum(len(x[1]) for x in entries) > 4096
                or canonical_digest(entries) != event.get("index_digest")):
                raise ValueError("durable retrieval index inconsistent with custody")
            if event["action"] == "activate":
                if (event.get("tier") not in ("shadow_to_weight", "weight_to_hyper")
                    or not HEX.fullmatch(event.get("holdout_digest", ""))
                    or not HEX.fullmatch(event.get("approval_digest", ""))
                    or not HEX.fullmatch(event.get("matrix_digest", ""))):
                    raise ValueError("durable activation evidence missing")
            else:
                if (event.get("tier") != "rollback"
                    or not HEX.fullmatch(event.get("rollback_order_digest", ""))):
                    raise ValueError("durable rollback evidence missing")
            items = [(x[0], tuple(x[1])) for x in entries]
            current = digest
            events.append(event)
        head = self.db.execute(
            "SELECT sequence,digest,head_mac FROM dragon_weight_vault_heads_v1 "
            "WHERE owner=?", (self.owner,)).fetchone()
        sequence = len(rows)
        expected_head = self._mac(domain="head", payload={
            "owner": self.owner, "sequence": sequence, "digest": current,
        })
        if (head is None and sequence
            or head is not None and (
                head[0] != sequence or head[1] != current
                or not hmac.compare_digest(head[2], expected_head))):
            raise ValueError("weight-vault head missing or corrupt")
        return sequence, current, items, events

    def _append(self, *, event: dict, seq: int, previous_event_digest: str):
        raw = canonical_json(event)
        digest = canonical_digest(event)
        mac = self._mac(domain="event", payload={
            "owner": self.owner, "sequence": seq, "digest": digest,
            "previous": previous_event_digest,
        })
        self.db.execute(
            "INSERT INTO dragon_weight_vault_events_v1 VALUES(?,?,?,?,?,?)",
            (self.owner, seq, raw, digest, previous_event_digest, mac))
        head = self._mac(domain="head", payload={
            "owner": self.owner, "sequence": seq, "digest": digest,
        })
        self.db.execute(
            "INSERT INTO dragon_weight_vault_heads_v1 VALUES(?,?,?,?) "
            "ON CONFLICT(owner) DO UPDATE SET sequence=excluded.sequence,"
            "digest=excluded.digest,head_mac=excluded.head_mac",
            (self.owner, seq, digest, head))
        return digest

    def publish(self, *, entries: tuple[tuple[str, tuple[str, ...]], ...],
                activation_kwargs: dict, expected_generation: int) -> dict:
        """Commit only after full existing Jeeves promotion validation passes."""
        if type(activation_kwargs) is not dict or type(expected_generation) is not int:
            raise TypeError("immutable external approval inputs required")
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                seq, chain_head, active, events = self._verify()
                if seq != expected_generation or seq >= MAX_EVENTS:
                    raise PermissionError("stale weight-vault generation or capacity")
                overlay = JeevesWeightOverlay(self.owner)
                # Restore *only* an HMAC-verified application retrieval index.
                # The original .activate() still verifies all external receipts.
                overlay._generation = seq
                overlay._active = tuple(active)
                overlay._active_digest = (events[-1]["index_digest"]
                                          if events else ZERO)
                overlay._postings = self._postings(active)
                outcome = overlay.activate(
                    entries=entries, expected_generation=seq,
                    **activation_kwargs)
                approval = activation_kwargs["approval"]
                eval_ = activation_kwargs["evaluation"]
                now = activation_kwargs["now"]
                # Serving authorization is bounded; a now-expired approval
                # cannot remain active across a service restart.
                expires = min(approval.expires_at, eval_.expires_at)
                if type(now) is not int or expires <= now:
                    raise PermissionError("expired live routing evidence")
                event = {
                    "schema": "skeleton.jeeves.weight_vault_event.v1",
                    "owner": self.owner, "generation": seq + 1,
                    "action": "activate",
                    "tier": approval.tier,
                    "previous_digest": (events[-1]["index_digest"]
                                        if events else ZERO),
                    "index_digest": outcome["index_digest"],
                    "entries": [[identity, list(words)] for identity, words in entries],
                    "holdout_digest": activation_kwargs["verdict"]["verdict_digest"],
                    "matrix_digest": eval_.matrix_report_digest,
                    "approval_digest": canonical_digest(approval.body()),
                    "expires_at": expires, "observed_at": now,
                }
                event_digest = self._append(
                    event=event, seq=seq+1, previous_event_digest=chain_head)
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise
        return {"generation": seq+1, "index_digest": outcome["index_digest"],
                "custody_digest": event_digest, "entries": len(entries),
                "durably_committed": True, "neural_weights_changed": False}

    @staticmethod
    def _postings(entries):
        result = {}
        for ident, words in entries:
            for word in words:
                result.setdefault(word, []).append(ident)
        return {term: tuple(sorted(ids)) for term, ids in result.items()}

    def route(self, query: str, *, limit: int = 5, now: int) -> dict:
        """Read-time HMAC replay prevents stale or tampered deployment use."""
        if (type(query) is not str or len(query) > 600
            or type(limit) is not int or not 1 <= limit <= 20
            or type(now) is not int or now < 0):
            raise ValueError("bounded routed query and timestamp required")
        with self._lock:
            seq, _, active, events = self._verify()
            if not events or now >= events[-1]["expires_at"]:
                return {"generation": seq, "bookmarked_retrieval_ids": [],
                        "inactive_reason": "absent_or_expired",
                        "read_only": True, "neural_weights_changed": False}
            postings = self._postings(active)
        scores = {}
        for word in set(WORD.findall(query.casefold())):
            for identity in postings.get(word, ()):
                scores[identity] = scores.get(identity, 0) + 1
        ranked = sorted(scores, key=lambda x: (-scores[x], x))
        return {"generation": seq, "bookmarked_retrieval_ids": ranked[:limit],
                "index_digest": events[-1]["index_digest"],
                "read_only": True, "neural_weights_changed": False}

    def rollback(self, order: SignedRollbackOrder, *, public_key: bytes,
                 operator: str, key_id: str, now: int) -> dict:
        if not isinstance(order, SignedRollbackOrder):
            raise TypeError("separate signed operator rollback required")
        if (type(public_key) is not bytes or len(public_key) != 32
            or order.owner != self.owner or order.operator != operator
            or order.key_id != key_id or type(now) is not int
            or not order.issued_at <= now < order.expires_at
            or order.expires_at-order.issued_at > 3600
            or any(type(x) is not str or not HEX.fullmatch(x)
                   for x in (order.current_digest, order.restore_digest,
                             order.reason_digest))):
            raise PermissionError("rollback authority expired or mismatched")
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                bytes.fromhex(order.signature_hex),
                canonical_json(order.body()).encode())
        except (InvalidSignature, TypeError, ValueError) as exc:
            raise PermissionError("independent rollback signature invalid") from exc
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                seq, head, active, events = self._verify()
                if (seq != order.expected_generation or not events
                    or seq >= MAX_EVENTS or len(events) < 2
                    or order.current_digest != events[-1]["index_digest"]
                    or order.restore_digest != events[-2]["index_digest"]
                    or events[-2]["expires_at"] <= now):
                    raise PermissionError("stale or unsafe signed rollback target")
                restore = events[-2]
                event = {
                    "schema": "skeleton.jeeves.weight_vault_event.v1",
                    "owner": self.owner, "generation": seq + 1,
                    "action": "rollback", "tier": "rollback",
                    "previous_digest": events[-1]["index_digest"],
                    "index_digest": restore["index_digest"],
                    "entries": restore["entries"],
                    "rollback_order_digest": canonical_digest(order.body()),
                    "expires_at": min(restore["expires_at"], order.expires_at),
                    "observed_at": now,
                }
                digest = self._append(
                    event=event, seq=seq+1, previous_event_digest=head)
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise
        return {"generation": seq+1, "restored_digest": restore["index_digest"],
                "custody_digest": digest, "neural_weights_changed": False}

    def audit(self) -> dict:
        with self._lock:
            sequence, head, active, events = self._verify()
        return {"owner": self.owner, "generation": sequence,
                "head_digest": head,
                "index_digest": events[-1]["index_digest"] if events else ZERO,
                "entries": len(active),
                "history_verified": True, "read_only": True,
                "neural_weights_changed": False}
