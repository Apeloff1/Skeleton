"""Agent reputation — sliding-window score tracking.

Meshes pick agents with the best recent history; reputation is an
explicit, time-decayed signal over successes vs attempts. Slotted
windows give a rolling summary instead of wholesale averages.

- :class:`ReputationScore` — per-agent counter
- :class:`ReputationTable` — per-agent scores with decay sweeps
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

from skeleton.kernel.errors import AgentError


class ReputationError(AgentError):
    code = "AGT.REPUTATION"


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
    """Per-agent reputation register with decay."""

    def __init__(self, *, decay_half_life_s: float = 86400.0, clock: Optional[Callable[[], float]] = None) -> None:
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
