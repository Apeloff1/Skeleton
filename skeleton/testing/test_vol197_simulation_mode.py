from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.simulation_mode import (
    SimulationAuthority,
    SimulationEvidence,
    SimulationRequest,
    SimulationRuntime,
)


def authority(*, cost: int = 3, latency: int = 20) -> SimulationAuthority:
    return SimulationAuthority(
        principal_id="worker",
        allowed_adapters=("mail.simulated",),
        max_cost_units=cost,
        max_latency_ms=latency,
    )


def test_simulation_runtime_is_deterministic_and_replay_safe() -> None:
    runtime = SimulationRuntime()
    calls: list[dict[str, object]] = []
    runtime.register(
        "mail.simulated",
        lambda args: calls.append(dict(args)) or {"accepted": True, "to": args["to"]},
        simulated=True,
    )
    request = SimulationRequest(
        "op-1",
        "mail.simulated",
        {"to": "fixture@example.invalid"},
        cost_units=2,
        latency_ms=5,
    )

    first = runtime.execute(request, authority())
    second = runtime.execute(request, authority())

    assert first == second
    assert len(calls) == 1
    assert first.evidence.simulated is True
    assert first.evidence.production_eligible is False
    assert first.evidence.input_digest == request.input_digest
    assert runtime.replay("op-1") == first


def test_simulation_rejects_production_adapter_and_ungranted_authority() -> None:
    runtime = SimulationRuntime()
    with pytest.raises(PermissionError, match="production adapter"):
        runtime.register("mail.real", lambda args: args, simulated=False)

    runtime.register("mail.simulated", lambda args: args, simulated=True)
    request = SimulationRequest("op-1", "mail.simulated", {"x": 1})
    denied = SimulationAuthority("worker", ("other.simulated",), 2, 10)
    with pytest.raises(PermissionError, match="outside simulation authority"):
        runtime.execute(request, denied)


def test_simulation_fails_closed_for_unregistered_adapter() -> None:
    runtime = SimulationRuntime()
    request = SimulationRequest("op-1", "mail.simulated", {"x": 1})
    with pytest.raises(PermissionError, match="unregistered adapter"):
        runtime.execute(request, authority())


def test_simulation_enforces_cost_and_latency_budgets_before_effect() -> None:
    runtime = SimulationRuntime()
    calls: list[object] = []
    runtime.register(
        "mail.simulated",
        lambda args: calls.append(args) or {"ok": True},
        simulated=True,
    )
    with pytest.raises(RuntimeError, match="cost budget exhausted"):
        runtime.execute(
            SimulationRequest("cost", "mail.simulated", {}, cost_units=4),
            authority(cost=3),
        )
    with pytest.raises(RuntimeError, match="latency budget exhausted"):
        runtime.execute(
            SimulationRequest("latency", "mail.simulated", {}, latency_ms=21),
            authority(latency=20),
        )
    assert calls == []


def test_simulation_replay_rejects_changed_input_without_second_effect() -> None:
    runtime = SimulationRuntime()
    calls: list[object] = []
    runtime.register(
        "mail.simulated",
        lambda args: calls.append(args) or {"ok": True},
        simulated=True,
    )
    runtime.execute(
        SimulationRequest("op-1", "mail.simulated", {"x": 1}),
        authority(),
    )
    with pytest.raises(ValueError, match="replay input collision"):
        runtime.execute(
            SimulationRequest("op-1", "mail.simulated", {"x": 2}),
            authority(),
        )
    assert len(calls) == 1


def test_simulation_evidence_cannot_claim_production_eligibility() -> None:
    with pytest.raises(ValueError, match="never be production eligible"):
        SimulationEvidence(
            operation_id="op",
            adapter_id="sim",
            principal_id="worker",
            input_digest="a" * 64,
            output_digest="b" * 64,
            production_eligible=True,
        )
