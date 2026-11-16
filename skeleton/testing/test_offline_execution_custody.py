"""Integration regressions for sealed source custody and measured execution gates.

Hardware fixtures and the cooperative slice test double are explicitly
non-qualifying. The whole-request test exercises the actual reference
inference engine, never a simulated native GGUF execution.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import threading
import time

import pytest

from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest, ModelIdentity, WeightLoadPlan, WeightShard
from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore
from skeleton.app.offline_energy_hysteresis import HysteresisPolicy
from skeleton.app.offline_runtime_custody import sealed_cpu_custody
from skeleton.app.offline_runtime_preflight import RuntimePreflightError
from skeleton.app.offline_runtime_queue import OfflineRequestQueue, Progress, QueuePolicy, reserve_cache
from skeleton.app.offline_runtime_session import OfflineRuntimeSession
from skeleton.testing.test_offline_runtime_admission import POLICY, sample, stage, GIB


def session_fixture(tmp_path, monkeypatch, *, queue_policy=None):
    root, plan, identity = stage(tmp_path)
    base = POLICY
    policy = reserve_cache(base, queue_policy) if queue_policy else base
    counter = [0]

    def observation():
        counter[0] += 1
        return sample(start=time.monotonic_ns() - 1000, origin="local_probe")

    monkeypatch.setattr("skeleton.app.offline_runtime_session.sample_hardware", observation)
    session = OfflineRuntimeSession(root, plan_digest=plan, model_identity_digest=identity,
                                    policy=policy, hysteresis=HysteresisPolicy(
                                        recovery_samples=2, recovery_cooldown_ns=0,
                                        max_sample_age_ns=policy.sample_age_ns))
    return session, base, counter


class Executor:
    def __init__(self):
        self.calls = []
        self.releases = []
        self.invalid = False

    def run_slice(self, *, request_id, phase, tokens, deadline_ns, cancel):
        assert isinstance(cancel, threading.Event)
        assert deadline_ns >= time.monotonic_ns()
        self.calls.append((request_id, phase, tokens))
        return Progress(request_id, phase, tokens + int(self.invalid))

    def release(self, request_id):
        self.releases.append(request_id)


def make_queue(tmp_path, monkeypatch, **overrides):
    policy = QueuePolicy(**overrides)
    owner, base, _ = session_fixture(tmp_path, monkeypatch, queue_policy=policy)
    executor = Executor()
    return OfflineRequestQueue(owner, policy, executor, base_policy=base), executor


def test_queue_preserves_real_phase_order_and_releases_exact_logical_reservation(tmp_path, monkeypatch):
    queue, executor = make_queue(tmp_path, monkeypatch, max_requests=2, max_active=1,
                                  max_request_tokens=16, kv_capacity_bytes=128, kv_bytes_per_token=8)
    queue.submit(BatchRequest("alpha", 2, 2), timeout_ms=10000)
    assert queue.status()["capacity"]["queued_requests"] == 1
    first = queue.tick()
    assert not first["progress"] and not executor.calls
    assert first["capacity"]["kv_used_bytes"] == 32
    for _ in range(6):
        result = queue.tick()
        if not queue.status()["requests"]:
            break
    assert executor.calls == [("alpha", "prefill", 2), ("alpha", "decode", 1), ("alpha", "decode", 1)]
    assert executor.releases == ["alpha"]
    assert result["retired"] == [{"request_id": "alpha", "terminal": "completed"}]
    assert result["capacity"]["kv_used_bytes"] == 0
    assert result["kv_accounting"] == "logical_reservation_only"
    queue.close()


def test_cache_capacity_and_request_bounds_fail_before_executor(tmp_path, monkeypatch):
    queue, executor = make_queue(tmp_path, monkeypatch, max_requests=2, max_active=1,
                                  max_request_tokens=16, kv_capacity_bytes=32, kv_bytes_per_token=8)
    with pytest.raises(ValueError):
        queue.submit(BatchRequest("oversized", 4, 1), timeout_ms=10000)
    queue.submit(BatchRequest("first", 2, 2), timeout_ms=10000)
    queue.submit(BatchRequest("second", 2, 2), timeout_ms=10000)
    with pytest.raises(ValueError):
        queue.submit(BatchRequest("third", 1, 1), timeout_ms=10000)
    assert queue.tick()["capacity"]["kv_used_bytes"] == 32
    assert queue.cancel("second")
    assert queue.cancel("first")
    retired = queue.tick()["retired"]
    assert {row["request_id"] for row in retired} == {"first", "second"}
    assert executor.calls == [] and executor.releases == ["first"]
    assert queue.status()["capacity"]["kv_used_bytes"] == 0
    queue.close()


def test_executor_overrun_poison_preserves_suspect_reservation(tmp_path, monkeypatch):
    queue, executor = make_queue(tmp_path, monkeypatch)
    queue.submit(BatchRequest("bad", 2, 2), timeout_ms=10000)
    queue.tick()
    executor.invalid = True
    with pytest.raises(RuntimePreflightError, match="exceeds exact grant"):
        queue.tick()
    assert queue.status()["poisoned"]
    assert queue.status()["capacity"]["kv_used_bytes"] > 0
    assert not executor.releases
    queue.close()
    assert executor.releases == ["bad"]


def test_missing_separate_cache_reserve_refuses_queue(tmp_path, monkeypatch):
    session, base, _ = session_fixture(tmp_path, monkeypatch)
    with pytest.raises(RuntimePreflightError, match="separately reserved"):
        OfflineRequestQueue(session, QueuePolicy(), Executor(), base_policy=base)
    session.close()


def test_native_sealed_owner_real_small_bytes_refuses_mutation(tmp_path, monkeypatch):
    if not hasattr(os, "memfd_create"):
        pytest.skip("Linux memfd unavailable")
    payload = b"actual original weight bytes"
    checksum = sha256(payload).hexdigest()
    model = ModelIdentity("test", "v1", "tiny", checksum, checksum, checksum)
    shard = WeightShard(0, checksum, len(payload), "local")
    plan = WeightLoadPlan(model.identity_digest, (shard,), len(payload))
    path = tmp_path / "source.bin"
    path.write_bytes(payload)
    store = tmp_path / "store"
    key = WeightShardStore(store).stage_plan(model, plan, {0: path})
    monkeypatch.setattr("skeleton.app.offline_runtime_custody.sample_hardware",
                        lambda: sample(start=time.monotonic_ns() - 1000, origin="local_probe"))
    with sealed_cpu_custody(store, plan_digest=key, model=model, policy=POLICY,
                            maximum_sealed_bytes=len(payload)) as (pages, receipt):
        assert bytes(pages[0]) == payload
        with pytest.raises(TypeError):
            pages[0][0] = 0
        assert receipt["sealed_bytes"] == len(payload)
        assert not receipt["native_qualified"]
        # An independent disk mutation cannot mutate the already sealed copy.
        next((store / "objects").glob("*/*")).write_bytes(b"tampered")
        assert bytes(pages[0]) == payload
    assert pages[0].closed
    with pytest.raises(ValueError):
        with sealed_cpu_custody(store, plan_digest=key, model=model, policy=POLICY,
                                maximum_sealed_bytes=len(payload)):
            pytest.fail("corrupt store should not be yielded")


def test_whole_request_uses_actual_reference_engine_after_full_reservation(tmp_path, monkeypatch):
    from skeleton.ai.runtime.inference.local import LocalInferenceEngine, LocalInferenceRequest, ReferenceNGramModel
    from skeleton.app.offline_runtime_whole_request import MeasuredWholeRequestEngine

    async def run():
        session, _, _ = session_fixture(tmp_path, monkeypatch)
        model = ReferenceNGramModel.train(["hello harbor hello harbor", "hello builder hello builder"])
        engine = LocalInferenceEngine(model, cache_size=0, max_concurrency=1)
        adapter = MeasuredWholeRequestEngine(session, engine, backend_digest=model.model_digest)
        req = LocalInferenceRequest("hello", max_output_tokens=4, seed=1, tool_choice="none")
        try:
            deferred = await adapter.generate(req, max_input_tokens=16, timeout_ms=10000)
            assert deferred.result is None and deferred.receipt["status"] == "deferred"
            completed = await adapter.generate(req, max_input_tokens=16, timeout_ms=10000)
            assert completed.result is not None
            assert completed.receipt["status"] == "completed"
            assert completed.result.model_digest == model.model_digest
            assert completed.receipt["usage"]["output_tokens"] <= 4
            assert completed.receipt["backend_weight_binding"] == "not_assessed"
            assert not completed.receipt["native_qualified"]
        finally:
            adapter.close()
            await engine.close()

    asyncio.run(run())


def test_whole_request_never_dispatches_partial_token_reservation(tmp_path, monkeypatch):
    from skeleton.ai.runtime.inference.local import LocalInferenceEngine, LocalInferenceRequest, ReferenceNGramModel
    from skeleton.app.offline_runtime_whole_request import MeasuredWholeRequestEngine

    async def run():
        session, _, _ = session_fixture(tmp_path, monkeypatch)
        model = ReferenceNGramModel.train(["hello harbor hello harbor"])
        engine = LocalInferenceEngine(model, cache_size=0)
        # Deliberately reduce headroom until canonical iteration grants
        # cannot cover the requested atomic budget.
        monkeypatch.setattr("skeleton.app.offline_runtime_session.sample_hardware",
                            lambda: sample(start=time.monotonic_ns() - 1000, available=2 * GIB,
                                           origin="local_probe"))
        adapter = MeasuredWholeRequestEngine(session, engine, backend_digest=model.model_digest)
        request = LocalInferenceRequest("hello", max_output_tokens=8)
        try:
            await adapter.generate(request, max_input_tokens=48, timeout_ms=10000)
            result = await adapter.generate(request, max_input_tokens=48, timeout_ms=10000)
            assert result.result is None and result.receipt["status"] == "partial_grant_deferred"
        finally:
            adapter.close()
            await engine.close()

    asyncio.run(run())


def test_queue_close_reports_inflight_until_executor_releases(tmp_path, monkeypatch):
    queue, executor = make_queue(tmp_path, monkeypatch, max_active=1)
    queue.submit(BatchRequest("running", 2, 2), timeout_ms=10000)
    queue.tick()
    entered = threading.Event()
    resume = threading.Event()
    errors = []

    def blocked(*, request_id, phase, tokens, deadline_ns, cancel):
        entered.set()
        assert resume.wait(5)
        assert cancel.is_set()
        return Progress(request_id, phase, tokens)

    executor.run_slice = blocked

    def worker():
        try:
            queue.tick()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert entered.wait(5)
        queue.close()
        pending = queue.status()
        assert pending["closed"] and pending["iteration_in_progress"]
        assert not pending["drain_complete"]
        assert pending["capacity"]["kv_used_bytes"] > 0
        assert executor.releases == []
    finally:
        resume.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert not errors
    assert queue.status()["drain_complete"]
    assert queue.status()["capacity"]["kv_used_bytes"] == 0
    assert executor.releases == ["running"]
    with pytest.raises(RuntimePreflightError):
        queue.tick()
    assert not queue.status()["poisoned"]


def test_sealed_runtime_rechecks_pressure_during_copy(tmp_path, monkeypatch):
    if not hasattr(os, "memfd_create"):
        pytest.skip("Linux memfd unavailable")
    payload = b"real sealed source bytes"
    checksum = sha256(payload).hexdigest()
    model = ModelIdentity("test", "v1", "tiny", checksum, checksum, checksum)
    plan = WeightLoadPlan(model.identity_digest, (WeightShard(0, checksum, len(payload), "local"),), len(payload))
    path = tmp_path / "source.bin"
    path.write_bytes(payload)
    store = tmp_path / "store"
    key = WeightShardStore(store).stage_plan(model, plan, {0: path})
    checks = []

    def telemetry():
        checks.append(True)
        return sample(start=time.monotonic_ns() - 1000, origin="local_probe",
                      temperature=45 if len(checks) <= 2 else 95)

    monkeypatch.setattr("skeleton.app.offline_runtime_custody.sample_hardware", telemetry)
    with pytest.raises(RuntimePreflightError, match="resource pressure during sealed copy"):
        with sealed_cpu_custody(store, plan_digest=key, model=model, policy=POLICY,
                                maximum_sealed_bytes=len(payload)):
            pytest.fail("pressure-denied sealed source published")
    assert len(checks) == 3


def test_runtime_session_exclusive_consumer_revokes_existing_offer(tmp_path, monkeypatch):
    from skeleton.testing.test_offline_runtime_admission import work
    session, _, _ = session_fixture(tmp_path, monkeypatch)
    session.offer(work())
    pending = session.offer(work())["admission"]
    assert pending["status"] == "candidate"
    owner = session.claim_consumer()
    assert session.status()["exclusive_consumer_bound"]
    assert not session.status()["admission"]["pending"]
    with pytest.raises(RuntimePreflightError, match="no pending"):
        session.consume(pending, consumer=owner)
    with pytest.raises(RuntimePreflightError, match="already has"):
        session.claim_consumer()
    with pytest.raises(RuntimePreflightError, match="owner mismatch"):
        session.offer(work())
    with pytest.raises(RuntimePreflightError, match="owner mismatch"):
        session.revalidate_source(consumer=object())
    session.offer(work(), consumer=owner)
    next_grant = session.offer(work(), consumer=owner)["admission"]
    assert next_grant["status"] == "candidate"
    with pytest.raises(RuntimePreflightError, match="owner mismatch"):
        session.consume(next_grant, consumer=object())
    assert session.consume(next_grant, consumer=owner)
    session.close()


def test_queue_and_whole_request_cannot_share_one_session(tmp_path, monkeypatch):
    from skeleton.ai.runtime.inference.local import LocalInferenceEngine, ReferenceNGramModel
    from skeleton.app.offline_runtime_whole_request import MeasuredWholeRequestEngine
    policy = QueuePolicy()
    session, base, _ = session_fixture(tmp_path, monkeypatch, queue_policy=policy)
    queue = OfflineRequestQueue(session, policy, Executor(), base_policy=base)
    model = ReferenceNGramModel.train(["harbor lights harbor lights"])
    engine = LocalInferenceEngine(model, cache_size=0, max_concurrency=1)
    try:
        with pytest.raises(RuntimePreflightError, match="already has"):
            MeasuredWholeRequestEngine(session, engine, backend_digest=model.model_digest)
        with pytest.raises(RuntimePreflightError, match="already has"):
            OfflineRequestQueue(session, policy, Executor(), base_policy=base)
    finally:
        queue.close()
        asyncio.run(engine.close())


def test_whole_request_wait_timeout_does_not_consume_or_revoke_owner(tmp_path, monkeypatch):
    from skeleton.ai.runtime.inference.local import LocalInferenceEngine, LocalInferenceRequest, ReferenceNGramModel
    from skeleton.app.offline_runtime_whole_request import MeasuredWholeRequestEngine
    async def run():
        session, _, samples = session_fixture(tmp_path, monkeypatch)
        model = ReferenceNGramModel.train(["hello harbor hello"])
        engine = LocalInferenceEngine(model, cache_size=0, max_concurrency=1)
        adapter = MeasuredWholeRequestEngine(session, engine, backend_digest=model.model_digest)
        req = LocalInferenceRequest("hello", max_output_tokens=4, seed=1, tool_choice="none")
        await adapter._lock.acquire()
        try:
            with pytest.raises(RuntimePreflightError, match="expired while waiting"):
                await asyncio.wait_for(adapter.generate(req, max_input_tokens=16, timeout_ms=5), timeout=2)
            assert adapter._lock.locked()
            assert samples[0] == 0
            assert not session.status()["closed"]
        finally:
            adapter._lock.release()
            adapter.close()
            await engine.close()
    asyncio.run(run())


def test_large_unicode_result_uses_compact_custody_digest():
    from skeleton.ai.runtime.inference.local import LocalInferenceResult
    from skeleton.app.offline_runtime_whole_request import MeasuredWholeRequestEngine
    payload = "\U0001f30a" * 400_000
    result = LocalInferenceResult(payload, "fixture", "a" * 64, 1, 1)
    first = MeasuredWholeRequestEngine._finish({}, "completed", result)
    changed = replace(result, text=payload + "x")
    second = MeasuredWholeRequestEngine._finish({}, "completed", changed)
    assert first.result is result and second.result is changed
    assert first.receipt["output_digest"] != second.receipt["output_digest"]
    assert len(first.receipt["receipt_digest"]) == 64
    assert payload[:100] not in str(first.receipt)
