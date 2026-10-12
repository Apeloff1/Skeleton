"""Durable, governed idle-only scheduler for Dragon Family's three gatherers.

Host-invoked on an authenticated user/device idle signal; never starts threads,
network tasks or an interval. This is a persistent lease + fair queue over the
canonical source inventory, not another crawler. The *trusted* host supplies
cancelable policy-bound article/video/recrawl adapters and review approvals.
All progress still passes DragonFamily.digest_idle and the current evidence gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from secrets import token_hex
from typing import Callable, Mapping
import json
import sqlite3

from .dragon_family import DragonFamily, IdleWindow, SourceReceipt, ROLES, _epoch, _owner, _source_id, _utc, _hash

@dataclass(frozen=True)
class IdleTask:
    dragon: str
    source_id: str
    url: str
    media: str
    topics: tuple[str, ...]
    last_content_digest: str
    attempt: int

@dataclass(frozen=True)
class IdleCoordinatorPolicy:
    max_tasks: int = 3
    min_idle_seconds: float = 300
    lease_seconds: float = 120
    changed_cooldown_seconds: float = 6 * 3600
    unchanged_cooldown_seconds: float = 6 * 3600
    transient_backoff_seconds: float = 300
    maximum_backoff_seconds: float = 8 * 3600
    max_eligible_scan: int = 2000

    def validate(self) -> None:
        if type(self.max_tasks) is not int or not 1 <= self.max_tasks <= 3:
            raise ValueError("invalid idle task limit")
        if type(self.max_eligible_scan) is not int or not 10 <= self.max_eligible_scan <= 100000:
            raise ValueError("invalid source scan budget")
        for name in ("min_idle_seconds", "lease_seconds", "changed_cooldown_seconds",
                     "unchanged_cooldown_seconds", "transient_backoff_seconds",
                     "maximum_backoff_seconds"):
            value = getattr(self, name)
            if type(value) not in (int,float) or not isfinite(value) or value < 1:
                raise ValueError("invalid scheduling policy: " + name)
        if not 60 <= self.min_idle_seconds <= 86400 or not 10 <= self.lease_seconds <= 3600:
            raise ValueError("invalid idle or lease duration")
        if self.transient_backoff_seconds > self.maximum_backoff_seconds:
            raise ValueError("backoff floor above ceiling")


def read_idle_family_history(db: sqlite3.Connection, owner: str, *,
                             authorized: bool, limit: int = 15) -> list[dict[str, object]]:
    """Verify the entire owner chain, then return bounded recent events."""
    _owner(owner)
    if not authorized:
        raise PermissionError("idle family journal requires authentication")
    if type(limit) is not int or not 1<=limit<=100:
        raise ValueError("invalid idle event page limit")
    exists=db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
        AND name='dragon_family_idle_attempt_events'""").fetchone()
    if not exists:
        return []
    rows=db.execute("""SELECT sequence,at,role,source_id,outcome,details,
        previous_hash,event_hash FROM dragon_family_idle_attempt_events
        WHERE owner=? ORDER BY sequence""",(owner,)).fetchall()
    prior="0"*64
    last=-1.
    result=[]
    for ordinal,row in enumerate(rows,1):
        sequence,at,role,sid,outcome,note,previous,digest=row
        if (sequence!=ordinal or at<last or previous!=prior or
                digest!=_hash([owner,sequence,at,role,sid,outcome,note,previous])):
            raise ValueError("idle family attempt journal integrity failure")
        last=at
        prior=digest
        result.append(dict(sequence=sequence,at=_utc(at),dragon=role,
                           source_id=sid,outcome=outcome,change=note,
                           digest=digest))
    return result[-limit:][::-1]


