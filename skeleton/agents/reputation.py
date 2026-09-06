"""Agent reputation — sliding-window scores + deed ledger.

Port of gameforge-rs ``crates/gf-gameforge/src/reputation.rs``. Standing is
earned slowly and lost quickly: it moves on a bounded logistic curve, so no
single deed makes a magnate and no single failure ruins a house — but a
pattern of either is unmistakable. Court suspects (divergent attesters) are
the heaviest drag: lying to the court is the one sin the empire does not
forgive cheaply.

Reputation is read-only to the outside: courts and routes *report* deeds,
they never set scores. The ledger of deeds is bounded and the standing is
always derivable from it — a projection, not a truth.

Legacy :class:`ReputationTable` (success/attempt sliding window) is preserved
extend-only so existing ``score()`` callers (e.g. TaskRouter) keep working.
The deed ledger is the forge-path write surface; the table remains a separate
attempt projection, not a rewrite of the attempt API.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

from skeleton.kernel.errors import AgentError

DEED_CAP = 4096
_HALF_LIFE_DAYS = 90.0


class ReputationError(AgentError):
    code = "AGT.REPUTATION"


# ---------------------------------------------------------------------------
# Legacy sliding-window projection (unchanged public surface)
# ---------------------------------------------------------------------------


@dataclass
class ReputationScore:
    successes: int = 0
    attempts: int = 0
    last_event_at: float = 0.0

    def score(self) -> float:
        if self.attempts == 0:
            return 0.0
        return self.successes / self.attempts


class ReputationTable:
    """Per-agent reputation register with decay.

    Success/attempt API preserved for TaskRouter and other callers.
    """

    def __init__(
        self, *, decay_half_life_s: float = 86400.0, clock: Optional[Callable[[], float]] = None
    ) -> None:
        self._half_life = decay_half_life_s
        self._now = clock or time.monotonic
        self._records: Dict[str, ReputationScore] = {}

    def record(self, agent: str, success: bool) -> ReputationScore:
        rec = self._records.setdefault(agent, ReputationScore())
        rec.attempts += 1
        if success:
            rec.successes += 1
        rec.last_event_at = self._now()
        return rec

    def score(self, agent: str) -> float:
        rec = self._records.get(agent)
        if rec is None:
            raise ReputationError("unknown agent", context={"agent": agent})
        return rec.score()

    def decay_sweep(self) -> None:
        """Number attempts/successes toward zero over time."""
        now = self._now()
        for rec in self._records.values():
            age_s = now - rec.last_event_at
            if age_s <= 0:
                continue
            steps = int(age_s / self._half_life)
            if steps > 0:
                rec.attempts = max(0, rec.attempts - steps)
                rec.successes = max(0, rec.successes - steps)
                rec.last_event_at = now

    def snapshot(self) -> Dict[str, float]:
        return {agent: rec.score() for agent, rec in self._records.items()}


# ---------------------------------------------------------------------------
# Deed ledger (gameforge-rs reputation.rs port)
# ---------------------------------------------------------------------------


class DeedKind(str, Enum):
    """Kind of deed reported to the court."""

    SERVICE = "service"  # Duty done well
    DISTINCTION = "distinction"  # Exceptional act
    LAPSE = "lapse"  # Minor breach
    TREASON = "treason"  # Diverged from decided quorum

    def base_delta(self) -> float:
        if self is DeedKind.SERVICE:
            return 0.15
        if self is DeedKind.DISTINCTION:
            return 0.45
        if self is DeedKind.LAPSE:
            return -0.35
        return -1.6  # TREASON


@dataclass(frozen=True)
class Deed:
    """One immutable ledger line — courts report deeds, never scores."""

    actor: str
    kind: DeedKind
    weight: float  # 0.0..=1.0 magnitude
    at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "kind": self.kind.value,
            "weight": self.weight,
            "at": self.at,
        }


class Reputation:
    """In-process deed ledger.

    The only write path is :meth:`record`. Standing is always a logistic
    projection over weighted, time-decayed deeds (quarter-year half-life).
    Thread-safe via a single RLock (mirrors the RS RwLock).
    """

    def __init__(self, *, clock: Optional[Callable[[], float]] = None) -> None:
        self._lock = threading.RLock()
        self._deeds: list[Deed] = []
        self._now = clock or time.time

    def record(self, actor: str, kind: DeedKind, weight: float = 1.0) -> Deed:
        """Record a deed. Scores are never assigned — only deeds are written."""
        if not isinstance(kind, DeedKind):
            raise ReputationError(
                "unknown deed kind",
                context={"kind": repr(kind)},
            )
        clamped = max(0.0, min(1.0, float(weight)))
        deed = Deed(actor=actor, kind=kind, weight=clamped, at=self._now())
        with self._lock:
            if len(self._deeds) >= DEED_CAP:
                # Drop oldest quarter when the roll fills (RS drain).
                del self._deeds[0 : DEED_CAP // 4]
            self._deeds.append(deed)
        return deed

    def standing(self, actor: str) -> float:
        """Standing in [-1, 1]: logistic over weighted deeds with half-life.

        Recent deeds speak louder; ancient deeds are rumor.
        """
        now = self._now()
        score = 0.0
        with self._lock:
            for d in self._deeds:
                if d.actor != actor:
                    continue
                days = max(0.0, (now - d.at) / 86400.0)
                decay = 0.5 ** (days / _HALF_LIFE_DAYS)
                score += d.kind.base_delta() * d.weight * decay
        return math.tanh(score / 4.0)

    def ledger_of(self, actor: str, limit: int = 64) -> list[Deed]:
        """An actor's deeds, newest first."""
        if limit < 0:
            limit = 0
        with self._lock:
            matched = [d for d in self._deeds if d.actor == actor]
        matched.reverse()
        return matched[:limit]

    def roll(self) -> dict[str, dict[str, int]]:
        """The roll of honor and shame: per-actor good/bad deed counts."""
        actors: dict[str, dict[str, int]] = {}
        with self._lock:
            for d in self._deeds:
                entry = actors.setdefault(d.actor, {"good": 0, "bad": 0})
                if d.kind in (DeedKind.SERVICE, DeedKind.DISTINCTION):
                    entry["good"] += 1
                else:
                    entry["bad"] += 1
        return actors
