"""Finite, consent-scoped practice scheduler atop the canonical DragonPracticeLab.

An existing trusted scheduler calls pulse(). Creating a subscription does not
spawn a thread, network crawler, or background job. Every run is bounded by
authorization expiry, tick count, cooldown and the Lab's daily quota.
"""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3
from .dragon_practice_lab import DragonPracticeLab, PracticeAttempt, _owner, _time


@dataclass(frozen=True)
class PracticeSubscription:
    owner: str
    enabled: bool
    expires_at: float
    next_due: float
    interval_seconds: int
    remaining_ticks: int
    demos_per_tick: int


class DragonPracticeCycles:
    def __init__(self, db: sqlite3.Connection, lab: DragonPracticeLab):
        if lab.db is not db:
            raise ValueError("practice controller and lab must share one canonical connection")
        self.db = db
        self.lab = lab
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_practice_cycles(
            owner TEXT PRIMARY KEY,enabled INTEGER NOT NULL,expires_at REAL NOT NULL,
            next_due REAL NOT NULL,interval_seconds INTEGER NOT NULL,
            remaining_ticks INTEGER NOT NULL,demos_per_tick INTEGER NOT NULL)""")
        db.commit()

    def enable(self, owner: str, *, authorized: bool, human_approved: bool,
               now: float, expires_at: float, interval_seconds: int = 3600,
               max_ticks: int = 24, demos_per_tick: int = 2) -> PracticeSubscription:
        _owner(owner)
        _time(now)
        _time(expires_at)
        if not authorized or not human_approved:
            raise PermissionError("scheduled practice requires separate human approval")
        if not (now < expires_at <= now + 7*86400):
            raise ValueError("practice permission must expire within seven days")
        if not isinstance(interval_seconds,int) or not 300 <= interval_seconds <= 86400:
            raise ValueError("practice interval out of bounds")
        if not isinstance(max_ticks,int) or not 1 <= max_ticks <= 1000:
            raise ValueError("practice run budget out of bounds")
        if (not isinstance(demos_per_tick,int)
                or not 1 <= demos_per_tick <= self.lab.policy.max_demos_per_batch):
            raise ValueError("practice demo batch out of bounds")
        with self.db:
            self.db.execute("""INSERT INTO dragon_practice_cycles VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(owner) DO UPDATE SET enabled=excluded.enabled,
                expires_at=excluded.expires_at,next_due=excluded.next_due,
                interval_seconds=excluded.interval_seconds,
                remaining_ticks=excluded.remaining_ticks,
                demos_per_tick=excluded.demos_per_tick""",
                (owner,1,expires_at,now,interval_seconds,max_ticks,demos_per_tick))
        return self.status(owner,authorized=True)

    def disable(self, owner: str, *, authorized: bool) -> None:
        _owner(owner)
        if not authorized:
            raise PermissionError("practice disable requires authorization")
        with self.db:
            self.db.execute("UPDATE dragon_practice_cycles SET enabled=0 WHERE owner=?",(owner,))

    def status(self, owner: str, *, authorized: bool) -> PracticeSubscription:
        _owner(owner)
        if not authorized:
            raise PermissionError("practice status requires authorization")
        row=self.db.execute("""SELECT enabled,expires_at,next_due,interval_seconds,
            remaining_ticks,demos_per_tick FROM dragon_practice_cycles
            WHERE owner=?""",(owner,)).fetchone()
        if row is None:
            return PracticeSubscription(owner,False,0,0,3600,0,0)
        return PracticeSubscription(owner,bool(row[0]),row[1],row[2],row[3],row[4],row[5])

    def pulse(self, owner: str, *, authorized: bool,
              now: float) -> tuple[PracticeAttempt,...]:
        """One allowed slice of work. No catch-up loops and no hidden retries."""
        _owner(owner)
        _time(now)
        if not authorized:
            raise PermissionError("practice pulse requires authorization")
        # Reserve the tick before reading it: prevent two scheduler workers
        # from starting the same practice slice concurrently.
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            row=self.db.execute("""SELECT enabled,expires_at,next_due,interval_seconds,
                remaining_ticks,demos_per_tick FROM dragon_practice_cycles
                WHERE owner=?""",(owner,)).fetchone()
            if row is None:
                return ()
            enabled,expires,due,interval,remaining,demos=row
            if now>=expires:
                self.db.execute("UPDATE dragon_practice_cycles SET enabled=0 WHERE owner=?",
                                (owner,))
                return ()
            if not enabled or now<due or remaining<=0:
                return ()
            # Reserve the budget and next due BEFORE materializing any artifact.
            updated=self.db.execute("""UPDATE dragon_practice_cycles
                SET remaining_ticks=remaining_ticks-1,next_due=?,
                enabled=CASE WHEN remaining_ticks<=1 THEN 0 ELSE enabled END
                WHERE owner=? AND enabled=1 AND next_due<=? AND expires_at>? AND remaining_ticks>0""",
                (now+interval,owner,now,now))
            if updated.rowcount!=1:
                return ()
        # Current authorized schedule is the consent grant. Lesson-specific
        # consent must also remain active; revocation blocks work immediately.
        return self.lab.run_batch(owner,authorized=True,consent=True,now=now,max_demos=demos)
