"""Pack F one-call wiring: s2s auth + pipeline + backpressure + telemetry.

:func:`build_pack_f_plane` assembles the pieces in the canonical order and
cross-wires telemetry into every gate::

    plane = build_pack_f_plane(verifier=verifier)
    decision = plane.s2s_gate.evaluate(method, path, headers)      # authN/authZ/admission
    resp, ctx = plane.router.call(request, upstream_handler)       # telemetry > backpressure
                                                                    # > deadline > retry > breaker
Nothing here is installed into an app automatically; callers opt in with
:func:`skeleton.gate_plane.s2s.install_s2s_gate` and their own client code.
No ``api/server.py`` lifespan change.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, Optional

from skeleton.gate_plane.admit import AdmissionMatrix
from skeleton.gate_plane.backpressure import BackpressureGate, backpressure_stage_factory, default_pressure_source
from skeleton.gate_plane.backpressure.sources import PressureSource
from skeleton.gate_plane.pipeline import BreakerRegistry, PipelineRouter, RetryBudgetRegistry, RouteTable, default_s2s_routes
from skeleton.gate_plane.s2s.authz import PolicyTable, default_gate_plane_policies
from skeleton.gate_plane.s2s.clock import Clock, system_clock
from skeleton.gate_plane.s2s.gate import S2SAuthGate
from skeleton.gate_plane.s2s.tokens import TokenVerifier
from skeleton.gate_plane.telemetry import GateTelemetry


@dataclass
class PackFPlane:
    router: PipelineRouter
    backpressure: BackpressureGate
    telemetry: GateTelemetry
    breakers: BreakerRegistry
    budgets: RetryBudgetRegistry
    s2s_gate: Optional[S2SAuthGate] = None

    def status(self) -> Dict[str, Any]:
        return {
            "routes": [r.name for r in self.router.table.routes()],
            "breakers": self.breakers.states(),
            "budgets": self.budgets.stats(),
            "backpressure": self.backpressure.stats(),
            "telemetry_dropped": self.telemetry.dropped,
            "s2s": self.s2s_gate is not None,
        }


def build_pack_f_plane(
    *,
    verifier: Optional[TokenVerifier] = None,
    policies: Optional[PolicyTable] = None,
    routes: Optional[RouteTable] = None,
    pressure: Optional[PressureSource] = None,
    matrix: Optional[AdmissionMatrix] = None,
    telemetry: Optional[GateTelemetry] = None,
    clock: Optional[Clock] = None,
    admission: bool = True,
    rng: Optional[random.Random] = None,
    **backpressure_kw: Any,
) -> PackFPlane:
    clk = clock or system_clock()
    tel = telemetry or GateTelemetry(clock=clk)
    breakers = BreakerRegistry(clock=clk)
    budgets = RetryBudgetRegistry(clock=clk)
    # Without an explicit source: registered Pack H, else the s2s admission gate's
    # own AdaptiveGate (or the registered one) as the fallback signal.
    fallback_gate = matrix.gate if matrix is not None else None
    bp = BackpressureGate(pressure or default_pressure_source(clock=clk, gate=fallback_gate), **backpressure_kw)
    tel.attach(breakers=breakers, backpressure=bp)
    router = PipelineRouter(
        routes or default_s2s_routes(),
        clock=clk,
        breakers=breakers,
        budgets=budgets,
        stage_factories={"telemetry": tel.stage_factory(), "backpressure": backpressure_stage_factory(bp)},
        rng=rng,
    )
    gate = None
    if verifier is not None:
        gate = S2SAuthGate(verifier, policies or default_gate_plane_policies(), matrix=matrix, admission=admission)
        tel.attach(s2s_gate=gate)
    return PackFPlane(router=router, backpressure=bp, telemetry=tel, breakers=breakers, budgets=budgets, s2s_gate=gate)


__all__ = ["PackFPlane", "build_pack_f_plane"]
