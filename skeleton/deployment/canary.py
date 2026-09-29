"""Compatibility shim for the canonical deployment strategies namespace."""
from skeleton.deploy.strategies.canary import DEFAULT_STAGES, CanaryController, Rollout, StageMetric

__all__ = ["DEFAULT_STAGES", "CanaryController", "Rollout", "StageMetric"]
