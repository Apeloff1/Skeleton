"""Legions — the zaibatsu's agent cohorts.

Port of gameforge-rs ``crates/gf-gameforge/src/legions.rs``. A legion is a
named body of workers sworn to a capability (rendering, indexing, scouting).
Cohorts hold members with rank and heartbeat; commanders draw assignments
from the swarm DAG. Byzantine posture: members that miss heartbeats are
degraded, and a member whose attestations repeatedly diverge in court can
be cashiered as a traitor — the legion marches on without them.

This is the forge-path cashier/cohort registry, **not** the omega
``LegionCommand`` specialty roster under ``backend/gameforge/omega/legions.py``.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Member:
    """One sworn worker inside a capability cohort."""

    id: str
    rank: int
    capability: str
    sworn_at: float
    last_heartbeat: float
    tasks_done: int = 0
    traitor: bool = False


@dataclass
class Cohort:
    """Members sharing one capability under a legion."""

    id: str
    capability: str
    members: list[Member] = field(default_factory=list)


@dataclass
class Legion:
    """Named body of cohorts sworn to the empire."""

    id: str
    name: str
    motto: str
    cohorts: list[Cohort] = field(default_factory=list)
    founded: float = 0.0


class LegionRegistry:
    """In-memory legion / cohort / member registry (RS LegionRegistry)."""

    def __init__(self, *, clock: Optional[Callable[[], float]] = None) -> None:
        self._now = clock or time.time
        self._lock = threading.RLock()
        self._legions: dict[str, Legion] = {}
        self.enlisted_total: int = 0
        self.cashiered_total: int = 0

    def found(self, name: str, motto: str) -> Legion:
        """Found a legion. Names are unique within the empire (last write wins)."""
        legion = Legion(
            id=str(uuid.uuid4()),
            name=name,
            motto=motto,
            cohorts=[],
            founded=self._now(),
        )
        with self._lock:
            self._legions[legion.name] = legion
        return legion

    def enlist(self, legion_name: str, capability: str) -> Optional[str]:
        """Swear a member into the cohort matching ``capability``, raising it if needed.

        Returns the member id, or None if the legion is unknown.
        """
        with self._lock:
            legion = self._legions.get(legion_name)
            if legion is None:
                return None
            if not any(c.capability == capability for c in legion.cohorts):
                legion.cohorts.append(
                    Cohort(id=str(uuid.uuid4()), capability=capability, members=[])
                )
            cohort = next(c for c in legion.cohorts if c.capability == capability)
            now = self._now()
            member = Member(
                id=str(uuid.uuid4()),
                rank=1,
                capability=capability,
                sworn_at=now,
                last_heartbeat=now,
                tasks_done=0,
                traitor=False,
            )
            cohort.members.append(member)
            self.enlisted_total += 1
            return member.id

    def heartbeat(self, legion_name: str, member_id: str) -> bool:
        """Prove the member lives. Missed beats are detected by ``degrade_silent``."""
        with self._lock:
            legion = self._legions.get(legion_name)
            if legion is None:
                return False
            for cohort in legion.cohorts:
                for m in cohort.members:
                    if m.id == member_id:
                        m.last_heartbeat = self._now()
                        return True
            return False

    def cashier(self, legion_name: str, member_id: str) -> bool:
        """Cashier a member whose court attestations diverged — byzantine expulsion."""
        with self._lock:
            legion = self._legions.get(legion_name)
            if legion is None:
                return False
            for cohort in legion.cohorts:
                for m in cohort.members:
                    if m.id == member_id and not m.traitor:
                        m.traitor = True
                        self.cashiered_total += 1
                        return True
            return False

    def promote(self, legion_name: str, member_id: str) -> bool:
        """Promote a member that has proven itself in tasks done."""
        with self._lock:
            legion = self._legions.get(legion_name)
            if legion is None:
                return False
            for cohort in legion.cohorts:
                for m in cohort.members:
                    if m.id == member_id and not m.traitor:
                        m.rank += 1
                        return True
            return False

    def degrade_silent(self, max_silence_secs: float) -> int:
        """Degrade members silent longer than ``max_silence_secs`` (rank > 1 only)."""
        now = self._now()
        degraded = 0
        with self._lock:
            for legion in self._legions.values():
                for cohort in legion.cohorts:
                    for m in cohort.members:
                        if (
                            not m.traitor
                            and m.rank > 1
                            and (now - m.last_heartbeat) > max_silence_secs
                        ):
                            m.rank -= 1
                            degraded += 1
        return degraded

    def get(self, name: str) -> Optional[Legion]:
        with self._lock:
            legion = self._legions.get(name)
            return legion

    def list(self) -> list[Legion]:
        with self._lock:
            return list(self._legions.values())

    def fit_for(self, capability: str) -> list[tuple[str, Member]]:
        """Fit non-traitor members for a capability, highest rank first."""
        out: list[tuple[str, Member]] = []
        with self._lock:
            for legion in self._legions.values():
                for cohort in legion.cohorts:
                    if cohort.capability != capability:
                        continue
                    for m in cohort.members:
                        if not m.traitor:
                            out.append((legion.name, m))
        out.sort(key=lambda pair: pair[1].rank, reverse=True)
        return out


__all__ = [
    "Member",
    "Cohort",
    "Legion",
    "LegionRegistry",
]
