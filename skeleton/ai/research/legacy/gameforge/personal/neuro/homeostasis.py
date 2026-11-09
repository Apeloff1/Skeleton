from __future__ import annotations
"""
Homeostasis Engine — single equilibrium across psychological, patient, schedule logs.
Can lock scheduling when baseline is unsafe.
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class HomeostasisReport:
    equilibrium: float  # 0..1 higher is better
    status: str  # balanced | strained | critical
    schedule_locked: bool
    reasons: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    components: Dict[str, float] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class HomeostasisEngine:
    def __init__(self, lock_threshold: float = 0.35):
        self.lock_threshold = lock_threshold
        self._locked = False
        self._last: Optional[HomeostasisReport] = None

    @property
    def schedule_locked(self) -> bool:
        return self._locked

    def evaluate(
        self,
        *,
        sleep_hours: float = 7.0,
        pain_level: float = 0.0,  # 0..1 from patient log
        affect_valence: float = 0.1,
        affect_energy: float = 0.55,
        adenosine: float = 0.3,
        stress_hints: int = 0,
        social_drain: float = 0.0,  # 0..1
    ) -> HomeostasisReport:
        reasons: List[str] = []
        actions: List[str] = []

        # component scores 0..1 (higher better)
        sleep_c = max(0.0, min(1.0, sleep_hours / 8.0))
        pain_c = max(0.0, 1.0 - pain_level)
        mood_c = max(0.0, min(1.0, (affect_valence + 1.0) / 2.0))
        energy_c = max(0.0, min(1.0, affect_energy))
        fatigue_c = max(0.0, 1.0 - adenosine)
        stress_c = max(0.0, 1.0 - min(1.0, stress_hints / 5.0))
        social_c = max(0.0, 1.0 - social_drain)

        components = {
            "sleep": round(sleep_c, 3),
            "pain": round(pain_c, 3),
            "mood": round(mood_c, 3),
            "energy": round(energy_c, 3),
            "fatigue": round(fatigue_c, 3),
            "stress": round(stress_c, 3),
            "social": round(social_c, 3),
        }

        # weighted equilibrium
        eq = (
            0.22 * sleep_c
            + 0.18 * pain_c
            + 0.15 * mood_c
            + 0.15 * energy_c
            + 0.12 * fatigue_c
            + 0.10 * stress_c
            + 0.08 * social_c
        )

        if sleep_hours < 5.5:
            reasons.append("low_sleep")
            actions.append("Prioritize rest before new commitments.")
        if pain_level >= 0.6:
            reasons.append("elevated_pain")
            actions.append("Reduce physical and cognitive load; patient care first.")
        if affect_valence < -0.25:
            reasons.append("low_valence")
            actions.append("Keep interactions warm and lists short.")
        if adenosine >= 0.7:
            reasons.append("high_adenosine")
            actions.append("Cut task capacity; prefer recovery blocks.")
        if stress_hints >= 3:
            reasons.append("stress_cluster")
            actions.append("Insert grounding; defer non-essential work.")

        if eq < self.lock_threshold or (pain_level >= 0.7 and sleep_hours < 6.0):
            status = "critical"
            locked = True
            actions.insert(0, "Scheduling locked until baseline recovers.")
            reasons.append("homeostasis_lock")
        elif eq < 0.55:
            status = "strained"
            locked = False
            actions.append("Soft limit: avoid adding high-stakes tasks.")
        else:
            status = "balanced"
            locked = False

        self._locked = locked
        report = HomeostasisReport(
            equilibrium=round(eq, 3),
            status=status,
            schedule_locked=locked,
            reasons=reasons,
            actions=actions,
            components=components,
        )
        self._last = report
        return report

    def assert_can_schedule(self) -> Dict[str, Any]:
        if self._locked:
            return {
                "allowed": False,
                "reason": "Homeostasis lock active — recover baseline before adding tasks.",
                "report": self._last.to_dict() if self._last else None,
            }
        return {"allowed": True, "report": self._last.to_dict() if self._last else None}
