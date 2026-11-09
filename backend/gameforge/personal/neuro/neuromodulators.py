from __future__ import annotations
"""
Neuromodulator Simulator — dopamine (motivation/reward) + adenosine (fatigue).
Dynamically scales daily task capacity from sleep and progress history.
"""

from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional
import math


@dataclass
class NeuromodulatorState:
    day: str
    dopamine: float  # 0..1 motivation / reward sensitivity
    adenosine: float  # 0..1 fatigue pressure
    sleep_hours: float
    capacity_scale: float  # multiply nominal task load
    max_tasks: int
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class NeuromodulatorSimulator:
    def __init__(
        self,
        baseline_tasks: int = 8,
        min_tasks: int = 2,
        max_tasks: int = 12,
    ):
        self.baseline_tasks = baseline_tasks
        self.min_tasks = min_tasks
        self.max_tasks = max_tasks
        self._reward_events: List[float] = []  # recent reward magnitudes
        self._last_state: Optional[NeuromodulatorState] = None

    def register_reward(self, magnitude: float = 0.3):
        """Call on completed milestones / positive wins."""
        self._reward_events.append(max(0.0, min(1.0, magnitude)))
        if len(self._reward_events) > 30:
            self._reward_events = self._reward_events[-30:]

    def compute(
        self,
        *,
        sleep_hours: float = 7.0,
        affect_energy: float = 0.55,
        affect_valence: float = 0.1,
        progress_delta: float = 0.0,  # % points gained recently
    ) -> NeuromodulatorState:
        notes: List[str] = []

        # Adenosine rises when sleep is short
        if sleep_hours >= 7.5:
            adenosine = 0.2
        elif sleep_hours >= 6.0:
            adenosine = 0.45
            notes.append("moderate_sleep_debt")
        elif sleep_hours >= 4.5:
            adenosine = 0.7
            notes.append("significant_sleep_debt")
        else:
            adenosine = 0.9
            notes.append("severe_sleep_debt")

        # Dopamine from rewards + valence + progress
        recent = self._reward_events[-5:]
        reward_avg = sum(recent) / len(recent) if recent else 0.25
        dopamine = 0.35 + 0.35 * reward_avg + 0.15 * max(0, affect_valence) + 0.1 * min(1.0, progress_delta / 20.0)
        dopamine = max(0.05, min(1.0, dopamine + 0.1 * (affect_energy - 0.5)))

        # Capacity formula: protect energy when adenosine high
        # If sleep low → cut capacity (user asked: half on low sleep)
        if sleep_hours < 5.5:
            capacity_scale = 0.5
            notes.append("capacity_halved_for_sleep")
        elif sleep_hours < 6.5:
            capacity_scale = 0.7
            notes.append("capacity_reduced_for_sleep")
        else:
            capacity_scale = 0.85 + 0.25 * dopamine - 0.35 * adenosine
            capacity_scale = max(0.4, min(1.2, capacity_scale))

        # blend affect energy
        capacity_scale *= 0.7 + 0.3 * affect_energy
        capacity_scale = max(0.35, min(1.25, capacity_scale))

        max_tasks = int(round(self.baseline_tasks * capacity_scale))
        max_tasks = max(self.min_tasks, min(self.max_tasks, max_tasks))

        if adenosine > 0.65:
            notes.append("prefer_low_cognition_tasks")
        if dopamine > 0.7 and adenosine < 0.4:
            notes.append("good_window_for_hard_work")

        state = NeuromodulatorState(
            day=date.today().isoformat(),
            dopamine=round(dopamine, 3),
            adenosine=round(adenosine, 3),
            sleep_hours=sleep_hours,
            capacity_scale=round(capacity_scale, 3),
            max_tasks=max_tasks,
            notes=notes,
        )
        self._last_state = state
        return state

    def adjust_schedule_limit(self, scheduled_count: int, state: Optional[NeuromodulatorState] = None) -> Dict[str, Any]:
        st = state or self._last_state or self.compute()
        over = scheduled_count > st.max_tasks
        return {
            "max_tasks": st.max_tasks,
            "scheduled": scheduled_count,
            "over_capacity": over,
            "suggestion": (
                f"Defer {scheduled_count - st.max_tasks} task(s); protect energy today."
                if over
                else "Within capacity."
            ),
            "state": st.to_dict(),
        }