def read_idle_family_health(db: sqlite3.Connection, owner: str, *,
                            authorized: bool) -> dict[str, object]:
    """Authenticated read-only UI projection; never constructs worker authority.

    A queued lease's existence is not proof that a background task is currently
    running or even that a host scheduler is installed. The UI must distinguish
    last-known dispatch from the device's current idle status.
    """
    _owner(owner)
    if not authorized:
        raise PermissionError("idle family health requires authentication")
    exists=db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
        AND name='dragon_family_idle_leases'""").fetchone()
    if not exists:
        return dict(schema="skeleton.ai.dragon.idle_status.v1",
                    configured=False,workers={},history=[],
                    idle_only=True,host_state="not_connected",
                    max_tasks_per_tick=3)
    rows=db.execute("""SELECT role,COUNT(*),
        SUM(last_outcome='failed'),SUM(last_outcome='running'),
        SUM(last_outcome='changed'),SUM(last_outcome='unchanged'),
        MIN(CASE WHEN next_due>0 THEN next_due ELSE NULL END)
        FROM dragon_family_idle_leases
        WHERE owner=? GROUP BY role ORDER BY role""", (owner,)).fetchall()
    details={role:dict(known_sources=n,failed=failed or 0,
            incomplete_leases=running or 0,
            last_changes=changed or 0,unchanged=unchanged or 0,
            earliest_due_at=_utc(due) if due is not None else None)
            for role,n,failed,running,changed,unchanged,due in rows}
    history=read_idle_family_history(db,owner,authorized=True,limit=15)
    return dict(schema="skeleton.ai.dragon.idle_status.v1",configured=True,
                workers=details,history=history,idle_only=True,
                host_state="not_observed",
                max_tasks_per_tick=3)


class DragonIdleCoordinator:
    """Policy-bound, owner-fenced SQLite dispatch with finite durable leases.

    The host MUST restrict construction to its canonical Dragon owner and supply
    authoritative idle_state(). Browser-supplied booleans and public endpoints
    are never valid admission signals. Multi-host deployments must share the
    same canonical SQLite file or use an equivalent transactional coordinator.
    """
    def __init__(self, family: DragonFamily, *, policy: IdleCoordinatorPolicy = IdleCoordinatorPolicy()):
        policy.validate()
        if not isinstance(family, DragonFamily) or family.owner_scope is None:
            raise PermissionError("idle coordinator requires an owner-locked trusted family")
        if family.approval is None:
            raise PermissionError("canonical review callback required")
        if family.min_idle_seconds > policy.min_idle_seconds:
            raise ValueError("idle coordinator cannot weaken family idle policy")
        self.family = family
        self.db = family.db
        self.policy = policy
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_family_idle_leases(
            owner TEXT NOT NULL, role TEXT NOT NULL, source_id TEXT NOT NULL,
            next_due REAL NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_started REAL, last_completed REAL,
            lease_token TEXT NOT NULL DEFAULT '',
            lease_expires REAL NOT NULL DEFAULT 0,
            last_outcome TEXT NOT NULL DEFAULT 'new',
            PRIMARY KEY(owner,role,source_id))""")
        self.db.execute("""CREATE INDEX IF NOT EXISTS dragon_family_idle_due
            ON dragon_family_idle_leases(owner,role,next_due,lease_expires)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_family_idle_scan_cursor(
            owner TEXT PRIMARY KEY, last_source_id TEXT NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_family_idle_attempt_events(
            owner TEXT NOT NULL, sequence INTEGER NOT NULL, at REAL NOT NULL,
            role TEXT NOT NULL, source_id TEXT NOT NULL,
            outcome TEXT NOT NULL, details TEXT NOT NULL,
            previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL,
            PRIMARY KEY(owner,sequence))""")
        self.db.commit()

    def _window(self, read: Callable[[], IdleWindow]) -> IdleWindow:
        state = read()
        if not isinstance(state, IdleWindow) or not state.permitted(
                min_idle_seconds=self.policy.min_idle_seconds):
            raise PermissionError("trusted host is not idle or consented")
        return state

    def _candidates(self, owner: str, now: float,
                    task_topics: tuple[str, ...], adjacent_topics: tuple[str, ...]) -> list[tuple]:
        from .dragon_family import _tokens
        focus, adjacent = set(_tokens(task_topics)), set(_tokens(adjacent_topics))
        if not focus:
            raise ValueError("idle research requires real task context")
        # Use the latest known source version across the *whole* family to
        # avoid duplicate fetches sold as novelty. A monitor must have a
        # previously acquired source; article/video may also discover new
        # approved, previously registered catalog entries.
        # Keyset cursor means a massive catalog cannot starve sources after
        # the first fixed-size window. We advance the scan even if every row
        # is irrelevant, and wrap deterministically at the end.
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            previous=self.db.execute("""SELECT last_source_id
                FROM dragon_family_idle_scan_cursor WHERE owner=?""",(owner,)).fetchone()
            marker=previous[0] if previous else ""
            query="""WITH latest AS (
                SELECT owner,source_id,content_digest,observed_at,
                  ROW_NUMBER() OVER (PARTITION BY owner,source_id
                      ORDER BY observed_at DESC,rowid DESC) AS ordinal
                FROM dragon_family_readings WHERE owner=?
              )
              SELECT s.source_id,s.url,s.media,s.topics_json,
                     COALESCE(l.content_digest,s.parent_digest),
                     COALESCE(l.observed_at,s.registered_at)
              FROM dragon_family_sources s LEFT JOIN latest l ON
                l.owner=s.owner AND l.source_id=s.source_id AND l.ordinal=1
              WHERE s.owner=? AND s.source_id {operator} ?
              ORDER BY s.source_id LIMIT ?"""
            rows=self.db.execute(query.format(operator=">"),
                                 (owner,owner,marker,self.policy.max_eligible_scan)).fetchall()
            if len(rows)<self.policy.max_eligible_scan and marker:
                rows+=self.db.execute(query.format(operator="<="),
                    (owner,owner,marker,self.policy.max_eligible_scan-len(rows))).fetchall()
            if rows:
                self.db.execute("""INSERT INTO dragon_family_idle_scan_cursor VALUES(?,?)
                    ON CONFLICT(owner) DO UPDATE SET last_source_id=excluded.last_source_id""",
                    (owner,rows[-1][0]))
        out = []
        for sid,url,media,topics_json,revision,seen_at in rows:
            source_topics = set(json.loads(topics_json))
            direct = bool(source_topics & focus)
            related = bool(source_topics & adjacent)
            if not (direct or related):
                continue
            for role in ROLES:
                if role != "monitor" and media != role:
                    continue
                if role == "monitor" and not revision:
                    continue
                lease = self.db.execute("""SELECT next_due,lease_expires,attempts
                    FROM dragon_family_idle_leases WHERE owner=? AND role=? AND source_id=?""",
                    (owner,role,sid)).fetchone()
                if lease and (lease[0] > now or lease[1] > now):
                    continue
                ordinal = lease[2] if lease else 0
                # Direct relevance > adjacent, then least tried, then least
                # recently examined, then stable ID. Separate candidate
                # generation from trusted network execution.
                # Dispatch primary article/video workers before the monitor;
                # otherwise Scout can claim a video's lease first and starve
                # Flicker despite three available catalog sources.
                out.append((ROLES.index(role),0 if direct else 1,ordinal,float(seen_at),
                            sid,role,url,media,tuple(sorted(source_topics)),revision or ""))
        return sorted(out)

    def _reserve(self, owner: str, role: str, sid: str, start: float) -> str | None:
        key = token_hex(24)
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            row = self.db.execute("""SELECT next_due,lease_expires,attempts
                FROM dragon_family_idle_leases WHERE owner=? AND role=? AND source_id=?""",
                (owner,role,sid)).fetchone()
            if row and (row[0] > start or row[1] > start):
                return None
            self.db.execute("""INSERT INTO dragon_family_idle_leases
                (owner,role,source_id,next_due,failures,attempts,last_started,
                 lease_token,lease_expires,last_outcome)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(owner,role,source_id) DO UPDATE SET
                  attempts=dragon_family_idle_leases.attempts+1,
                  last_started=excluded.last_started,
                  lease_token=excluded.lease_token,
                  lease_expires=excluded.lease_expires,
                  last_outcome='running'""",
                (owner,role,sid,0,0,1,start,key,start+self.policy.lease_seconds,"running"))
        return key

    def _owned(self, owner: str, role: str, sid: str, key: str, now: float) -> bool:
        row=self.db.execute("""SELECT lease_expires FROM dragon_family_idle_leases
            WHERE owner=? AND role=? AND source_id=? AND lease_token=?""",
            (owner,role,sid,key)).fetchone()
        return bool(row and now < row[0])

    def _record_attempt(self, owner: str, role: str, sid: str,
                        at: float, outcome: str) -> None:
        notes = {
            "changed": "(improved: independently reviewed new source content acquired)",
            "unchanged": "(checked: no novel verified source information)",
            "failed": "(deferred: adapter failed; bounded retry scheduled)",
            "paused": "(paused: user activity, consent, capacity, or lease fence)",
        }
        if outcome not in notes:
            raise ValueError("unknown idle research outcome")
        previous=self.db.execute("""SELECT sequence,event_hash,at
            FROM dragon_family_idle_attempt_events WHERE owner=?
            ORDER BY sequence DESC LIMIT 1""",(owner,)).fetchone()
        sequence,prior=(previous[0]+1,previous[1]) if previous else (1,"0"*64)
        if sequence>100000:
            raise ValueError("idle attempt history capacity exhausted")
        if previous and at<previous[2]:
            raise ValueError("idle research event time regressed")
        note=notes[outcome]
        fingerprint=_hash([owner,sequence,at,role,sid,outcome,note,prior])
        self.db.execute("""INSERT INTO dragon_family_idle_attempt_events
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (owner,sequence,at,role,sid,outcome,note,prior,fingerprint))

    def _finish(self, owner: str, role: str, sid: str, key: str,
                now: float, outcome: str) -> None:
        if outcome not in ("changed","unchanged","failed","paused"):
            raise ValueError("invalid idle completion")
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            previous=self.db.execute("""SELECT failures FROM dragon_family_idle_leases
                WHERE owner=? AND role=? AND source_id=? AND lease_token=?""",
                (owner,role,sid,key)).fetchone()
            if previous is None:
                return
            errors = min(16,previous[0]+1) if outcome=="failed" else 0
            due = (self.policy.changed_cooldown_seconds if outcome=="changed" else
                   self.policy.unchanged_cooldown_seconds if outcome=="unchanged" else
                   min(self.policy.maximum_backoff_seconds,
                       self.policy.transient_backoff_seconds*(2**min(12,errors-1))) if outcome=="failed" else
                   self.policy.transient_backoff_seconds)
            self.db.execute("""UPDATE dragon_family_idle_leases SET next_due=?,
                failures=?,last_completed=?,last_outcome=?,lease_token='',lease_expires=0
                WHERE owner=? AND role=? AND source_id=? AND lease_token=?""",
                (now+due,errors,now,outcome,owner,role,sid,key))
            self._record_attempt(owner,role,sid,now,outcome)

    def run_once(self, owner: str, *,
                 authorized: bool,
                 idle_state: Callable[[], IdleWindow],
                 gatherers: Mapping[str, Callable[[IdleTask], SourceReceipt | None]],
                 task_topics: tuple[str, ...],
                 adjacent_topics: tuple[str, ...] = ()) -> dict[str, object]:
        """Host-invoked bounded tick; fails closed if foreground becomes active.

        A trusted adapter must apply DNS/SSRF/robots/license policies, network
        deadlines < lease duration, rate limits, video grants, content hash and
        independently reviewed evidence before returning SourceReceipt. `None`
        means unchanged evidence, not a successful acquisition. No catch-up or
        unbounded work is scheduled after an interruption.
        """
        self.family._assert_owner(owner)
        if not authorized:
            raise PermissionError("authenticated host owner required")
        if not callable(idle_state):
            raise ValueError("trusted idle observer required")
        if not isinstance(gatherers,Mapping):
            raise ValueError("host must supply policy-bound gatherers")
        state=self._window(idle_state)
        if not self.db.execute("SELECT 1 FROM dragon_family_broods WHERE owner=?",
                               (owner,)).fetchone():
            return dict(at=_utc(state.now),attempted=0,changed=0,unchanged=0,
                        failed=0,paused=False,reason="parent_source_quest_incomplete")
        candidates=self._candidates(owner,state.now,task_topics,adjacent_topics)
        stats: dict[str,object] = dict(at=_utc(state.now),attempted=0,changed=0,
                                       unchanged=0,failed=0,paused=False)
        roles_seen: set[str] = set()
        sources_seen: set[str] = set()
        for _,_,attempts,seen,sid,role,url,media,tags,digest in candidates:
            if len(roles_seen) >= self.policy.max_tasks:
                break
            if sid in sources_seen or role in roles_seen or role not in gatherers:
                continue
            adapter = gatherers[role]
            if not callable(adapter):
                raise ValueError("invalid specialist adapter")
            try:
                before=self._window(idle_state)
            except PermissionError:
                stats["paused"]=True
                break
            key=self._reserve(owner,role,sid,before.now)
            if key is None:
                continue
            roles_seen.add(role)
            sources_seen.add(sid)
            stats["attempted"] += 1
            task=IdleTask(role,sid,url,media,tags,digest,attempts+1)
            try:
                receipt=adapter(task)
                after=self._window(idle_state)
                if not self._owned(owner,role,sid,key,after.now):
                    raise PermissionError("idle lease lost or expired")
                if receipt is None:
                    status="unchanged"
                elif (not isinstance(receipt,SourceReceipt) or
                      receipt.source_id!=sid):
                    raise ValueError("untrusted adapter returned wrong source receipt")
                else:
                    changed=self.family.digest_idle(
                        owner,role,receipt,authorized=True,window=after,
                        task_topics=task_topics,adjacent_topics=adjacent_topics)
                    status="changed" if changed else "unchanged"
                self._finish(owner,role,sid,key,after.now,status)
                stats[status] += 1
            except PermissionError:
                # A loss of consent/activity/lease must never award progress;
                # the host may explicitly resume on a later idle tick.
                stats["paused"]=True
                self._finish(owner,role,sid,key,_epoch(idle_state().now),"paused")
                break
            except Exception:
                # Do not disclose adapter exceptions in the user-facing game.
                # Surface aggregate errors for operators; bound retries.
                stats["failed"] += 1
                current=idle_state()
                if not isinstance(current,IdleWindow):
                    raise PermissionError("idle host observer failed")
                self._finish(owner,role,sid,key,_epoch(current.now),"failed")
        return stats

    def health(self, owner: str, *, authorized: bool) -> dict[str,object]:
        self.family._assert_owner(owner)
        if not authorized:
            raise PermissionError("authenticated idle coordinator status required")
        rows=self.db.execute("""SELECT role,COUNT(*),SUM(last_outcome='failed'),
            SUM(last_outcome='running'),MIN(next_due)
            FROM dragon_family_idle_leases WHERE owner=? GROUP BY role ORDER BY role""",
            (owner,)).fetchall()
        by_role={role:dict(sources=n,failed=errors or 0,
                           running=running or 0,
                           next_due_at=_utc(due) if due is not None else None)
                 for role,n,errors,running,due in rows}
        return dict(idle_only=True,workers=by_role,
                    max_tasks_per_tick=self.policy.max_tasks,
                    scheduling="trusted host-invoked; bounded lease; no daemon")
