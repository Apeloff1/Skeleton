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
    # Keep quantities internally valid so denial exercises the lease identity,
    # rather than merely exceeding the request token ceiling.
    lease = state["pending"][0]
    assert lease["tokens"] > 1
    lease["tokens"] -= 1
    lease["bytes_reserved"] -= 2
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

def test_whole_request_checkpoint_distinguishes_policy_and_rejects_partial_grants():
    queue = FairStreamScheduler(quantum=1, whole_request=True)
    queue.submit(StreamRequest("native", "tenant", InferencePhase.PREFILL, 4, 2,
                               authorization_digest="f" * 64))
    assert queue.plan(budget(tokens=3, slots=1)).leases == ()
    assert queue.plan(budget(tokens=4, slots=1, available=258, reserve=256)).leases == ()
    with pytest.raises(ValueError, match="execution policy"):
        queue.plan(budget(tokens=4), whole_request=False)
    lease, = queue.plan(budget(tokens=4, slots=1)).leases
    assert lease.tokens == 4
    checkpoint = queue.checkpoint()
    restored = FairStreamScheduler.restore(checkpoint)
    assert restored.whole_request
    assert restored.checkpoint() == checkpoint
    with pytest.raises(ValueError, match="execution policy"):
        restored.acknowledge(lease.lease_id, consumed_tokens=0, whole_request=False)
    restored.acknowledge(lease.lease_id, consumed_tokens=0)
    assert restored.request_ids == ()

def _rehash_checkpoint(state):
    body = {key: value for key, value in state.items() if key != "digest"}
    state["digest"] = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return state


def test_restored_round_overflow_fails_before_queue_mutation():
    from skeleton.ai.model_runtime.fair_stream_queue import MAX_BYTES

    queue = FairStreamScheduler()
    queue.submit(request("r"))
    state = queue.checkpoint()
    state["round"] = MAX_BYTES
    restored = FairStreamScheduler.restore(_rehash_checkpoint(state))
    before = restored.checkpoint()
    with pytest.raises(ValueError, match="round counter exhausted"):
        restored.plan(budget())
    assert restored.checkpoint() == before


def test_restored_token_history_cannot_exceed_original_limit():
    from skeleton.ai.model_runtime.fair_stream_queue import MAX_TOKENS

    queue = FairStreamScheduler()
    queue.submit(request("r", tokens=MAX_TOKENS))
    state = queue.checkpoint()
    state["requests"][0]["served_tokens"] = 1
    with pytest.raises(ValueError, match="token history"):
        FairStreamScheduler.restore(_rehash_checkpoint(state))


@pytest.mark.parametrize("damage", ["historical_round", "wait_age"])
def test_pending_lease_must_belong_to_latest_planning_round(damage):
    queue = FairStreamScheduler()
    queue.submit(request("r"))
    queue.plan(budget())
    state = queue.checkpoint()
    if damage == "historical_round":
        state["round"] += 1
    else:
        state["requests"][0]["wait_rounds"] = 1
    with pytest.raises(ValueError, match="lease does not bind"):
        FairStreamScheduler.restore(_rehash_checkpoint(state))


def test_large_tenant_inventory_remains_insertion_order_independent():
    from dataclasses import replace

    requests = [
        replace(request(f"r-{i:04d}", f"tenant-{i % 137:03d}",
                        tokens=(i % 13) + 1, priority=(i % 21) - 10),
                authorization_digest="a" * 64)
        for i in range(384)
    ]
    queues = [FairStreamScheduler(whole_request=True) for _ in range(2)]
    for queue, items in zip(queues, (requests, reversed(requests))):
        for item in items:
            queue.submit(item)
    for _ in range(8):
        plans = [queue.plan(budget(tokens=96, slots=16, available=8192)) for queue in queues]
        assert plans[0] == plans[1]
        for queue, plan in zip(queues, plans):
            for lease in plan.leases:
                queue.acknowledge(lease.lease_id, consumed_tokens=lease.tokens)
    assert queues[0].checkpoint() == queues[1].checkpoint()
