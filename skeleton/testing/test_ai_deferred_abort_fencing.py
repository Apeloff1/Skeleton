from __future__ import annotations

import json

import pytest

from skeleton.ai.runtime.deferred import (
    DeferredExecutionError,
    DeferredExecutor,
    build_registry,
)
from skeleton.ai.runtime.deferred.contracts import Budget, EvidenceReceipt


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
        )
    )
    record.verify(
        EvidenceReceipt(
            volume_id="VOL-160",
            head_sha=HEAD,
            artifact_digests=(HEX_A, HEX_B),
            tests=("candidate:test", "verified:test"),
            status="verified",
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
