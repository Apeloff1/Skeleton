"""Owner-scoped durable Dragon nest state and append-only progression receipts.

Trusted workers call record_parent/record_idle; HTTP exposes only read(). A
MAC protects the latest snapshot and its audit-chain head; it cannot establish
the truth of a remote source, and external anti-rollback anchors remain separate.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import hmac
import json
import sqlite3

from .dragon_nest_progression import (
    AcquiredKnowledge, DragonNest, Hatchling, NestChange, _digest, _id,
    _iso, _tags, feed_parent, learn_when_idle, new_nest,
    nest_snapshot, verify_change_history,
)

MAX_SNAPSHOT_BYTES = 2_000_000
MAX_EVENTS = 40000


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


class DragonNestStore:
    """Persistent reducer for an already authenticated principal.

    Only trusted application workers should receive this object. No method
    accepts a client-supplied arbitrary XP/level or promotion decision.
    """

    def __init__(self, db: sqlite3.Connection, *, signing_key: bytes):
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("independent 32-byte nest signing key required")
        self.db = db
        self.key = signing_key
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS dragon_nest_state(
                owner TEXT PRIMARY KEY, state_json TEXT NOT NULL,
                event_count INTEGER NOT NULL, head TEXT NOT NULL,
                snapshot_mac TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS dragon_nest_history(
                owner TEXT NOT NULL, sequence INTEGER NOT NULL,
                change_json TEXT NOT NULL,
                PRIMARY KEY(owner,sequence))""")

    def _mac(self, owner: str, body: str, count: int, head: str) -> str:
        value = _json((owner, body, count, head))
        return hmac.new(self.key, value.encode("utf-8"), sha256).hexdigest()

    def _read_locked(self, owner: str) -> DragonNest | None:
        row = self.db.execute(
            "SELECT state_json,event_count,head,snapshot_mac "
            "FROM dragon_nest_state WHERE owner=?", (owner,)
        ).fetchone()
        if row is None:
            return None
        encoded, count, head, actual_mac = row
        if (not isinstance(encoded, str) or len(encoded) > MAX_SNAPSHOT_BYTES
                or type(count) is not int or count < 1 or count > MAX_EVENTS
                or not isinstance(head, str) or len(head) != 64
                or not isinstance(actual_mac, str)
                or not hmac.compare_digest(actual_mac, self._mac(owner, encoded, count, head))):
            raise ValueError("nest snapshot signature or limits invalid")
        rows = self.db.execute(
            "SELECT sequence,change_json FROM dragon_nest_history "
            "WHERE owner=? ORDER BY sequence", (owner,)
        )
        changes = []
        for index, (sequence, data) in enumerate(rows, 1):
            if index > count or sequence != index or not isinstance(data, str) or len(data) > 1200:
                raise ValueError("nest append-only history sequence invalid")
            try:
                entry = NestChange(**json.loads(data))
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError("nest history record invalid") from exc
            changes.append(entry)
        if len(changes) != count:
            raise ValueError("missing nest history events")
        try:
            value = json.loads(encoded)
            children = tuple(Hatchling(
                lane=child["lane"], stage=child["stage"], level=child["level"],
                evidence=tuple(tuple(receipt) for receipt in child["evidence"])
            ) for child in value["children"])
            state = DragonNest(
                owner=value["owner"], focus_tags=tuple(value["focus_tags"]),
                adjacent_tags=tuple(value["adjacent_tags"]),
                source_ids=tuple(value["source_ids"]),
                catalog_digest=value["catalog_digest"],
                consumed=tuple(value["consumed"]),
                level=value["level"], stage=value["stage"],
                children=children, changes=tuple(changes), head=value["head"],
            )
            if (state.owner != owner or state.head != head
                    or len(state.changes) != count or not verify_change_history(state)
                    or state.catalog_digest != _digest((
                        "dragon-source-census-v1", state.source_ids
                    )) or tuple(sorted(set(state.source_ids))) != state.source_ids
                    or len(state.source_ids) > 10000
                    or not set(state.consumed).issubset(state.source_ids)
                    or len(state.consumed) != len(set(state.consumed))
                    or tuple(sorted(state.consumed)) != state.consumed
                    or (len(state.consumed) == len(state.source_ids)) != (
                        state.stage == "adult" and len(children) == 3
                    ) or (children and tuple(x.lane for x in children) != (
                        "article", "video", "updates"
                    )) or any(
                        len(child.evidence) > 8192
                        or len({(r[0], r[1]) for r in child.evidence}) != len(child.evidence)
                        for child in children
                    )):
                raise ValueError("nest signed snapshot has inconsistent lineage")
            return state
        except (TypeError, ValueError, KeyError, IndexError, AttributeError) as exc:
            raise ValueError("nest signed snapshot cannot be reconstructed") from exc

    def read(self, owner: str, *, authorized: bool) -> DragonNest | None:
        _id(owner)
        if authorized is not True:
            raise PermissionError("owner authorization required")
        return self._read_locked(owner)

    def _save_locked(self, state: DragonNest, previous: DragonNest | None) -> None:
        if not verify_change_history(state):
            raise ValueError("history must verify before storing")
        before = len(previous.changes) if previous is not None else 0
        if previous is not None and state.changes[:before] != previous.changes:
            raise ValueError("history cannot be revised")
        if len(state.changes) <= before:
            raise ValueError("new journal event required")
        raw = asdict(state)
        del raw["changes"]
        encoded = _json(raw)
        if len(encoded.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
            raise ValueError("dragon nest snapshot exceeds storage budget")
        for entry in state.changes[before:]:
            self.db.execute(
                "INSERT INTO dragon_nest_history(owner,sequence,change_json) VALUES(?,?,?)",
                (state.owner, entry.sequence, _json(asdict(entry))),
            )
        count = len(state.changes)
        sig = self._mac(state.owner, encoded, count, state.head)
        if previous is None:
            self.db.execute(
                "INSERT INTO dragon_nest_state VALUES(?,?,?,?,?)",
                (state.owner, encoded, count, state.head, sig)
            )
        else:
            changed = self.db.execute(
                "UPDATE dragon_nest_state SET state_json=?,event_count=?,head=?,snapshot_mac=? "
                "WHERE owner=? AND head=?",
                (encoded, count, state.head, sig, state.owner, previous.head)
            )
            if changed.rowcount != 1:
                raise ValueError("nest state moved during transaction")

    def initialize(self, owner: str, source_ids: tuple[str, ...], *,
                   focus_tags: tuple[str, ...], adjacent_tags: tuple[str, ...] = (),
                   at: str, authorized: bool) -> DragonNest:
        _id(owner)
        if authorized is not True:
            raise PermissionError("trusted census authorizer required")
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            if self._read_locked(owner) is not None:
                raise ValueError("existing source census cannot be replaced")
            state = new_nest(owner, source_ids, focus_tags=focus_tags,
                             adjacent_tags=adjacent_tags, at=at)
            self._save_locked(state, None)
        return state

    def record_parent(self, owner: str, source_id: str, *,
                      content_sha256: str, at: str, authorized: bool,
                      reviewed: bool, lawful: bool) -> DragonNest:
        _id(owner)
        if authorized is not True:
            raise PermissionError("trusted parent evidence required")
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            before = self._read_locked(owner)
            if before is None:
                raise ValueError("nest must be initialized first")
            state = feed_parent(before, source_id, content_sha256=content_sha256,
                                at=at, authorized=authorized,
                                reviewed=reviewed, lawful=lawful)
            if state is not before:
                self._save_locked(state, before)
        return state

    def record_idle(self, owner: str, lane: str, evidence: AcquiredKnowledge, *,
                    at: str, idle_since: str, consented: bool,
                    background_allowed: bool, authorized: bool) -> DragonNest:
        _id(owner)
        if authorized is not True:
            raise PermissionError("trusted idle research authorizer required")
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            before = self._read_locked(owner)
            if before is None:
                raise ValueError("nest must be initialized first")
            state = learn_when_idle(
                before, lane, evidence, at=at, idle_since=idle_since,
                consented=consented, background_allowed=background_allowed,
                owner_authorized=authorized,
            )
            if state is not before:
                self._save_locked(state, before)
        return state

    def view(self, owner: str, *, authorized: bool) -> dict | None:
        state = self.read(owner, authorized=authorized)
        return nest_snapshot(state) if state is not None else None
