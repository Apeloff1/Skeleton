"""Production composition of Jeeves' robust cognitive control plane.

``CognitiveControlPlane`` contains the policy/learning architecture.  This module
binds it to the factorized Bayesian causal ensemble so high-dimensional
supervisor state does not fall back to full-joint enumeration.
"""

from __future__ import annotations

from typing import Any, Callable
import time

from .causal_inference import InferencePolicy
from .cognitive_control_plane import CognitiveControlPlane, ControlPlanePolicy
from .live_supervisor import LiveSupervisor
from .scalable_causal_ensemble import FactorizedBayesianCausalEnsemble


class FrontierCognitiveControlPlane(CognitiveControlPlane):
    """Cognitive control plane with sparse causal inference as the default."""

    def __init__(
        self,
        baseline: LiveSupervisor | None = None,
        *,
        policy: ControlPlanePolicy | None = None,
        inference_policy: InferencePolicy | None = None,
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
        return value
