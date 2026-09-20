"""Gate plane — Middleware Pack B assurance surface.

Deepens install_gate / admit_write / create_app wiring with a chaos-aware
admission catalog, reverse-proxy contracts (Zaibatsu.Gate sibling), and
scenario evidence. Pure planning/policy — no host side effects.
"""

from __future__ import annotations

from skeleton.gate_plane.stack import (
    GATE_LAYERS,
    GateLayer,
    describe_stack,
    install_order,
)
from skeleton.gate_plane.admit import (
    AdmissionDecision,
    AdmissionMatrix,
    evaluate_admission,
)
from skeleton.gate_plane.chaos_scenarios import (
    ChaosScenario,
    SCENARIOS,
    run_scenario,
    scenario_catalog,
)
from skeleton.gate_plane.proxy_contracts import (
    ProxyUpstream,
    RetryPolicy,
    default_upstreams,
    validate_proxy_plan,
)
from skeleton.gate_plane.create_app_hooks import (
    CreateAppGatePlan,
    build_create_app_gate_plan,
    open_probe_prefixes,
)
from skeleton.gate_plane.operations import (
    GateAction,
    GatePlan,
    playbook_chaos_sample,
    playbook_create_app_smoke,
    registry as gate_registry,
)
from skeleton.gate_plane.evidence import (
    GateEvidence,
    digest_plane,
    render_evidence,
)

__all__ = [
    "GateAction",
    "GatePlan",
    "playbook_chaos_sample",
    "playbook_create_app_smoke",
    "gate_registry",
    "GATE_LAYERS",
    "GateLayer",
    "describe_stack",
    "install_order",
    "AdmissionDecision",
    "AdmissionMatrix",
    "evaluate_admission",
    "ChaosScenario",
    "SCENARIOS",
    "run_scenario",
    "scenario_catalog",
    "ProxyUpstream",
    "RetryPolicy",
    "default_upstreams",
    "validate_proxy_plan",
    "CreateAppGatePlan",
    "build_create_app_gate_plan",
    "open_probe_prefixes",
    "GateEvidence",
    "digest_plane",
    "render_evidence",
]
