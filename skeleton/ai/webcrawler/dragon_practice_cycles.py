"""Finite, consent-scoped practice scheduler atop the canonical DragonPracticeLab.

An existing trusted scheduler calls pulse(). Creating a subscription does not
spawn a thread, network crawler, or background job. Every run is bounded by
authorization expiry, tick count, cooldown and the Lab's daily quota.
"""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3
from .dragon_practice_lab import DragonPracticeLab, PracticeAttempt, _owner, _time
from .dragon_native_targets import STYLES
from .dragon_native_projects import EMITTERS
from .dragon_native_practice import DragonNativePracticeLab, NativeAttempt


@dataclass(frozen=True)
class PracticeSubscription:
    owner: str
    enabled: bool
    expires_at: float
    next_due: float
    interval_seconds: int
    remaining_ticks: int
    demos_per_tick: int
    generation_mode: str = 'html'
    native_target: str = 'game_boy'
    native_style: str = 'arcade_score_attack'


class DragonPracticeCycles:
    def __init__(self, db: sqlite3.Connection, lab: DragonPracticeLab):
        if lab.db is not db:
            raise ValueError("practice controller and lab must share one canonical connection")
        self.db = db
        self.lab = lab
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_practice_cycles(
            owner TEXT PRIMARY KEY,enabled INTEGER NOT NULL,expires_at REAL NOT NULL,
            next_due REAL NOT NULL,interval_seconds INTEGER NOT NULL,
            remaining_ticks INTEGER NOT NULL,demos_per_tick INTEGER NOT NULL,
            generation_mode TEXT NOT NULL DEFAULT 'html',
            native_target TEXT NOT NULL DEFAULT 'game_boy',
            native_style TEXT NOT NULL DEFAULT 'arcade_score_attack')""")
        columns={r[1] for r in db.execute("PRAGMA table_info(dragon_practice_cycles)")}
        for column,definition in (
            ("generation_mode","TEXT NOT NULL DEFAULT 'html'"),
            ("native_target","TEXT NOT NULL DEFAULT 'game_boy'"),
            ("native_style","TEXT NOT NULL DEFAULT 'arcade_score_attack'"),
        ):
            if column not in columns:
                db.execute("ALTER TABLE dragon_practice_cycles ADD COLUMN "+column+" "+definition)
        db.commit()

    def enable(self, owner: str, *, authorized: bool, human_approved: bool,
               now: float, expires_at: float, interval_seconds: int = 3600,
               max_ticks: int = 24, demos_per_tick: int = 2,
               generation_mode: str = 'html',native_target: str = 'game_boy',
               native_style: str = 'arcade_score_attack') -> PracticeSubscription:
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
        if generation_mode not in ('html','native','curriculum'):
            raise ValueError("unsupported scheduled generation mode")
        if generation_mode=='native' and (native_target not in EMITTERS or native_style not in STYLES):
            raise ValueError("requested native target or style has no source emitter")
        with self.db:
            self.db.execute("""INSERT INTO dragon_practice_cycles
                (owner,enabled,expires_at,next_due,interval_seconds,remaining_ticks,
                 demos_per_tick,generation_mode,native_target,native_style)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(owner) DO UPDATE SET enabled=excluded.enabled,
                expires_at=excluded.expires_at,next_due=excluded.next_due,
                interval_seconds=excluded.interval_seconds,
                remaining_ticks=excluded.remaining_ticks,
                demos_per_tick=excluded.demos_per_tick,
                generation_mode=excluded.generation_mode,
                native_target=excluded.native_target,
                native_style=excluded.native_style""",
                (owner,1,expires_at,now,interval_seconds,max_ticks,demos_per_tick,
                 generation_mode,native_target,native_style))
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
            remaining_ticks,demos_per_tick,generation_mode,native_target,native_style FROM dragon_practice_cycles
            WHERE owner=?""",(owner,)).fetchone()
        if row is None:
            return PracticeSubscription(owner,False,0,0,3600,0,0)
        return PracticeSubscription(owner,bool(row[0]),row[1],row[2],row[3],row[4],row[5],row[6],row[7],row[8])

    def pulse(self, owner: str, *, authorized: bool,
              now: float) -> tuple[PracticeAttempt | NativeAttempt,...]:
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
                remaining_ticks,demos_per_tick,generation_mode,native_target,native_style
                FROM dragon_practice_cycles
                WHERE owner=?""",(owner,)).fetchone()
            if row is None:
                return ()
            enabled,expires,due,interval,remaining,demos,mode,target,style=row
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
        if mode in ('native','curriculum'):
            native=DragonNativePracticeLab(self.db,self.lab)
            course=None
            if mode=='curriculum':
                from .dragon_native_curriculum import DragonNativeCurriculum
                from .dragon_build_evidence import DragonBuildEvidence
                import os
                key_str=os.environ.get("SKL_DRAGON_BUILD_SIGNING_KEY_HEX","").strip()
                evidence=None
                if key_str:
                    try:
                        private_key=bytes.fromhex(key_str)
                    except ValueError:
                        raise PermissionError("invalid native evidence signing configuration") from None
                    evidence=DragonBuildEvidence(
                        self.db,native,private_signing_key=private_key)
                course=DragonNativeCurriculum(native,evidence)
            created=[]
            for _ in range(demos):
                # Every attempt changes the native exercise, never regenerates
                # an existing lesson/target/style merely to inflate workloads.
                # Keep the chosen genre honest; each attempt increments a
                # separately seeded challenge variant under the same target.
                try:
                    if course is not None:
                        _,attempt=course.generate_next(
                            owner,authorized=True,consent=True,now=now)
                        created.append(attempt)
                    else:
                        created.append(native.generate(
                            owner,target_id=target,style=style,
                            now=now,authorized=True,consent=True))
                except (PermissionError,ValueError):
                    break
            return tuple(created)
        return self.lab.run_batch(owner,authorized=True,consent=True,now=now,max_demos=demos)
