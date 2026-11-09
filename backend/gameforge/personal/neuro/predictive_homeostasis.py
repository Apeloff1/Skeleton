from __future__ import annotations
"""
Predictive Homeostasis — forecast equilibrium risk before the day collapses.
Uses recent trajectory (sleep, pain, valence, adenosine, weather stress) to
project hours-ahead risk and recommend preemptive load cuts.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import math


@dataclass
class TrajectoryPoint:
    ts: str
    sleep_hours: float
    pain: float
    valence: float
    energy: float
    adenosine: float
    noise_db: float
    weather_stress: float  # 0..1
    equilibrium: float


@dataclass
class PredictiveHomeostasisReport:
    day: str
    current_eq: float
    predicted_eq_6h: float
    predicted_eq_24h: float
    risk_level: str  # low | elevated | high | critical
    trend: str  # improving | stable | declining
    hours_to_lock_risk: Optional[float]
    preemptive_actions: List[str] = field(default_factory=list)
    confidence: float = 0.5
    components_forecast: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class PredictiveHomeostasisEngine:
    def __init__(self, lock_threshold: float = 0.35, horizon_hours: int = 24):
        self.lock_threshold = lock_threshold
        self.horizon_hours = horizon_hours
        self.history: List[TrajectoryPoint] = []

    def observe(
        self,
        *,
        sleep_hours: float,
        pain: float,
        valence: float,
        energy: float,
        adenosine: float,
        noise_db: float = 45.0,
        weather_condition: str = "clear",
        equilibrium: Optional[float] = None,
    ):
        wx_stress = {
            "clear": 0.1,
            "clouds": 0.2,
            "fog": 0.35,
            "rain": 0.45,
            "snow": 0.4,
            "storm": 0.7,
        }.get((weather_condition or "clear").lower(), 0.25)
        if equilibrium is None:
            equilibrium = self._instant_eq(sleep_hours, pain, valence, energy, adenosine, noise_db, wx_stress)
        self.history.append(
            TrajectoryPoint(
                ts=datetime.utcnow().isoformat(),
                sleep_hours=sleep_hours,
                pain=pain,
                valence=valence,
                energy=energy,
                adenosine=adenosine,
                noise_db=noise_db,
                weather_stress=wx_stress,
                equilibrium=equilibrium,
            )
        )
        if len(self.history) > 200:
            self.history = self.history[-200:]

    def _instant_eq(self, sleep, pain, valence, energy, adenosine, noise, wx_stress) -> float:
        sleep_c = max(0.0, min(1.0, sleep / 8.0))
        pain_c = max(0.0, 1.0 - pain)
        mood_c = max(0.0, min(1.0, (valence + 1.0) / 2.0))
        energy_c = max(0.0, min(1.0, energy))
        fatigue_c = max(0.0, 1.0 - adenosine)
        noise_c = max(0.0, 1.0 - max(0.0, (noise - 40) / 50.0))
        wx_c = max(0.0, 1.0 - wx_stress)
        return (
            0.2 * sleep_c
            + 0.18 * pain_c
            + 0.14 * mood_c
            + 0.14 * energy_c
            + 0.12 * fatigue_c
            + 0.12 * noise_c
            + 0.1 * wx_c
        )

    def _slope(self, values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        n = len(values)
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(values) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
        den = sum((x - mean_x) ** 2 for x in xs) or 1.0
        return num / den

    def forecast(
        self,
        *,
        sleep_hours: float,
        pain: float,
        valence: float,
        energy: float,
        adenosine: float,
        noise_db: float = 45.0,
        weather_condition: str = "clear",
    ) -> PredictiveHomeostasisReport:
        self.observe(
            sleep_hours=sleep_hours,
            pain=pain,
            valence=valence,
            energy=energy,
            adenosine=adenosine,
            noise_db=noise_db,
            weather_condition=weather_condition,
        )
        current = self.history[-1].equilibrium
        eqs = [p.equilibrium for p in self.history[-12:]]
        slope = self._slope(eqs)  # per observation step (~session)

        # project: adenosine rises through day if sleep was short; energy drifts with slope
        aden_6 = min(1.0, adenosine + (0.08 if sleep_hours < 6.5 else 0.03))
        aden_24 = min(1.0, adenosine + (0.15 if sleep_hours < 6.5 else 0.05))
        energy_6 = max(0.0, energy + slope * 2)
        energy_24 = max(0.0, energy + slope * 5)
        # overnight recovery if sleep expected normal — conservative: assume same sleep
        pred_6 = self._instant_eq(sleep_hours, pain, valence, energy_6, aden_6, noise_db,
                                  self.history[-1].weather_stress)
        pred_24 = self._instant_eq(
            min(8.0, sleep_hours + 0.5),  # mild recovery hope
            max(0.0, pain - 0.05),
            valence + slope * 0.5,
            energy_24,
            aden_24 * 0.85,
            noise_db,
            self.history[-1].weather_stress,
        )

        # blend trajectory slope into predictions
        pred_6 = max(0.0, min(1.0, 0.7 * pred_6 + 0.3 * (current + slope * 3)))
        pred_24 = max(0.0, min(1.0, 0.6 * pred_24 + 0.4 * (current + slope * 8)))

        if slope < -0.02:
            trend = "declining"
        elif slope > 0.02:
            trend = "improving"
        else:
            trend = "stable"

        # hours to lock risk if declining
        hours_to_lock = None
        if slope < 0 and current > self.lock_threshold:
            # crude linear time-to-threshold
            steps = (current - self.lock_threshold) / abs(slope) if slope else 999
            hours_to_lock = round(min(48.0, max(0.5, steps * 2.0)), 1)

        risk = "low"
        if pred_6 < self.lock_threshold or current < self.lock_threshold:
            risk = "critical"
        elif pred_24 < self.lock_threshold + 0.1 or pred_6 < 0.5:
            risk = "high"
        elif pred_24 < 0.55 or trend == "declining":
            risk = "elevated"

        actions: List[str] = []
        if risk in ("high", "critical"):
            actions.append("Preemptively cut non-essential tasks before capacity collapses.")
        if hours_to_lock is not None and hours_to_lock < 12:
            actions.append(f"~{hours_to_lock}h until lock-risk if trend continues — schedule recovery block now.")
        if sleep_hours < 6.0:
            actions.append("Protect sleep tonight; predictive model weights sleep debt heavily.")
        if pain >= 0.5:
            actions.append("Pain elevated — avoid stacking high-load commitments.")
        if noise_db >= 55:
            actions.append("Noise load high — prefer quiet environment or low-cognition work.")
        if not actions:
            actions.append("Trajectory stable — maintain gentle positive structure.")

        conf = min(0.95, 0.35 + 0.05 * len(self.history))

        return PredictiveHomeostasisReport(
            day=date.today().isoformat(),
            current_eq=round(current, 3),
            predicted_eq_6h=round(pred_6, 3),
            predicted_eq_24h=round(pred_24, 3),
            risk_level=risk,
            trend=trend,
            hours_to_lock_risk=hours_to_lock,
            preemptive_actions=actions,
            confidence=round(conf, 2),
            components_forecast={
                "adenosine_6h": round(aden_6, 3),
                "adenosine_24h": round(aden_24, 3),
                "energy_6h": round(energy_6, 3),
                "energy_24h": round(energy_24, 3),
                "slope": round(slope, 4),
            },
        )
