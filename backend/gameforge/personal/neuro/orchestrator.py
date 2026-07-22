from __future__ import annotations
"""
Neuro stack orchestrator — salience, neuromodulators, plasticity, consolidation, homeostasis.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from gameforge.personal.neuro.salience import SalienceNetwork
from gameforge.personal.neuro.neuromodulators import NeuromodulatorSimulator
from gameforge.personal.neuro.neuroplasticity import NeuroplasticityEngine
from gameforge.personal.neuro.consolidation import SleepConsolidationRoutine
from gameforge.personal.neuro.homeostasis import HomeostasisEngine
from gameforge.personal.neuro.predictive_homeostasis import PredictiveHomeostasisEngine
from gameforge.personal.neuro.predictive_risk import PredictiveRiskEngine


class NeuroOrchestrator:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.salience = SalienceNetwork()
        self.neuromod = NeuromodulatorSimulator()
        self.plasticity = NeuroplasticityEngine()
        self.consolidation = SleepConsolidationRoutine(user_id, self.salience)
        self.homeostasis = HomeostasisEngine()
        self.predictive = PredictiveHomeostasisEngine()
        self.risk = PredictiveRiskEngine()

    def filter_transcripts(self, segments: List[str]) -> Dict[str, Any]:
        kept, dropped = self.salience.filter_batch(segments)
        return {
            "kept": [k.to_dict() for k in kept],
            "dropped_count": len(dropped),
            "kept_count": len(kept),
        }

    def daily_control_plane(
        self,
        *,
        sleep_hours: float = 7.0,
        weather_condition: str = "clear",
        noise_db: float = 45.0,
        affect_energy: float = 0.55,
        affect_valence: float = 0.1,
        pain_level: float = 0.0,
        progress_delta: float = 0.0,
        scheduled_count: int = 0,
        stress_hints: int = 0,
    ) -> Dict[str, Any]:
        neuro = self.neuromod.compute(
            sleep_hours=sleep_hours,
            affect_energy=affect_energy,
            affect_valence=affect_valence,
            progress_delta=progress_delta,
        )
        cap = self.neuromod.adjust_schedule_limit(scheduled_count, neuro)

        # plasticity observation + intervention
        self.plasticity.observe_day(
            date.today(),
            weather_condition=weather_condition,
            noise_db=noise_db,
            progress_delta=progress_delta,
            valence=affect_valence,
        )
        intervention = self.plasticity.intervene(
            weather_condition=weather_condition,
            noise_db=noise_db,
            valence=affect_valence,
        )

        homeo = self.homeostasis.evaluate(
            sleep_hours=sleep_hours,
            pain_level=pain_level,
            affect_valence=affect_valence,
            affect_energy=affect_energy,
            adenosine=neuro.adenosine,
            stress_hints=stress_hints,
        )

        schedule_gate = self.homeostasis.assert_can_schedule()
        if intervention.active and intervention.recommended_task_mode == "low_cognition":
            # further soften capacity
            neuro.max_tasks = max(2, int(neuro.max_tasks * 0.75))
            cap = self.neuromod.adjust_schedule_limit(scheduled_count, neuro)

        pred = self.predictive.forecast(
            sleep_hours=sleep_hours,
            pain=pain_level,
            valence=affect_valence,
            energy=affect_energy,
            adenosine=neuro.adenosine,
            noise_db=noise_db,
            weather_condition=weather_condition,
        )
        self.risk.observe_equilibrium(homeo.equilibrium)
        risk_report = self.risk.assess(
            sleep_hours=sleep_hours,
            pain=pain_level,
            valence=affect_valence,
            energy=affect_energy,
            adenosine=neuro.adenosine,
            scheduled_count=scheduled_count,
            max_tasks=neuro.max_tasks,
            predictive_eq_6h=pred.predicted_eq_6h,
            predictive_eq_24h=pred.predicted_eq_24h,
            plasticity_active=intervention.active,
            noise_db=noise_db,
        )
        directives = self._directives(neuro, intervention, homeo)
        if risk_report.level in ("high", "severe"):
            directives.insert(0, f"Predictive risk {risk_report.level}: {risk_report.mitigations[0]}")

        if pred.risk_level in ("high", "critical"):
            directives.insert(0, f"Predictive homeostasis {pred.risk_level}: {pred.preemptive_actions[0] if pred.preemptive_actions else 'reduce load'}")
        for a in pred.preemptive_actions[:2]:
            if a not in directives:
                directives.append(f"Predictive: {a}")

        return {
            "neuromodulators": neuro.to_dict(),
            "capacity": cap,
            "plasticity": intervention.to_dict(),
            "homeostasis": homeo.to_dict(),
            "predictive_homeostasis": pred.to_dict(),
            "predictive_risk": risk_report.to_dict(),
            "schedule_gate": schedule_gate,
            "jeeves_directives": directives,
        }

    def midnight_consolidation(self, segments: List[str], extra_notes: Optional[List[str]] = None) -> Dict[str, Any]:
        result = self.consolidation.consolidate(segments, extra_notes=extra_notes)
        return result.to_dict()

    def _directives(self, neuro, intervention, homeo) -> List[str]:
        out = []
        out.append(
            f"Dopamine={neuro.dopamine:.2f}, adenosine={neuro.adenosine:.2f}, "
            f"max_tasks={neuro.max_tasks} (scale={neuro.capacity_scale:.2f})."
        )
        for n in neuro.notes:
            out.append(f"Neuro note: {n}")
        if intervention.active:
            out.append(f"Plasticity intervention: {intervention.message}")
        if homeo.schedule_locked:
            out.append("HOMEOSTASIS LOCK: do not accept new schedule items.")
        for a in homeo.actions[:3]:
            out.append(f"Homeostasis: {a}")
        out.append("Tone: empathetic, protective of energy, positively reinforcing.")
        return out

    def jeeves_context_block(self, control: Optional[Dict[str, Any]] = None) -> str:
        if control is None:
            control = self.daily_control_plane()
        lines = ["[NEURO CONTROL PLANE]"]
        for d in control.get("jeeves_directives") or []:
            lines.append(f"- {d}")
        return "\n".join(lines)
