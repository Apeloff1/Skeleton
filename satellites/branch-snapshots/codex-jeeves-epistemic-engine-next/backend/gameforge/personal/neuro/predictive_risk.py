from __future__ import annotations
"""
Predictive risk algorithms — multi-horizon risk scoring beyond homeostasis equilibrium.
Combines schedule load, sleep debt, plasticity failure rates, budget burn, and volatility.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional
import math
import statistics


@dataclass
class RiskFactor:
    name: str
    score: float  # 0..1 higher = more risk
    weight: float
    evidence: str


@dataclass
class PredictiveRiskReport:
    day: str
    overall_risk: float  # 0..1
    level: str  # low | moderate | high | severe
    horizon_6h: float
    horizon_24h: float
    horizon_7d: float
    factors: List[Dict[str, Any]] = field(default_factory=list)
    mitigations: List[str] = field(default_factory=list)
    confidence: float = 0.5

    def to_dict(self) -> dict:
        return asdict(self)


class PredictiveRiskEngine:
    def __init__(self):
        self._eq_series: List[float] = []
        self._progress_series: List[float] = []
        self._task_overruns: List[float] = []

    def observe_equilibrium(self, eq: float):
        self._eq_series.append(eq)
        if len(self._eq_series) > 60:
            self._eq_series = self._eq_series[-60:]

    def observe_progress_delta(self, delta: float):
        self._progress_series.append(delta)
        if len(self._progress_series) > 60:
            self._progress_series = self._progress_series[-60:]

    def observe_overrun(self, ratio: float):
        self._task_overruns.append(ratio)
        if len(self._task_overruns) > 60:
            self._task_overruns = self._task_overruns[-60:]

    def _vol(self, xs: List[float]) -> float:
        if len(xs) < 2:
            return 0.0
        try:
            return float(statistics.pstdev(xs))
        except Exception:
            return 0.0

    def assess(
        self,
        *,
        sleep_hours: float = 7.0,
        pain: float = 0.0,
        valence: float = 0.0,
        energy: float = 0.55,
        adenosine: float = 0.3,
        scheduled_count: int = 0,
        max_tasks: int = 8,
        predictive_eq_6h: float = 0.6,
        predictive_eq_24h: float = 0.6,
        plasticity_active: bool = False,
        budget_utilization: float = 0.0,  # 0..1
        noise_db: float = 45.0,
    ) -> PredictiveRiskReport:
        factors: List[RiskFactor] = []

        sleep_risk = max(0.0, min(1.0, (7.0 - sleep_hours) / 5.0))
        factors.append(RiskFactor("sleep_debt", sleep_risk, 0.18, f"sleep={sleep_hours}h"))

        load_ratio = scheduled_count / max(1, max_tasks)
        load_risk = max(0.0, min(1.0, load_ratio - 0.5) * 2)
        factors.append(RiskFactor("schedule_load", load_risk, 0.16, f"{scheduled_count}/{max_tasks}"))

        eq_vol = self._vol(self._eq_series)
        factors.append(RiskFactor("equilibrium_volatility", min(1.0, eq_vol * 4), 0.12, f"vol={eq_vol:.3f}"))

        pain_risk = max(0.0, min(1.0, pain))
        factors.append(RiskFactor("pain", pain_risk, 0.12, f"pain={pain}"))

        mood_risk = max(0.0, min(1.0, (-valence) * 0.8)) if valence < 0 else 0.0
        factors.append(RiskFactor("mood_drag", mood_risk, 0.1, f"valence={valence}"))

        fatigue_risk = max(0.0, min(1.0, adenosine))
        factors.append(RiskFactor("fatigue", fatigue_risk, 0.1, f"adenosine={adenosine}"))

        eq6_risk = max(0.0, min(1.0, (0.55 - predictive_eq_6h) * 2))
        factors.append(RiskFactor("forecast_6h", eq6_risk, 0.1, f"eq6={predictive_eq_6h}"))

        plast_risk = 0.35 if plasticity_active else 0.0
        factors.append(RiskFactor("historical_failure_pattern", plast_risk, 0.06, "plasticity_match" if plasticity_active else "none"))

        budget_risk = max(0.0, min(1.0, (budget_utilization - 0.7) / 0.3)) if budget_utilization > 0.7 else 0.0
        factors.append(RiskFactor("budget_pressure", budget_risk, 0.04, f"util={budget_utilization:.2f}"))

        noise_risk = max(0.0, min(1.0, (noise_db - 50) / 30.0))
        factors.append(RiskFactor("noise_load", noise_risk, 0.02, f"noise={noise_db}"))

        overall = sum(f.score * f.weight for f in factors)
        overall = max(0.0, min(1.0, overall))

        # horizons: near-term weights fatigue/load more; 7d weights volatility/budget
        h6 = max(0.0, min(1.0, 0.5 * overall + 0.3 * fatigue_risk + 0.2 * load_risk))
        h24 = max(0.0, min(1.0, 0.45 * overall + 0.25 * eq6_risk + 0.15 * sleep_risk + 0.15 * plast_risk))
        h7 = max(0.0, min(1.0, 0.4 * overall + 0.25 * eq_vol * 4 + 0.2 * budget_risk + 0.15 * sleep_risk))

        if overall >= 0.75:
            level = "severe"
        elif overall >= 0.55:
            level = "high"
        elif overall >= 0.35:
            level = "moderate"
        else:
            level = "low"

        mitigations: List[str] = []
        if sleep_risk > 0.4:
            mitigations.append("Protect sleep window; cut evening load.")
        if load_risk > 0.4:
            mitigations.append("Defer lowest-priority tasks below capacity ceiling.")
        if plast_risk > 0:
            mitigations.append("Historical pattern day — prefer low-cognition work.")
        if budget_risk > 0:
            mitigations.append("Budget utilization high — freeze discretionary spend items.")
        if eq6_risk > 0.4:
            mitigations.append("6h equilibrium forecast weak — insert recovery block.")
        if not mitigations:
            mitigations.append("Risk contained — maintain steady execution.")

        conf = min(0.95, 0.4 + 0.01 * len(self._eq_series) + 0.01 * len(self._progress_series))

        return PredictiveRiskReport(
            day=date.today().isoformat(),
            overall_risk=round(overall, 3),
            level=level,
            horizon_6h=round(h6, 3),
            horizon_24h=round(h24, 3),
            horizon_7d=round(h7, 3),
            factors=[asdict(f) for f in factors],
            mitigations=mitigations,
            confidence=round(conf, 2),
        )
