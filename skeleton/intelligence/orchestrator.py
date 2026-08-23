"""Intelligence Orchestrator — split from the intelligence monolith (v16.2)."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from skeleton.kernel.events import EventBus

from .temporal import TemporalEvent, TemporalReasoner
from .causal import CausalInference
from .metalearning import MetaLearner
from .neurosymbolic import NeuralSymbolicEngine
from .economic import BudgetConstraint, EconomicOptimiser

# =============================================================================
# INTELLIGENCE ORCHESTRATOR
# =============================================================================

class IntelligenceOrchestrator:
    """
    Composes all advanced intelligence systems into a unified interface.
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self.temporal = TemporalReasoner(bus)
        self.causal = CausalInference(bus)
        self.meta = MetaLearner(bus=bus)
        self.neurosym = NeuralSymbolicEngine(bus)
        self.economic = EconomicOptimiser(bus)
        self._bus = bus

    def reason(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Multi-modal reasoning: temporal, causal, symbolic, economic.
        Returns integrated result with confidence scores.
        """
        results = {
            "temporal": None,
            "causal": None,
            "symbolic": None,
            "economic": None,
            "confidence": 0.0,
        }

        # Temporal reasoning
        if context and "events" in context:
            for event_data in context["events"]:
                event = TemporalEvent(
                    event_id=event_data.get("id", str(hash(event_data))),
                    description=event_data.get("description", ""),
                    timestamp=event_data.get("timestamp", time.time()),
                    duration=event_data.get("duration"),
                )
                self.temporal.add_event(event)
            # Query temporal patterns
            if context.get("predict_next"):
                predictions = self.temporal.predict_next(context["predict_next"])
                results["temporal"] = {"predictions": predictions}

        # Causal reasoning
        if context and "intervention" in context:
            treatment = context["intervention"].get("treatment")
            outcome = context["intervention"].get("outcome")
            if treatment and outcome:
                ate, se = self.causal.estimate_ate(treatment, outcome)
                results["causal"] = {"ate": ate, "se": se}

        # Symbolic reasoning
        if context and "goal" in context:
            proved, chain, confidence = self.neurosym.infer(context["goal"])
            results["symbolic"] = {"proved": proved, "chain": [r.conclusion for r in chain], "confidence": confidence}

        # Economic optimisation
        if context and "query_complexity" in context:
            model = self.economic.route_query(
                context["query_complexity"],
                set(context.get("required_capabilities", [])),
                BudgetConstraint(
                    total_budget=context.get("budget", 100.0),
                    max_cost_per_query=context.get("max_cost", 10.0),
                    min_quality=context.get("min_quality", 0.7),
                    max_latency_ms=context.get("max_latency", 5000),
                ),
            )
            if model:
                results["economic"] = {
                    "model_id": model.model_id,
                    "cost": model.cost_per_token,
                    "quality": model.quality_score,
                }

        # Aggregate confidence
        confidences = [
            v.get("confidence", 0) if isinstance(v, dict) else 0
            for v in results.values() if v is not None
        ]
        results["confidence"] = sum(confidences) / len(confidences) if confidences else 0.0

        return results
