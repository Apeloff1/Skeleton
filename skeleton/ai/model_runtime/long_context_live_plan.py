"""Bind non-authorizing fair token proposals to *live* local observations.

This adapter never trusts operator-supplied pressure levels and never grants
execution. Unknown telemetry, baseline-only event counters, and sensor faults
are converted to conservative holds before the existing fair planner runs.
"""
from __future__ import annotations

from hashlib import sha256

from .long_context_fairness import (
    LongContextFairPlanner, PressureSignals, StreamDemand,
)
from .long_context_pressure_latch import _inspect
from .long_context_progress import LongContextProgressHead
from .long_context_spool import LongContextSpoolError, _canonical
from .long_context_telemetry_fusion import LongContextTelemetryFusion


class LongContextLivePlanner:
    """Read-only live telemetry binding; backend must independently authorize."""

    def __init__(self, heads: LongContextProgressHead,
                 monitor: LongContextTelemetryFusion):
        if not isinstance(heads, LongContextProgressHead):
            raise LongContextSpoolError("invalid progress coordinator")
        if not isinstance(monitor, LongContextTelemetryFusion):
            raise LongContextSpoolError("invalid telemetry monitor")
        self._heads = heads
        self._monitor = monitor

    def plan(self, demands: tuple[StreamDemand, ...], *,
             expected_tokenizer_digest: str, total_token_budget: int,
             quantum_tokens: int = 256, max_checkpoints: int = 4096
             ) -> dict[str, object]:
        try:
            observation = self._monitor.sample()
            status, levels, digest = _inspect(observation)
        except Exception:
            status, levels, digest = "monitor_unavailable", {}, None
        # A checksum does not attest sensor authority. Only a fully normal,
        # structurally valid observation may be used as a planning hint.
        # Even then the underlying planner does not grant execution.
        if status != "normal_observed":
            levels = {key: "unknown" for key in
                      ("cpu", "memory", "thermal", "energy")}
            digest = None
        signals = PressureSignals(
            cpu=levels["cpu"], memory=levels["memory"],
            thermal=levels["thermal"], energy=levels["energy"],
            device_kind="cpu",
        )
        proposal = LongContextFairPlanner(self._heads).plan(
            demands, expected_tokenizer_digest=expected_tokenizer_digest,
            signals=signals, total_token_budget=total_token_budget,
            quantum_tokens=quantum_tokens, max_checkpoints=max_checkpoints,
        )
        # A future planner change must not accidentally promote a hold.
        if status != "normal_observed" and (
            proposal.get("state") != "hold" or proposal.get("slots")
            or proposal.get("proposed_tokens") != 0
        ):
            raise LongContextSpoolError("unsafe planner hold contract")
        if proposal.get("is_admission_grant") is not False or (
            proposal.get("is_execution_lease") is not False
        ):
            raise LongContextSpoolError("planner claimed unsupported authority")
        result: dict[str, object] = {
            "schema": "skeleton.ai.long-context-live-plan.v1",
            "state": proposal["state"],
            "observation_status": status,
            "observation_digest": digest,
            "observation_digest_is_authenticity_proof": False,
            "plan": proposal,
            "device_qualified": False,
            "pressure_signals_attested": False,
            "is_admission_grant": False,
            "is_execution_lease": False,
            "requires_live_backend_revalidation": True,
        }
        result["live_plan_digest"] = sha256(_canonical(result)).hexdigest()
        return result


__all__ = ["LongContextLivePlanner"]
