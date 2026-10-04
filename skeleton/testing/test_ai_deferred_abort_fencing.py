from __future__ import annotations

import json

import pytest

from skeleton.ai.runtime.deferred import (
    DeferredExecutionError,
    DeferredExecutor,
    build_registry,
)
from skeleton.ai.runtime.deferred.contracts import Budget, EvidenceReceipt, sha256_json


HEX_A = "a" * 64
HEX_B = "b" * 64
HEAD = "d" * 40


def _enabled_executor(handler):
    registry = build_registry()
    record = registry.get("VOL-160")
    record.candidate(
        EvidenceReceipt(
            volume_id="VOL-160",
            head_sha=HEAD,
            artifact_digests=(HEX_A,),
            tests=("candidate:test",),
            status="implementation_candidate",
            created_at="2026-10-04T00:00:00+00:00",
        )
    )
    record.verify(
        EvidenceReceipt(
            volume_id="VOL-160",
            head_sha=HEAD,
            artifact_digests=(HEX_A, HEX_B),
            tests=("candidate:test", "verified:test"),
            status="verified",
            created_at="2026-10-04T00:00:01+00:00",
        )
    )
    registry.enable("VOL-160")

    executor = DeferredExecutor(registry)
    executor.register_handler(
        "VOL-160",
        handler,
        handler_identity=record.spec.handler,
    )
    executor.set_budget(
        "VOL-160",
        Budget(max_attempts=1, max_cost_units=2, max_latency_ms=10),
    )
    return executor


def test_baseexception_after_effect_fences_operation_before_propagation() -> None:
    calls: list[dict[str, object]] = []

    class AbortAfterEffect(BaseException):
        pass

    def handler(payload):
        calls.append(dict(payload))
        raise AbortAfterEffect("sensitive abort detail")

    executor = _enabled_executor(handler)
    payload = {"value": 1}
    invocation = executor.prepare(
        "VOL-160",
        "abort-after-effect",
        payload,
        cost_units=1,
        latency_ms=1,
    )

    with pytest.raises(AbortAfterEffect, match="sensitive abort detail"):
        executor.execute(invocation, payload)

    receipt = executor.receipt("abort-after-effect")
    assert receipt.status == "failed"
    assert receipt.error_type == "AbortAfterEffect"
    assert "sensitive abort detail" not in json.dumps(receipt.as_dict())
    assert calls == [{"value": 1}]

    with pytest.raises(DeferredExecutionError, match="previously failed") as retry:
        executor.execute(invocation, payload)

    assert retry.value.receipt == receipt
    assert calls == [{"value": 1}]


def test_aborted_operation_is_visible_in_deterministic_snapshot() -> None:
    class Abort(BaseException):
        pass

    executor = _enabled_executor(lambda payload: (_ for _ in ()).throw(Abort("boom")))
    payload = {"value": 1}
    invocation = executor.prepare("VOL-160", "snapshot-abort", payload)

    with pytest.raises(Abort):
        executor.execute(invocation, payload)

    first = executor.snapshot()
    second = executor.snapshot()

    assert first == second
    assert len(first["operations"]) == 1
    assert first["operations"][0]["receipt"]["operation_id"] == "snapshot-abort"
    assert first["operations"][0]["receipt"]["status"] == "failed"
    assert len(first["snapshot_digest"]) == 64



def test_terminal_success_checkpoint_replays_without_second_effect() -> None:
    calls: list[dict[str, object]] = []

    def handler(payload):
        calls.append(dict(payload))
        return {"answer": 42}

    first = _enabled_executor(handler)
    payload = {"value": 1}
    invocation = first.prepare(
        "VOL-160",
        "restart-success",
        payload,
        cost_units=1,
        latency_ms=1,
    )
    initial = first.execute(invocation, payload)
    checkpoint = first.export_state()

    second = _enabled_executor(handler)
    second.restore_state(checkpoint)
    replay = second.execute(invocation, payload)

    assert replay.receipt == initial.receipt
    assert replay.result == {"answer": 42}
    assert calls == [{"value": 1}]


def test_terminal_failure_checkpoint_remains_fenced_after_restart() -> None:
    calls: list[dict[str, object]] = []

    def handler(payload):
        calls.append(dict(payload))
        raise RuntimeError("provider detail")

    first = _enabled_executor(handler)
    payload = {"value": 1}
    invocation = first.prepare("VOL-160", "restart-failure", payload)

    with pytest.raises(DeferredExecutionError) as failed:
        first.execute(invocation, payload)

    checkpoint = first.export_state()
    second = _enabled_executor(handler)
    second.restore_state(checkpoint)

    with pytest.raises(DeferredExecutionError, match="previously failed") as replay:
        second.execute(invocation, payload)

    assert replay.value.receipt == failed.value.receipt
    assert calls == [{"value": 1}]


def test_restore_rejects_tampered_success_even_with_resealed_state_digest() -> None:
    first = _enabled_executor(lambda payload: {"answer": 42})
    payload = {"value": 1}
    invocation = first.prepare("VOL-160", "tampered-success", payload)
    first.execute(invocation, payload)

    checkpoint = json.loads(json.dumps(first.export_state()))
    checkpoint["operations"][0]["result"] = {"answer": 43}
    checkpoint["state_digest"] = sha256_json(
        {
            "schema_version": checkpoint["schema_version"],
            "operations": checkpoint["operations"],
        }
    )

    second = _enabled_executor(lambda payload: {"answer": 42})
    with pytest.raises(ValueError, match="result digest mismatch"):
        second.restore_state(checkpoint)


def test_restore_rejects_duplicate_operations_and_non_fresh_target() -> None:
    first = _enabled_executor(lambda payload: {"ok": True})
    payload = {"value": 1}
    invocation = first.prepare("VOL-160", "duplicate-op", payload)
    first.execute(invocation, payload)

    duplicate = json.loads(json.dumps(first.export_state()))
    duplicate["operations"].append(
        json.loads(json.dumps(duplicate["operations"][0]))
    )
    duplicate["state_digest"] = sha256_json(
        {
            "schema_version": duplicate["schema_version"],
            "operations": duplicate["operations"],
        }
    )

    second = _enabled_executor(lambda payload: {"ok": True})
    with pytest.raises(ValueError, match="duplicate terminal operation id"):
        second.restore_state(duplicate)

    clean = first.export_state()
    occupied = _enabled_executor(lambda payload: {"ok": True})
    occupied.execute(
        occupied.prepare("VOL-160", "already-present", payload),
        payload,
    )
    with pytest.raises(RuntimeError, match="fresh executor"):
        occupied.restore_state(clean)
