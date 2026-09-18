"""Production composition of Jeeves' robust cognitive control plane.

``CognitiveControlPlane`` contains the policy/learning architecture.  This module
binds it to the factorized Bayesian causal ensemble so high-dimensional
supervisor state does not fall back to full-joint enumeration, and adds an
explicit epistemic frontier that turns knowledge debt into falsifiable probes.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence
import time

from .causal_inference import InferencePolicy
from .cognitive_control_plane import CognitiveControlPlane, ControlPlanePolicy
from .epistemic_frontier import (
    EpistemicFrontierEngine,
    EpistemicFrontierPolicy,
    FrontierSnapshot,
    KnowledgeObligation,
)
from .live_supervisor import LiveSupervisor
from .scalable_causal_ensemble import FactorizedBayesianCausalEnsemble


class FrontierCognitiveControlPlane(CognitiveControlPlane):
    """Cognitive control plane with sparse causal inference and gap discovery."""

    def __init__(
        self,
        baseline: LiveSupervisor | None = None,
        *,
        policy: ControlPlanePolicy | None = None,
        inference_policy: InferencePolicy | None = None,
        epistemic_policy: EpistemicFrontierPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(baseline, policy=policy, clock=clock)
        self.inference_policy = inference_policy or InferencePolicy(
            maximum_sparse_entries=300_000,
            maximum_dense_capacity=8_000_000,
            ancestor_pruning=True,
        )
        # The base constructor creates an empty ensemble.  Replacing it before
        # any learning cycle is lossless and keeps the control-plane logic
        # independent from its exact inference backend.
        self._ensemble = FactorizedBayesianCausalEnsemble(
            preferences=self._preferences,
            policy=self.policy.ensemble_policy,
            clock=clock,
            history_limit=self.policy.history_limit,
            inference_policy=self.inference_policy,
        )
        self.epistemic_frontier = EpistemicFrontierEngine(
            policy=epistemic_policy,
            clock=clock,
        )
        self._last_frontier_snapshot: FrontierSnapshot | None = None

    def map_epistemic_frontier(
        self,
        obligations: Sequence[KnowledgeObligation],
    ) -> FrontierSnapshot:
        """Discover and rank decision-relevant knowledge gaps.

        This is intentionally deterministic host logic. Model confidence alone
        cannot mark an obligation resolved: weak evidence coverage can create a
        blind-spot gap even when confidence is high.
        """

        snapshot = self.epistemic_frontier.discover(obligations)
        self._last_frontier_snapshot = snapshot
        return snapshot

    def epistemic_summary(
        self,
        snapshot: FrontierSnapshot | None = None,
    ) -> dict[str, Any]:
        current = snapshot or self._last_frontier_snapshot
        policy = self.epistemic_frontier.policy
        value: dict[str, Any] = {
            "engine": "epistemic-frontier",
            "minimum_signal": policy.minimum_signal,
            "blind_spot_minimum_impact": policy.blind_spot_minimum_impact,
            "blind_spot_maximum_coverage": policy.blind_spot_maximum_coverage,
            "blind_spot_minimum_confidence": policy.blind_spot_minimum_confidence,
            "maximum_probes": policy.maximum_probes,
        }
        if current is not None:
            value.update(
                {
                    "obligations": len(current.obligations),
                    "open_gaps": len(current.gaps),
                    "ranked_probes": len(current.probes),
                    "frontier_pressure": current.frontier_pressure,
                    "unresolved_decision_value": current.unresolved_decision_value,
                    "snapshot_fingerprint": current.fingerprint,
                }
            )
        return value

    def inference_summary(self) -> dict[str, Any]:
        return {
            "backend": "sparse-variable-elimination",
            "heuristic": self.inference_policy.heuristic.value,
            "maximum_sparse_entries": self.inference_policy.maximum_sparse_entries,
            "maximum_dense_capacity": self.inference_policy.maximum_dense_capacity,
            "ancestor_pruning": self.inference_policy.ancestor_pruning,
            "ensemble_models": len(self._ensemble.hypotheses()),
        }

    def summary(self) -> dict[str, Any]:
        value = super().summary()
        value["inference"] = self.inference_summary()
        value["epistemic_frontier"] = self.epistemic_summary()
        return value
