"""Durable, owner-scoped RSS freshness queue for the idle Updates hatchling.

Only proposes source IDs for a separately authorized worker. It never opens
URLs, issues website rights, creates a worker ticket, or turns news into
approved knowledge. Its HMAC-linked journal detects rollback and mutations
of scheduled state on any subsequent read, including after process restart.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import sqlite3
from urllib.parse import urlsplit
from dataclasses import dataclass

from skeleton.ai.game_builder.contracts import canonical_json, canonical_digest
from .dragon_nest_worker_admission import HatchlingWorkerTicket, DragonNestWorkerAdmission

ZERO = "0" * 64
MAX_SUBSCRIPTIONS = 512
MAX_EVENTS_PER_SOURCE = 10000


def _identity(owner: str, source_id: str, url: str | None = None) -> None:
    if (type(owner) is not str or not 1 <= len(owner) <= 128
        or any(c in owner for c in "\n\r/\\")
        or type(source_id) is not str or len(source_id) != 71
        or not source_id.startswith("source-")
        or any(c not in "0123456789abcdef" for c in source_id[7:])):
        raise ValueError("bounded canonical owner and source ID required")
    if url is not None:
        if type(url) is not str or len(url) > 2048:
            raise ValueError("bounded HTTPS feed URL required")
        p = urlsplit(url)
        if (p.scheme != "https"
            or not p.hostname or p.username or p.password or p.fragment
            or not p.netloc or any(c.isspace() for c in url)):
            raise ValueError("HTTPS feed identity without credentials required")


def _hash(value: str) -> str:
    if (type(value) is not str or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError("external policy evidence digest required")
    return value


@dataclass(frozen=True)
class FeedPlan:
    owner: str
    source_id: str
    feed_url: str
    host: str
    priority: int
    polling_period: int
    next_due: int
    failures: int
    last_poll: int | None
    last_result: str
    external_policy_digest: str
    revision: int


class DragonRssFreshnessScheduler:
    def __init__(self, db: sqlite3.Connection, *, signing_key: bytes):
        if (not isinstance(db, sqlite3.Connection)
            or type(signing_key) is not bytes or len(signing_key) < 32):
            raise ValueError("operator-controlled signed RSS ledger required")
        self.db = db
        self.key = signing_key
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_rss_schedule_v1(
            owner TEXT NOT NULL, source_id TEXT NOT NULL,
            revision INTEGER NOT NULL, state TEXT NOT NULL,
            mac TEXT NOT NULL, PRIMARY KEY(owner,source_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_rss_schedule_events_v1(
            owner TEXT NOT NULL, source_id TEXT NOT NULL,
            sequence INTEGER NOT NULL, snapshot TEXT NOT NULL,
            previous_mac TEXT NOT NULL, mac TEXT NOT NULL,
            PRIMARY KEY(owner,source_id,sequence))""")

    def _mac(self, owner: str, sid: str, seq: int,
             state: str, previous: str) -> str:
        message = canonical_json({
            "schema": "skeleton.dragon.rss_poll_journal.v1",
            "owner": owner, "source_id": sid, "sequence": seq,
            "state": state, "previous_mac": previous,
        }).encode()
        return hmac.new(self.key, message, hashlib.sha256).hexdigest()

    def _current(self, owner: str, sid: str) -> dict | None:
        row = self.db.execute(
            "SELECT revision,state,mac FROM dragon_rss_schedule_v1 "
            "WHERE owner=? AND source_id=?", (owner, sid)).fetchone()
        events = self.db.execute(
            "SELECT sequence,snapshot,previous_mac,mac "
            "FROM dragon_rss_schedule_events_v1 WHERE owner=? AND source_id=? "
            "ORDER BY sequence", (owner, sid)).fetchall()
        if row is None and events:
            raise ValueError("deleted RSS scheduler head")
        if row is None:
            return None
        if len(events) != row[0] or not 1 <= row[0] <= MAX_EVENTS_PER_SOURCE:
            raise ValueError("RSS scheduler event-chain length mismatch")
        previous = ZERO
        for index, (seq, state, old, mac) in enumerate(events, start=1):
            if (seq != index or old != previous
                or not hmac.compare_digest(
                    mac, self._mac(owner, sid, seq, state, old))):
                raise ValueError("RSS scheduler journal chain corrupted")
            previous = mac
        if row[2] != previous or row[1] != events[-1][1]:
            raise ValueError("RSS scheduler head does not match journal")
        try:
            state = json.loads(row[1])
            if canonical_json(state) != row[1]:
                raise ValueError("noncanonical RSS scheduler snapshot")
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid RSS scheduler snapshot") from exc
        if (state.get("owner") != owner or state.get("source_id") != sid
            or state.get("revision") != row[0]):
            raise ValueError("RSS scheduler identity mismatch")
        _identity(owner, sid, state["feed_url"])
        _hash(state["external_policy_digest"])
        return state

    def _write(self, state: dict, expected: int) -> None:
        owner, sid = state["owner"], state["source_id"]
        body = canonical_json(state)
        seq = expected + 1
        if seq > MAX_EVENTS_PER_SOURCE:
            raise ValueError("RSS event budget exhausted; archive under operator control")
        old = ZERO if expected == 0 else self.db.execute(
            "SELECT mac FROM dragon_rss_schedule_v1 WHERE owner=? AND source_id=?",
            (owner, sid)).fetchone()[0]
        mac = self._mac(owner, sid, seq, body, old)
        if expected == 0:
            self.db.execute(
                "INSERT INTO dragon_rss_schedule_v1 VALUES(?,?,?,?,?)",
                (owner, sid, seq, body, mac))
        else:
            changed = self.db.execute(
                "UPDATE dragon_rss_schedule_v1 SET revision=?,state=?,mac=? "
                "WHERE owner=? AND source_id=? AND revision=?",
                (seq, body, mac, owner, sid, expected)).rowcount
            if changed != 1:
                raise PermissionError("stale RSS schedule compare-and-swap")
        self.db.execute(
            "INSERT INTO dragon_rss_schedule_events_v1 VALUES(?,?,?,?,?,?)",
            (owner, sid, seq, body, old, mac))

    def subscribe(self, owner: str, source_id: str, feed_url: str, *,
                  policy_receipt_digest: str, priority: int,
                  period_seconds: int, now: int, operator_authorized: bool) -> dict:
        _identity(owner, source_id, feed_url)
        _hash(policy_receipt_digest)
        if operator_authorized is not True:
            raise PermissionError("trusted RSS source subscription required")
        if (type(priority) is not int or not 0 <= priority <= 5
            or type(period_seconds) is not int
            or not 3600 <= period_seconds <= 7*86400
            or type(now) is not int or now < 0):
            raise ValueError("bounded RSS priority and poll period required")
        if self._current(owner, source_id) is not None:
            raise ValueError("RSS feed already registered")
        count = self.db.execute(
            "SELECT COUNT(*) FROM dragon_rss_schedule_v1 WHERE owner=?",
            (owner,)).fetchone()[0]
        if count >= MAX_SUBSCRIPTIONS:
            raise ValueError("RSS source subscription limit exceeded")
        host = urlsplit(feed_url).hostname.lower()
        state = {
            "owner": owner, "source_id": source_id,
            "feed_url": feed_url, "host": host,
            "external_policy_digest": policy_receipt_digest,
            "priority": priority, "polling_period": period_seconds,
            "next_due": now, "failures": 0, "last_poll": None,
            "last_result": "never", "revision": 1,
        }
        with self.db:
            self._write(state, 0)
        return {"revision": 1, "next_due": now,
                "scheduler_only": True, "crawl_authorized": False}

    def due(self, owner: str, *, now: int, limit: int = 20,
            per_host: int = 1, authorized: bool) -> dict:
        if authorized is not True:
            raise PermissionError("tenant RSS planning authority required")
        _identity(owner, "source-"+"0"*64)
        if (type(now) is not int or now < 0 or type(limit) is not int
            or not 1 <= limit <= 80 or type(per_host) is not int
            or not 1 <= per_host <= 5):
            raise ValueError("bounded RSS due census required")
        ids = self.db.execute(
            "SELECT source_id FROM dragon_rss_schedule_v1 "
            "WHERE owner=? ORDER BY source_id LIMIT ?",
            (owner, MAX_SUBSCRIPTIONS+1)).fetchall()
        if len(ids) > MAX_SUBSCRIPTIONS:
            raise ValueError("RSS schedule exceeds owner resource budget")
        candidates = []
        for (source_id,) in ids:
            state = self._current(owner, source_id)
            if state["next_due"] <= now:
                candidates.append(state)
        candidates.sort(key=lambda s: (
            -s["priority"], s["next_due"], s["host"], s["source_id"]))
        counts = {}
        selected = []
        for item in candidates:
            host = item["host"]
            if counts.get(host, 0) >= per_host:
                continue
            selected.append(item)
            counts[host] = counts.get(host, 0) + 1
            if len(selected) >= limit:
                break
        entries = [{
            "source_id": s["source_id"],
            "feed_url": s["feed_url"], "host": s["host"],
            "priority": s["priority"],
            "next_due": s["next_due"],
            "revision": s["revision"],
            "retry_failures": s["failures"],
            "existing_policy_receipt_digest": s["external_policy_digest"],
            "separate_fresh_rights_verification_required": True,
            "separate_idle_worker_admission_required": True,
            "crawler_authorized": False,
        } for s in selected]
        return {
            "schema": "skeleton.dragon.rss_due_workboard.v1",
            "owner": owner, "checked_at": now,
            "total_due": len(candidates), "selected": entries,
            "selected_count": len(entries), "per_host_limit": per_host,
            "read_only": True, "network_requests": 0,
            "workers_started": 0, "xp_awarded": 0,
            "training_authorized": False,
        }

    def record_poll(self, ticket: HatchlingWorkerTicket,
                    admission: DragonNestWorkerAdmission, *,
                    admission_kwargs: dict, expected_revision: int,
                    now: int, succeeded: bool,
                    snapshot_digest: str | None, authorized: bool) -> dict:
        if (authorized is not True or not isinstance(ticket, HatchlingWorkerTicket)
            or ticket.lane != "updates"
            or not isinstance(admission, DragonNestWorkerAdmission)
            or type(now) is not int or now < 0
            or type(succeeded) is not bool
            or type(expected_revision) is not int
            or type(admission_kwargs) is not dict):
            raise PermissionError("admitted idle Updates worker required")
        _identity(ticket.owner, ticket.source_id, ticket.source_url)
        if succeeded:
            _hash(snapshot_digest)
        elif snapshot_digest is not None:
            raise ValueError("failed fetch must not claim a signed snapshot")
        if not admission.authorize_chunk(ticket, **admission_kwargs):
            raise PermissionError("idle worker stopped before RSS poll recording")
        with self.db:
            state = self._current(ticket.owner, ticket.source_id)
            if state is None or state["revision"] != expected_revision:
                raise PermissionError("stale RSS poll scheduler generation")
            if state["feed_url"] != ticket.source_url:
                raise PermissionError("RSS ticket belongs to different source")
            if now < state["next_due"]:
                raise PermissionError("RSS poll cannot advance before its due time")
            if not admission.authorize_chunk(ticket, **admission_kwargs):
                raise PermissionError("idle worker preempted during RSS update")
            failures = 0 if succeeded else min(state["failures"]+1, 20)
            delay = state["polling_period"] * (2**min(failures, 8))
            delay = min(delay, 7*86400)
            # Stable source-specific jitter spreads retries without random
            # numbers or schedule drift on retries and server restarts.
            spread = int(hashlib.sha256(ticket.source_id.encode()).hexdigest()[:4],16)%60
            state = dict(state, revision=expected_revision+1, failures=failures,
                         next_due=now+delay+spread, last_poll=now,
                         last_result=("reported_snapshot:"+snapshot_digest
                                      if succeeded else "fetch_or_rights_failure"))
            self._write(state, expected_revision)
        return {
            "revision": state["revision"],
            "next_due": state["next_due"], "failures": failures,
            "host": state["host"], "network_requests": 0,
            "idle_ticket_rechecked": True,
            "crawl_rights_granted": False, "weights_promoted": False,
            "receipt_verified_here": False,
        }
