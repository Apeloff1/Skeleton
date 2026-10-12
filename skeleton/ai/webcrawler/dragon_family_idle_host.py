"""Durable, owner-locked host control for Dragon Family idle research.

The application/desktop host, never a browser or source adapter, issues a
scoped DragonConsentLedger receipt after opt-in, installs the device-idle
observer, and invokes tick() on its existing authorized idle event loop.
No daemon, web access, model-weight writes or provider credentials live here.

A durable session records approved topics and active consent. Every idle
observation rechecks session generation and revocable consent. An atomic daily
budget is debited *with* each SQLite source lease, not after work completes.
A foreground/resumed/cancelled session cannot accept resulting Dragon XP.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Callable
import json
import sqlite3

from .dragon_consent_ledger import DragonConsentLedger
from .dragon_family import IdleWindow, _epoch, _hash, _owner, _tokens, _utc
from .dragon_family_custody_bridge import DragonFamilyCustodyBridge
from .dragon_family_idle_coordinator import IdleCoordinatorPolicy
from .dragon_family_idle_integration import CaptureAdapter, DragonIdleAcquisitionService

SCHEMA = "skeleton.ai.dragon.idle.host.v1"


def idle_consent_scope(owner: str, task_topics: tuple[str, ...],
                       adjacent_topics: tuple[str, ...]) -> str:
    """Stable source-scope digest; tokens cannot be silently widened later."""
    _owner(owner)
    primary = _tokens(task_topics)
    adjacent = _tokens(adjacent_topics)
    if not primary or len(primary) > 24 or set(primary) & set(adjacent):
        raise ValueError("idle session requires nonoverlapping task/adjacent topics")
    return _hash([SCHEMA,owner,primary,adjacent,("article","video","monitor")])


@dataclass(frozen=True)
class DragonIdleHostPolicy:
    max_daily_attempts: int = 48
    max_daily_per_role: int = 20
    min_seconds_between_ticks: float = 120
    max_consent_lifetime_seconds: float = 30 * 86400

    def validate(self) -> None:
        if (type(self.max_daily_attempts) is not int or
                not 1 <= self.max_daily_attempts <= 1000 or
                type(self.max_daily_per_role) is not int or
                not 1 <= self.max_daily_per_role <= self.max_daily_attempts):
            raise ValueError("invalid daily research quota")
        for value in (self.min_seconds_between_ticks, self.max_consent_lifetime_seconds):
            if type(value) not in (int,float) or not isfinite(value) or value <= 0:
                raise ValueError("invalid host idle time limits")
        if not 60 <= self.min_seconds_between_ticks <= 86400:
            raise ValueError("invalid idle tick throttle")
        if not 3600 <= self.max_consent_lifetime_seconds <= 30*86400:
            raise ValueError("invalid consent lifetime ceiling")


def read_idle_host_projection(db: sqlite3.Connection, owner: str, *,
                              at: float, authorized: bool) -> dict[str, object]:
    """Read-only, authenticated UI projection; never enrolls a device worker.

    A deployed backend is not necessarily the user's local desktop. This
    endpoint reports *consent and past durable work*, never live OS activity.
    No schema creation, worker activation, or fresh consent issuance occurs.
    """
    _owner(owner)
    if not authorized:
        raise PermissionError("authenticated Dragon idle status required")
    at=_epoch(at)
    has_sessions=db.execute("""SELECT 1 FROM sqlite_master
      WHERE type='table' AND name='dragon_family_idle_host_sessions'""").fetchone()
    row=(db.execute("""SELECT consent_id,scope_digest,task_topics_json,
      adjacent_topics_json,active,generation,changed_at,next_tick_at
      FROM dragon_family_idle_host_sessions WHERE owner=?""",(owner,)).fetchone()
      if has_sessions else None)
    has_ledger=db.execute("""SELECT 1 FROM sqlite_master
      WHERE type='table' AND name='dragon_consent'""").fetchone()
    valid=False
    expires_at=None
    if row and row[4] and has_ledger:
        record=db.execute("""SELECT capture,analysis,issued_at,expires_at,
          revoked_at,scope_digest FROM dragon_consent
          WHERE owner=? AND consent_id=?""",(owner,row[0])).fetchone()
        try:
            primary=tuple(json.loads(row[2]))
            adjacent=tuple(json.loads(row[3]))
            valid=bool(
                record and record[0] == 1 and record[1] == 1 and
                record[4] is None and
                0 <= at-record[2] < record[3]-record[2] <= 30*86400 and
                record[5]==row[1] and
                idle_consent_scope(owner,primary,adjacent)==row[1]
            )
            if valid:
                expires_at=_utc(record[3])
        except (ValueError,TypeError,OverflowError,KeyError):
            valid=False
    has_usage=db.execute("""SELECT 1 FROM sqlite_master
      WHERE type='table' AND name='dragon_family_idle_daily_usage'""").fetchone()
    usage=dict(db.execute("""SELECT role,started
        FROM dragon_family_idle_daily_usage WHERE owner=? AND day_utc=?""",
        (owner,int(at//86400))).fetchall()) if has_usage else {}
    return dict(schema=SCHEMA,configured=bool(row),active=valid,
                host_idle_now=None,requires_os_idle_observer=True,
                daily_attempts=sum(usage.values()),daily_by_specialist=usage,
                consent_expires_at=expires_at,
                next_tick_at=_utc(row[7]) if row and valid else None)


class DragonIdleHostControl:
    """Canonical host's opt-in/revoke/tick integration for one authenticated owner.

    It is NOT safe to construct this class from unauthenticated requests or to
    treat device-idle state transmitted by a browser as trusted. The host must
    bind its own OS/foreground/job/consent observation. Each call to tick
    performs at most the already-bound coordinator's three specialist tasks.
    """

    def __init__(self, bridge: DragonFamilyCustodyBridge,
                 *, host_policy: DragonIdleHostPolicy = DragonIdleHostPolicy(),
                 coordinator_policy: IdleCoordinatorPolicy = IdleCoordinatorPolicy()):
        if not isinstance(bridge, DragonFamilyCustodyBridge):
            raise PermissionError("canonical owner-locked source custody required")
        host_policy.validate()
        coordinator_policy.validate()
        self.bridge = bridge
        self.owner = bridge.owner
        self.db = bridge.db
        self.policy = host_policy
        self.consent = DragonConsentLedger(self.db)
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_family_idle_host_sessions(
            owner TEXT PRIMARY KEY, consent_id TEXT NOT NULL,
            scope_digest TEXT NOT NULL, task_topics_json TEXT NOT NULL,
            adjacent_topics_json TEXT NOT NULL,
            active INTEGER NOT NULL, generation INTEGER NOT NULL,
            changed_at REAL NOT NULL, next_tick_at REAL NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_family_idle_daily_usage(
            owner TEXT NOT NULL, day_utc INTEGER NOT NULL,
            role TEXT NOT NULL, started INTEGER NOT NULL,
            PRIMARY KEY(owner,day_utc,role))""")
        self.db.commit()
        self.acquisition = DragonIdleAcquisitionService(
            bridge, policy=coordinator_policy, reserve_budget=self._reserve_budget)

    def _row(self) -> tuple | None:
        return self.db.execute("""SELECT consent_id,scope_digest,task_topics_json,
            adjacent_topics_json,active,generation,changed_at,next_tick_at
            FROM dragon_family_idle_host_sessions WHERE owner=?""",
            (self.owner,)).fetchone()

    def _require(self, at: float, generation: int | None = None) -> tuple:
        _epoch(at)
        row = self._row()
        if row is None or row[4] != 1:
            raise PermissionError("Dragon idle research is not opted in")
        if generation is not None and row[5] != generation:
            raise PermissionError("Dragon idle session changed during capture")
        consent = self.consent.require_active(
            self.owner,row[0],now=at,scope_digest=row[1],authorized=True)
        if not consent.capture or not consent.analysis:
            raise PermissionError("capture and analysis consent both required")
        if consent.expires_at-consent.issued_at > self.policy.max_consent_lifetime_seconds:
            raise PermissionError("idle consent exceeds maximum allowed lifetime")
        primary=tuple(json.loads(row[2]))
        adjacent=tuple(json.loads(row[3]))
        if idle_consent_scope(self.owner,primary,adjacent)!=row[1]:
            raise PermissionError("stored idle task consent scope changed")
        return row

    def activate(self, *, consent_id: str,
                 task_topics: tuple[str, ...],
                 adjacent_topics: tuple[str, ...] = (),
                 at: float, authorized: bool) -> dict[str,object]:
        """Activate an *existing*, explicitly granted, unrevoked consent ID."""
        if not authorized:
            raise PermissionError("authenticated host opt-in required")
        at=_epoch(at)
        scope=idle_consent_scope(self.owner,task_topics,adjacent_topics)
        consent=self.consent.require_active(
            self.owner,consent_id,now=at,scope_digest=scope,authorized=True)
        if not consent.capture or not consent.analysis:
            raise PermissionError("capture/analysis consent missing")
        if consent.expires_at-consent.issued_at > self.policy.max_consent_lifetime_seconds:
            raise PermissionError("idle opt-in cannot exceed policy lifetime")
        primary=_tokens(task_topics)
        adjacent=_tokens(adjacent_topics)
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            previous=self._row()
            if previous and at<previous[6]:
                raise ValueError("idle session clock regressed")
            if previous and previous[4] and previous[0]==consent_id and previous[1]==scope:
                return self.status(at=at,authorized=True)
            # A new opt-in generation fences outstanding capture workers.
            generation=(previous[5]+1) if previous else 1
            self.db.execute("""INSERT INTO dragon_family_idle_host_sessions
              VALUES(?,?,?,?,?,?,?,?,?)
              ON CONFLICT(owner) DO UPDATE SET
               consent_id=excluded.consent_id,scope_digest=excluded.scope_digest,
               task_topics_json=excluded.task_topics_json,
               adjacent_topics_json=excluded.adjacent_topics_json,
               active=excluded.active,generation=excluded.generation,
               changed_at=excluded.changed_at,next_tick_at=excluded.next_tick_at""",
               (self.owner,consent_id,scope,json.dumps(primary),
                json.dumps(adjacent),1,generation,at,at))
        return self.status(at=at,authorized=True)

    def stop(self, *, at: float, authorized: bool) -> dict[str,object]:
        """Immediately fences pending research; does not revoke other app jobs."""
        if not authorized:
            raise PermissionError("authenticated opt-out required")
        at=_epoch(at)
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            row=self._row()
            if row:
                if at<row[6]:
                    raise ValueError("idle opt-out clock regressed")
                self.db.execute("""UPDATE dragon_family_idle_host_sessions SET
                    active=0,generation=generation+1,changed_at=?,
                    next_tick_at=? WHERE owner=?""",(at,at,self.owner))
        return self.status(at=at,authorized=True)

    def _reserve_budget(self, owner: str, role: str, at: float) -> None:
        """Called WITHIN the coordinator's BEGIN IMMEDIATE lease transaction."""
        if owner!=self.owner or role not in ("article","video","monitor"):
            raise PermissionError("quota owner or specialist mismatch")
        self._require(at)
        day=int(_epoch(at)//86400)
        used=self.db.execute("""SELECT COALESCE(SUM(started),0)
            FROM dragon_family_idle_daily_usage WHERE owner=? AND day_utc=?""",
            (owner,day)).fetchone()[0]
        if used>=self.policy.max_daily_attempts:
            raise PermissionError("daily idle acquisition quota exhausted")
        self.db.execute("""INSERT INTO dragon_family_idle_daily_usage
          (owner,day_utc,role,started) VALUES(?,?,?,1)
          ON CONFLICT(owner,day_utc,role) DO UPDATE SET
          started=started+1 WHERE started<?""",
          (owner,day,role,self.policy.max_daily_per_role))
        count=self.db.execute("""SELECT started FROM dragon_family_idle_daily_usage
            WHERE owner=? AND day_utc=? AND role=?""",(owner,day,role)).fetchone()[0]
        if count>self.policy.max_daily_per_role:
            raise PermissionError("specialist daily quota exhausted")
        # SQLITE upsert predicate can be ignored when quota is reached.
        if self.db.execute("SELECT changes()").fetchone()[0]!=1:
            raise PermissionError("specialist daily quota exhausted")

    def tick(self, *, authorized: bool,
             host_idle_state: Callable[[], IdleWindow],
             article_capture: CaptureAdapter | None = None,
             video_capture: CaptureAdapter | None = None,
             monitor_capture: CaptureAdapter | None = None) -> dict[str,object]:
        if not authorized:
            raise PermissionError("authenticated host idle dispatcher required")
        if not callable(host_idle_state):
            raise ValueError("authoritative host idle observer required")
        first=host_idle_state()
        if not isinstance(first,IdleWindow):
            raise PermissionError("untrusted idle state observation")
        if not first.permitted(min_idle_seconds=self.acquisition.coordinator.policy.min_idle_seconds):
            raise PermissionError("host not idle")
        initial=self._require(first.now)
        generation=initial[5]
        # Durable throttle is a guard against hundreds of overlapping
        # tick calls; it is NOT evidence that the user's machine is idle.
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            row=self._require(first.now,generation)
            if first.now<row[7]:
                raise PermissionError("idle tick rate limit")
            updated=self.db.execute("""UPDATE dragon_family_idle_host_sessions SET
              next_tick_at=? WHERE owner=? AND active=1 AND generation=?
              AND next_tick_at<=?""",(
                first.now+self.policy.min_seconds_between_ticks,
                self.owner,generation,first.now))
            if updated.rowcount!=1:
                raise PermissionError("idle scheduler session was replaced")
        def checked_state() -> IdleWindow:
            state=host_idle_state()
            if not isinstance(state,IdleWindow):
                raise PermissionError("untrusted host activity observation")
            self._require(state.now,generation)
            return state
        return self.acquisition.run_once(
            authorized=True,idle_state=checked_state,
            article_capture=article_capture,
            video_capture=video_capture,
            monitor_capture=monitor_capture,
            task_topics=tuple(json.loads(initial[2])),
            adjacent_topics=tuple(json.loads(initial[3])),
            # Called *under* the same write transaction that inserts a new
            # reading. Consent revocation on another connection cannot race
            # past this final durable check.
            commit_gate=lambda at: bool(self._require(at,generation)))

    def status(self, *, at: float, authorized: bool) -> dict[str,object]:
        if not authorized:
            raise PermissionError("authenticated host status required")
        at=_epoch(at)
        row=self._row()
        active=False
        if row and row[4]==1:
            try:
                self._require(at)
                active=True
            except (PermissionError,ValueError):
                active=False
        today=int(at//86400)
        usage=dict(self.db.execute("""SELECT role,started
            FROM dragon_family_idle_daily_usage WHERE owner=? AND day_utc=?""",
            (self.owner,today)).fetchall())
        return dict(schema=SCHEMA,owner=self.owner,active=active,
                    configured=row is not None,host_idle_now=None,
                    consent_expires_at=(self.consent.get(
                        self.owner,row[0],authorized=True).expires_at
                        if active else None),
                    daily_attempts=sum(usage.values()),
                    daily_limit=self.policy.max_daily_attempts,
                    daily_by_specialist=usage,
                    next_tick_at=_utc(row[7]) if row and active else None,
                    requires_os_idle_observer=True)
