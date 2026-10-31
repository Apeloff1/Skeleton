"""Canonical deterministic regressions for local fair-stream admission.

All hardware envelopes here are explicitly simulated. These tests do not
qualify GPU execution, OS thermal sensors, physical memory reservation or
native model throughput.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from types import SimpleNamespace

import pytest

from skeleton.ai.model_runtime.fair_stream_queue import (
    FairStreamScheduler, MeasuredStreamBudget, StreamRequest,
)
from skeleton.ai.model_runtime.fair_stream_cli import _command, main
from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase


def request(name: str, tenant: str = "tenant", *, tokens: int = 100,
            bytes_per_token: int = 2, priority: int = 0,
            phase: InferencePhase = InferencePhase.PREFILL) -> StreamRequest:
    return StreamRequest(name, tenant, phase, tokens, bytes_per_token, priority)


def budget(*, tokens: int = 100, slots: int = 2, available: int = 1024,
           reserve: int = 256, pressure: int = 0,
           thermal: bool = False) -> MeasuredStreamBudget:
    return MeasuredStreamBudget(
        available, reserve, tokens, slots, pressure, thermal, "simulated",
    )


def test_exact_budget_and_memory_accounting() -> None:
    queue = FairStreamScheduler(quantum=64)
    queue.submit(request("a", tokens=100, bytes_per_token=4))
    queue.submit(request("b", tokens=100, bytes_per_token=4))
    plan = queue.plan(budget(tokens=100, slots=2, available=500, reserve=200))
    assert sum(lease.tokens for lease in plan.leases) <= 100
    assert sum(lease.bytes_reserved for lease in plan.leases) <= 300
    assert all(lease.tokens > 0 for lease in plan.leases)
    assert plan.available_ram_bytes >= 0
    assert plan.checkpoint_digest == queue.checkpoint()["digest"]


def test_tenant_round_robin_prevents_single_slot_starvation() -> None:
    queue = FairStreamScheduler(quantum=1)
    for name in ("a", "b", "c"):
        queue.submit(request(name, name, tokens=5))
    observed = []
    for _ in range(6):
        plan = queue.plan(budget(tokens=1, slots=1))
        assert len(plan.leases) == 1
        lease = plan.leases[0]
        observed.append(lease.tenant_id)
        queue.acknowledge(lease.lease_id, consumed_tokens=1)
    assert observed == ["a", "b", "c", "a", "b", "c"]


def test_bounded_priority_within_tenant_and_no_cross_tenant_capture() -> None:
    queue = FairStreamScheduler(quantum=1)
    queue.submit(request("low", "a", priority=-100, tokens=4096))
    queue.submit(request("high", "a", priority=100, tokens=4096))
    queue.submit(request("other", "b", priority=100, tokens=4096))
    first = queue.plan(budget(tokens=1, slots=1))
    assert first.leases[0].request_id == "high"
    queue.acknowledge(first.leases[0].lease_id, consumed_tokens=1)
    second = queue.plan(budget(tokens=1, slots=1))
    assert second.leases[0].request_id == "other"
    queue.acknowledge(second.leases[0].lease_id, consumed_tokens=1)
    for _ in range(250):
        plan = queue.plan(budget(tokens=1, slots=1))
        queue.acknowledge(plan.leases[0].lease_id, consumed_tokens=1)
        if plan.leases[0].request_id == "low":
            break
    else:
        pytest.fail("bounded aging failed to admit low priority work")


def test_decode_one_token_quantum_preserves_phase() -> None:
    queue = FairStreamScheduler(quantum=100)
    queue.submit(request("decode", phase=InferencePhase.DECODE, tokens=8))
    plan = queue.plan(budget(tokens=100))
    assert len(plan.leases) == 1
    assert plan.leases[0].phase is InferencePhase.DECODE
    assert plan.leases[0].tokens == 1


@pytest.mark.parametrize("pressure,slots,tokens", [
    (0, 8, 100),
    (600_000, 2, 40),
    (800_000, 1, 20),
    (950_000, 0, 0),
    (1_000_000, 0, 0),
])
def test_pressure_is_monotone_and_fail_closed(
    pressure: int, slots: int, tokens: int,
) -> None:
    sample = budget(tokens=100, slots=8, pressure=pressure)
    assert sample.effective_slots == slots
    assert sample.effective_tokens == tokens


def test_thermal_hold_blocks_admission_without_consumption() -> None:
    queue = FairStreamScheduler()
    queue.submit(request("a"))
    plan = queue.plan(budget(thermal=True))
    assert not plan.leases
    assert plan.deferred == ("a",)
    assert queue.request_ids == ("a",)


def test_zero_ram_and_unknown_capacity_never_grant_tokens() -> None:
    queue = FairStreamScheduler()
    queue.submit(request("a"))
    plan = queue.plan(budget(available=100, reserve=100))
    assert not plan.leases
    assert plan.available_ram_bytes == 0


def test_pending_lease_fences_new_plans_and_cancellation() -> None:
    queue = FairStreamScheduler()
    queue.submit(request("a"))
    lease = queue.plan(budget()).leases[0]
    with pytest.raises(ValueError, match="pending"):
        queue.plan(budget())
    with pytest.raises(ValueError, match="pending"):
        queue.cancel("a")
    queue.acknowledge(lease.lease_id, consumed_tokens=0)
    assert queue.plan(budget()).leases[0].request_id == "a"


def test_partial_ack_and_terminal_removal() -> None:
    queue = FairStreamScheduler(quantum=10)
    queue.submit(request("a", tokens=12))
    lease = queue.plan(budget()).leases[0]
    queue.acknowledge(lease.lease_id, consumed_tokens=7)
    assert queue.checkpoint()["requests"][0]["remaining_tokens"] == 5
    second = queue.plan(budget()).leases[0]
    assert second.tokens == 5
    queue.acknowledge(second.lease_id, consumed_tokens=5)
    assert queue.request_ids == ()


def test_checkpoint_restore_requires_explicit_lease_resolution() -> None:
    queue = FairStreamScheduler(quantum=16)
    queue.submit(request("a", tokens=50))
    lease = queue.plan(budget()).leases[0]
    restored = FairStreamScheduler.restore(queue.checkpoint())
    assert restored.pending_ids == (lease.lease_id,)
    with pytest.raises(ValueError, match="pending"):
        restored.plan(budget())
    restored.acknowledge(lease.lease_id, consumed_tokens=16)
    assert restored.checkpoint()["requests"][0]["remaining_tokens"] == 34
    assert restored.plan(budget()).leases


def test_checkpoint_is_deterministic_and_replay_stable() -> None:
    left = FairStreamScheduler()
    right = FairStreamScheduler()
    for queue in (left, right):
        queue.submit(request("x", "a"))
        queue.submit(request("y", "b"))
    assert left.checkpoint() == right.checkpoint()
    assert left.plan(budget()) == right.plan(budget())


def test_checkpoint_integrity_rejects_tampering() -> None:
    queue = FairStreamScheduler()
    queue.submit(request("a"))
    state = queue.checkpoint()
    state["requests"][0]["remaining_tokens"] = 999
    with pytest.raises(ValueError, match="integrity"):
        FairStreamScheduler.restore(state)


def test_checkpoint_cannot_forge_pending_lease_binding_with_recomputed_hash() -> None:
    queue = FairStreamScheduler()
    queue.submit(request("a"))
    queue.plan(budget())
    state = queue.checkpoint()
    state["pending"][0]["tokens"] += 1
    state["digest"] = hashlib.sha256(json.dumps(
        {k: v for k, v in state.items() if k != "digest"},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()
    with pytest.raises(ValueError, match="lease"):
        FairStreamScheduler.restore(state)


@pytest.mark.parametrize("bad", [
    {"request_id": "", "tenant_id": "x"},
    {"request_id": "a\nb", "tenant_id": "x"},
    {"request_id": "a", "tenant_id": ""},
    {"request_id": "a", "tenant_id": "x", "tokens": True},
])
def test_malformed_request_identity_or_quantity_fails_closed(bad: dict[str, object]) -> None:
    kwargs = {
        "request_id": "a", "tenant_id": "x",
        "phase": InferencePhase.PREFILL, "remaining_tokens": 3,
        "bytes_per_token": 2, "priority": 0,
    }
    kwargs.update(bad)
    if "tokens" in kwargs:
        kwargs["remaining_tokens"] = kwargs.pop("tokens")
    with pytest.raises(ValueError):
        StreamRequest(**kwargs)


def test_duplicate_and_capacity_are_explicit_errors() -> None:
    queue = FairStreamScheduler(max_requests=1)
    queue.submit(request("a"))
    with pytest.raises(ValueError, match="duplicate"):
        queue.submit(request("a"))
    with pytest.raises(ValueError, match="full"):
        queue.submit(request("b"))


def test_budget_rejects_boolean_negative_and_forged_thermal_values() -> None:
    with pytest.raises(ValueError):
        budget(tokens=True)
    with pytest.raises(ValueError):
        budget(pressure=-1)
    with pytest.raises(ValueError):
        MeasuredStreamBudget(100, 0, 10, 1, 0, "false", "operator")


def _payload() -> dict[str, object]:
    return {
        "schema": "skeleton.ai.fair-stream-command.v1",
        "requests": [{
            "request_id": "a", "tenant_id": "world-builder",
            "phase": "prefill", "remaining_tokens": 10,
            "bytes_per_token": 4, "priority": 0,
        }],
        "checkpoint": None, "acknowledgments": [], "cancellations": [],
        "envelope": {
            "available_ram_bytes": 1024, "reserved_ram_bytes": 256,
            "token_budget": 10, "stream_slots": 1, "pressure_ppm": 0,
            "thermal_hold": False, "measurement": "simulated",
        },
        "token_budget": None,
    }


def test_cli_command_is_source_bound_and_replayable() -> None:
    first = _command(_payload(), live=False, storage_path=".")
    assert first["measurement"] == "simulated"
    assert first["plan"]["leases"][0]["tokens"] == 10
    assert first["checkpoint"]["pending"]
    second_payload = _payload()
    second_payload["requests"] = []
    second_payload["checkpoint"] = first["checkpoint"]
    second_payload["acknowledgments"] = [{
        "lease_id": first["plan"]["leases"][0]["lease_id"],
        "consumed_tokens": 10,
    }]
    second = _command(second_payload, live=False, storage_path=".")
    assert second["checkpoint"]["requests"] == []


def test_cli_rejects_operator_claim_of_os_probe() -> None:
    payload = _payload()
    payload["envelope"]["measurement"] = "os_probe"
    with pytest.raises(ValueError, match="cannot claim"):
        _command(payload, live=False, storage_path=".")


def test_cli_bounds_stdin_and_returns_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"x" * 262145)))
    assert main([]) == 2
    assert "input byte budget" in capsys.readouterr().err


def test_cli_round_trip_stdout_without_payload_leak(monkeypatch, capsys) -> None:
    raw = json.dumps(_payload()).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw)))
    assert main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["plan"]["leases"][0]["request_id"] == "a"
    assert "world-builder" in json.dumps(output)
    assert "prompt" not in json.dumps(output)
