from __future__ import annotations
"""
Neuroplasticity Loops — pattern match past days to intervene before failure repeats.
"""

from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict


@dataclass
class PatternRule:
    rule_id: str
    description: str
    condition: Dict[str, Any]  # e.g. weather=rain, noise_db_gt=50
    effect: str  # e.g. progress_drop
    support: int  # how many historical hits
    intervention: str


@dataclass
class Intervention:
    active: bool
    rules_fired: List[str]
    message: str
    recommended_task_mode: str  # low_cognition | normal | high_focus
    details: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class NeuroplasticityEngine:
    """
    Learns simple associations:
      (weather condition, noise threshold, affect) → progress outcomes
    and fires preemptive interventions.
    """

    def __init__(self):
        self.history: List[Dict[str, Any]] = []  # daily feature rows
        self.min_support = 3

    def observe_day(
        self,
        d: date,
        *,
        weather_condition: str,
        noise_db: float,
        progress_delta: float,
        valence: float = 0.0,
        completed_ratio: float = 0.5,
    ):
        self.history.append(
            {
                "day": d.isoformat(),
                "weather": (weather_condition or "clear").lower(),
                "noise_db": float(noise_db),
                "progress_delta": float(progress_delta),
                "valence": float(valence),
                "completed_ratio": float(completed_ratio),
                "drop": progress_delta < 0 or completed_ratio < 0.35,
            }
        )
        if len(self.history) > 400:
            self.history = self.history[-400:]

    def mine_rules(self) -> List[PatternRule]:
        rules: List[PatternRule] = []
        # weather + high noise → drop
        buckets: Dict[Tuple[str, str], List[bool]] = defaultdict(list)
        for row in self.history:
            noise_bin = "high" if row["noise_db"] >= 50 else "low"
            key = (row["weather"], noise_bin)
            buckets[key].append(row["drop"])

        for (weather, noise_bin), drops in buckets.items():
            if len(drops) < self.min_support:
                continue
            rate = sum(1 for x in drops if x) / len(drops)
            if rate >= 0.55 and noise_bin == "high":
                rules.append(
                    PatternRule(
                        rule_id=f"wx_{weather}_noise_high",
                        description=f"Progress often drops when weather={weather} and noise≥50dB",
                        condition={"weather": weather, "noise_db_gt": 50},
                        effect="progress_drop",
                        support=len(drops),
                        intervention=(
                            f"It looks {weather} and noisy today; historically this cuts your focus. "
                            f"Let's shift to low-cognition tasks and protect the main milestone."
                        ),
                    )
                )
            if rate >= 0.55 and weather in ("rain", "storm") and noise_bin == "low":
                rules.append(
                    PatternRule(
                        rule_id=f"wx_{weather}_inward",
                        description=f"Rain/storm days correlate with lower completion",
                        condition={"weather": weather},
                        effect="progress_drop",
                        support=len(drops),
                        intervention=(
                            f"Weather is {weather}. Past you struggled a bit on days like this — "
                            f"one deep task max, then administrative or reflective work."
                        ),
                    )
                )

        # low valence clusters
        low_v = [r for r in self.history if r["valence"] < -0.2]
        if len(low_v) >= self.min_support:
            drop_rate = sum(1 for r in low_v if r["drop"]) / len(low_v)
            if drop_rate >= 0.5:
                rules.append(
                    PatternRule(
                        rule_id="low_valence_drop",
                        description="Low mood days associate with incomplete schedules",
                        condition={"valence_lt": -0.2},
                        effect="progress_drop",
                        support=len(low_v),
                        intervention=(
                            "Mood lean is soft today. Keep the list short and celebrate any single finish."
                        ),
                    )
                )
        return rules

    def intervene(
        self,
        *,
        weather_condition: str,
        noise_db: float,
        valence: float = 0.0,
    ) -> Intervention:
        rules = self.mine_rules()
        fired: List[PatternRule] = []
        wx = (weather_condition or "clear").lower()
        for rule in rules:
            cond = rule.condition
            ok = True
            if "weather" in cond and cond["weather"] != wx:
                ok = False
            if "noise_db_gt" in cond and not (noise_db >= cond["noise_db_gt"]):
                ok = False
            if "valence_lt" in cond and not (valence < cond["valence_lt"]):
                ok = False
            if ok:
                fired.append(rule)

        if not fired:
            return Intervention(
                active=False,
                rules_fired=[],
                message="No historical risk pattern matched for today.",
                recommended_task_mode="normal",
                details=[],
            )

        mode = "low_cognition"
        msg = fired[0].intervention
        if len(fired) > 1:
            msg += " Additional patterns also match — keep the day gentle."
        return Intervention(
            active=True,
            rules_fired=[r.rule_id for r in fired],
            message=msg,
            recommended_task_mode=mode,
            details=[asdict(r) for r in fired],
        )
