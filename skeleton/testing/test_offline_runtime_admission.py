"""Source and resource admission regression coverage for recovered local owners."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import io
import json
from pathlib import Path

import pytest

from skeleton.ai.model_runtime.device_placement import DeviceDescriptor, NativeGpuMemoryReceipt
from skeleton.ai.model_runtime.flgb_model_runtime import ModelIdentity, WeightLoadPlan, WeightShard
from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore
from skeleton.app.offline_cpu_budget import CpuTopology, MemoryTopology
from skeleton.app.offline_energy_budget import PowerObservation
from skeleton.app.offline_energy_hysteresis import HysteresisPolicy
from skeleton.app.offline_runtime_preflight import (
    HardwareSample, MIB, ModelSource, RuntimePolicy, RuntimePreflightError,
    digest, inspect_source, plan_preflight,
)
from skeleton.app.offline_runtime_control import RuntimeAdmission, parse_work
from skeleton.app.offline_runtime_cli import main, read_work

GIB = 1024 * MIB
POLICY = RuntimePolicy(verify_gguf_headers=False, host_reserve_bytes=GIB,
                       device_reserve_bytes=GIB, maximum_tokens=128, prefill_quantum=64,
                       bytes_per_worker=256 * MIB, maximum_workers=8)


def source(weights=(GIB, GIB)):
    shards = tuple(WeightShard(i, sha256(str(i).encode()).hexdigest(), count, "local")
                   for i, count in enumerate(weights))
    identity = "a" * 64
    plan = WeightLoadPlan(identity, shards, sum(weights))
    return ModelSource(plan.digest, identity, "b" * 64, plan, ())


def sample(*, start=1_000_000_000, available=12 * GIB, total=16 * GIB,
           temperature=45, ac=True, battery=90, gpu=None, origin="fixture"):
    cpu = CpuTopology(16, 8, 12.0, 8 * MIB, "fixture-affinity", "fixture-quota",
                      "fixture-cache", "fixture-platform")
    memory = MemoryTopology(total, available, "fixture-memory")
    power = PowerObservation(battery, ac, temperature, "fixture-battery",
                             "fixture-ac", "fixture-thermal")
    gpu = gpu or NativeGpuMemoryReceipt("unavailable", "unavailable", (), 0, 0)
    return HardwareSample(cpu, memory, power, gpu, start, start + 1, origin)


def work():
    return parse_work([
        {"request_id": "prefill", "phase": "prefill", "remaining_tokens": 1000,
         "priority": 0, "age": 0},
        {"request_id": "decode-a", "phase": "decode", "remaining_tokens": 20,
         "priority": 0, "age": 0},
        {"request_id": "decode-b", "phase": "decode", "remaining_tokens": 20,
         "priority": 0, "age": 0},
    ])


def measured_gpu(*, source_name="simulated_nvml", free=8 * GIB):
    return NativeGpuMemoryReceipt(source_name, "measured",
                                  (DeviceDescriptor("cuda-0", "cuda", free),),
                                  12 * GIB, free)


def test_cpu_placement_reserves_model_memory_and_hardware_pressure():
    model = source()
    reading = sample()
    plan = plan_preflight(model, reading, POLICY, now_ns=reading.finished_ns)
    assert plan["status"] == "candidate"
    assert plan["host_weight_bytes"] == 2 * GIB
    assert sum(row["bytes"] for row in plan["placement"]) == 2 * GIB
    assert plan["devices"][0]["memory_bytes"] == 11 * GIB
    assert plan["cpu_plan"]["memory_limit"] == 36
    assert plan["pressure_fraction"] == 1 - 10 / 16
    assert plan["worker_ceiling"] == 8
    assert plan["evidence_origin"] == "fixture"
    assert not plan["native_qualified"] and not plan["release_qualified"]
    assert digest({k: v for k, v in plan.items() if k != "preflight_digest"}) == plan["preflight_digest"]
    assert plan_preflight(model, reading, POLICY, now_ns=reading.finished_ns) == plan


def test_cpu_memory_reservation_reduces_workers_without_double_counting():
    reading = sample(available=3 * GIB + 512 * MIB)
    plan = plan_preflight(source(), reading, POLICY, now_ns=reading.finished_ns)
    assert plan["host_weight_bytes"] == 2 * GIB
    assert plan["cpu_plan"]["memory_limit"] == 2
    assert plan["worker_ceiling"] == 2


@pytest.mark.parametrize("reading,expected", [
    (sample(available=None), "host_memory_telemetry_unavailable"),
    (sample(available=2 * GIB), "canonical_placement_rejected"),
    (sample(temperature=90), "energy_or_worker_budget_zero"),
    (sample(ac=False, battery=5), "energy_or_worker_budget_zero"),
])
def test_fail_closed_resource_conditions(reading, expected):
    result = plan_preflight(source(), reading, POLICY, now_ns=reading.finished_ns)
    assert expected in result["blockers"]
    assert result["worker_ceiling"] == 0


def test_cuda_never_silently_falls_back_to_cpu():
    policy = replace(POLICY, backend="cuda")
    absent = sample()
    result = plan_preflight(source(), absent, policy, now_ns=absent.finished_ns)
    assert "cuda_memory_unavailable" in result["blockers"]
    assert not result["placement"]
    reading = sample(gpu=measured_gpu())
    ready = plan_preflight(source(), reading, policy, now_ns=reading.finished_ns)
    assert all(row["device_id"] == "cuda-0" for row in ready["placement"])
    assert ready["host_weight_bytes"] == 0
    assert ready["pressure_fraction"] == 0.5
    assert ready["worker_ceiling"] == 8
    assert not ready["native_qualified"]


def test_hybrid_whole_shard_placement_is_not_a_combined_virtual_pool():
    reading = sample(available=4 * GIB, gpu=measured_gpu(free=4 * GIB))
    policy = replace(POLICY, backend="hybrid")
    result = plan_preflight(source((5 * GIB,)), reading, policy, now_ns=reading.finished_ns)
    assert result["placement_status"] == "canonical_placement_rejected"
    assert result["worker_ceiling"] == 0


def test_stale_future_and_simulated_hardware_are_distinct():
    reading = sample()
    late = plan_preflight(source(), reading, POLICY, now_ns=reading.started_ns + POLICY.sample_age_ns + 1)
    early = plan_preflight(source(), reading, POLICY, now_ns=reading.started_ns)
    for result in (late, early):
        assert "stale_or_future_hardware_sample" in result["blockers"]
        assert result["worker_ceiling"] == 0
    with pytest.raises(RuntimePreflightError, match="simulated GPU"):
        sample(gpu=measured_gpu(), origin="local_probe")


def test_non_gguf_evidence_cannot_satisfy_framing_policy():
    reading = sample()
    with pytest.raises(RuntimePreflightError, match="framing required"):
        plan_preflight(source(), reading, replace(POLICY, verify_gguf_headers=True),
                       now_ns=reading.finished_ns)


def stage(root: Path):
    payload = b"actual locally staged model bytes"
    checksum = sha256(payload).hexdigest()
    model = ModelIdentity("offline-test", "revision-1", "tiny", checksum, checksum, checksum)
    shard = WeightShard(0, checksum, len(payload), "local")
    plan = WeightLoadPlan(model.identity_digest, (shard,), len(payload))
    path = root / "source.bin"
    path.write_bytes(payload)
    store = root / "store"
    key = WeightShardStore(store).stage_plan(model, plan, {0: path})
    return store, key, model.identity_digest


def test_real_selected_source_and_independent_pins(tmp_path):
    store, key, model = stage(tmp_path)
    result = inspect_source(store, plan_digest=key, model_identity_digest=model, policy=POLICY)
    assert result.plan_digest == key and result.model_identity_digest == model
    assert result.plan.expected_total_bytes > 0 and result.headers == ()
    assert str(store) not in json.dumps(result.snapshot())
    with pytest.raises(RuntimePreflightError, match="pinned identity"):
        inspect_source(store, plan_digest=key, model_identity_digest="0"*64, policy=POLICY)
    with pytest.raises(RuntimePreflightError, match="pinned identity"):
        inspect_source(store, plan_digest="0"*64, model_identity_digest=model, policy=POLICY)
    next((store / "objects").glob("*/*")).write_bytes(b"tampered")
    with pytest.raises(ValueError):
        inspect_source(store, plan_digest=key, model_identity_digest=model, policy=POLICY)


def test_gguf_framing_is_checked_by_owner_for_each_pinned_shard(tmp_path, monkeypatch):
    from skeleton.native.gguf_preflight import GGUFHeader
    store, key, model = stage(tmp_path)
    seen = []

    def inspect(path, *, expected_sha256, max_bytes):
        raw = path.read_bytes()
        assert sha256(raw).hexdigest() == expected_sha256 and len(raw) == max_bytes
        seen.append(expected_sha256)
        return GGUFHeader(3, 1, 0, len(raw), expected_sha256)

    monkeypatch.setattr("skeleton.app.offline_runtime_preflight.inspect_gguf", inspect)
    policy = replace(POLICY, verify_gguf_headers=True)
    result = inspect_source(store, plan_digest=key, model_identity_digest=model, policy=policy)
    assert seen == [result.plan.shards[0].digest]
    assert result.headers[0]["file_size"] == result.plan.shards[0].bytes
    # This is an explicitly mocked framing adapter test, never native evidence.


def controller():
    return RuntimeAdmission(source(), POLICY, hysteresis_policy=HysteresisPolicy(
        recovery_samples=2, recovery_cooldown_ns=0, max_sample_age_ns=POLICY.sample_age_ns))


def offer(owner, tick, *, origin="fixture", temperature=45):
    reading = sample(start=1_000_000_000 + tick * 10, origin=origin, temperature=temperature)
    result = owner.offer(reading, work(), now_ns=reading.finished_ns)
    return result["admission"], reading


def test_hysteresis_worker_limit_and_decode_priority_are_jointly_enforced():
    owner = controller()
    first, _ = offer(owner, 0)
    assert first["status"] == "no_grant"
    next, _ = offer(owner, 1)
    assert next["worker_ceiling"] == 1
    assert next["slices"] == [{"request_id": "decode-a", "phase": "decode", "tokens": 1}]
    assert next["scheduled_tokens"] <= next["token_ceiling"] <= POLICY.maximum_tokens
    hot, _ = offer(owner, 2, temperature=95)
    assert hot["worker_ceiling"] == 0 and hot["slices"] == []
    assert not owner.status()["pending"]


def test_fixture_history_cannot_prewarm_local_gate_or_authorize_consume():
    owner = controller()
    offer(owner, 0)
    receipt, reading = offer(owner, 1)
    with pytest.raises(RuntimePreflightError, match="fixture"):
        owner.consume(receipt, now_ns=reading.finished_ns)
    local, _ = offer(owner, 2, origin="local_probe")
    assert local["worker_ceiling"] == 0  # distinct sample origin, reset
    local, reading = offer(owner, 3, origin="local_probe")
    # This direct synthetic construction exercises the trusted-process API;
    # it does not claim an actual live physical sample.
    assert owner.consume(local, now_ns=reading.finished_ns) == tuple(local["slices"])
    with pytest.raises(RuntimePreflightError, match="no pending"):
        owner.consume(local, now_ns=reading.finished_ns)


def test_replayed_sample_clears_grant_and_old_proposals_are_invalid():
    owner = controller()
    offer(owner, 0, origin="local_probe")
    grant, reading = offer(owner, 1, origin="local_probe")
    replay = owner.offer(reading, work(), now_ns=reading.finished_ns + 1)["admission"]
    assert replay["worker_ceiling"] == 0
    assert "replayed_or_nonadvancing_hardware_sample" in replay["blockers"]
    with pytest.raises(RuntimePreflightError, match="no pending"):
        owner.consume(grant, now_ns=reading.finished_ns + 1)


def test_tamper_expiry_and_restart_never_inherit_grants():
    owner = controller()
    offer(owner, 0, origin="local_probe")
    grant, reading = offer(owner, 1, origin="local_probe")
    forged = deepcopy(grant)
    forged["slices"][0]["tokens"] = 999
    forged["admission_digest"] = digest({k: v for k, v in forged.items() if k != "admission_digest"})
    with pytest.raises(RuntimePreflightError, match="exact pending"):
        owner.consume(forged, now_ns=reading.finished_ns)
    offer(owner, 2, origin="local_probe")
    grant, reading = offer(owner, 3, origin="local_probe")
    with pytest.raises(RuntimePreflightError, match="stale"):
        owner.consume(grant, now_ns=grant["expires_ns"] + 1)
    with pytest.raises(RuntimePreflightError, match="no pending"):
        controller().consume(grant, now_ns=reading.finished_ns)
    offer(owner, 4, origin="local_probe")
    owner.revoke()
    assert not owner.status()["pending"] and owner.status()["hysteresis_workers"] == 0


@pytest.mark.parametrize("raw", [
    b'[{"request_id":"a","request_id":"b"}]', b"[NaN]", b"{}",
    b"x" * (1024 * 1024 + 1),
])
def test_work_document_is_bounded_and_strict(raw):
    with pytest.raises(ValueError):
        read_work(io.BytesIO(raw))


def test_cli_reuses_real_store_and_explicit_fixture_probe(tmp_path, monkeypatch):
    store, key, model = stage(tmp_path)
    reading = sample()
    monkeypatch.setattr("skeleton.app.offline_runtime_cli.sample_hardware", lambda: reading)
    monkeypatch.setattr("skeleton.app.offline_runtime_cli.time.monotonic_ns", lambda: reading.finished_ns)
    out, err = io.StringIO(), io.StringIO()
    opts = ["--store", str(store), "--plan-sha", key, "--model-identity-sha", model,
            "--skip-gguf-framing"]
    rc = main(["preflight", *opts], stdout=out, stderr=err)
    assert rc == 0, err.getvalue()
    result = json.loads(out.getvalue())
    assert result["source"]["plan_digest"] == key
    assert result["evidence_origin"] == "fixture"
    assert result["model_activation"] == "not_performed"
    assert str(store) not in out.getvalue()
    out, err = io.StringIO(), io.StringIO()
    assert main(["preflight", *opts, "--model-identity-sha", "0"*64],
                stdout=out, stderr=err) == 2
    assert not out.getvalue() and str(store) not in err.getvalue()


def test_runtime_session_owns_clock_and_revokes_on_source_reinspection(tmp_path, monkeypatch):
    from skeleton.app.offline_runtime_session import OfflineRuntimeSession
    store, key, model = stage(tmp_path)
    tick = [1_000_000_000]
    # Synthetic hardware is deliberately mocked in this regression.
    monkeypatch.setattr("skeleton.app.offline_runtime_session.time.monotonic_ns", lambda: tick[0] + 1)
    monkeypatch.setattr("skeleton.app.offline_runtime_session.sample_hardware",
                        lambda: sample(start=tick[0], origin="local_probe"))
    session = OfflineRuntimeSession(store, plan_digest=key, model_identity_digest=model,
                                    policy=POLICY, hysteresis=HysteresisPolicy(
                                        recovery_samples=2, recovery_cooldown_ns=0,
                                        max_sample_age_ns=POLICY.sample_age_ns))
    with session:
        assert session.offer(work())["admission"]["status"] == "no_grant"
        tick[0] += 10
        grant = session.offer(work())["admission"]
        assert grant["status"] == "candidate"
        assert session.consume(grant) == tuple(grant["slices"])
        tick[0] += 10
        new = session.offer(work())["admission"]
        assert new["status"] == "candidate"
        assert session.revalidate_source()["source_status"] == "reinspected"
        with pytest.raises(RuntimePreflightError, match="no pending"):
            session.consume(new)
        next((store / "objects").glob("*/*")).write_bytes(b"changed")
        with pytest.raises(ValueError):
            session.revalidate_source()
        assert session.status()["closed"]
        with pytest.raises(RuntimePreflightError, match="closed"):
            session.offer(work())
    assert session.status()["closed"]


def test_gpu_aggregate_drift_rejected_and_source_label_not_published():
    invalid = NativeGpuMemoryReceipt("simulated_nvml", "measured",
                                     (DeviceDescriptor("cuda-0", "cuda", GIB),),
                                     8 * GIB, 2 * GIB)
    with pytest.raises(RuntimePreflightError, match="aggregate"):
        sample(gpu=invalid)
    original = source()
    shard = WeightShard(0, original.plan.shards[0].digest, GIB, "/private/model/path")
    plan = WeightLoadPlan(original.model_identity_digest, (shard,), GIB)
    redacted = ModelSource(plan.digest, original.model_identity_digest,
                            original.inventory_digest, plan, ())
    assert "/private/model/path" not in json.dumps(redacted.snapshot())
    assert redacted.snapshot()["shards"][0]["source_label_digest"] == digest(shard.source)


def test_nonadvancing_offer_clock_and_invalid_consume_revoke_grants():
    owner = controller()
    initial, _ = offer(owner, 0, origin="local_probe")
    grant, reading = offer(owner, 1, origin="local_probe")
    assert grant["status"] == "candidate"
    with pytest.raises(RuntimePreflightError, match="consumption timestamp"):
        owner.consume(grant, now_ns=True)
    with pytest.raises(RuntimePreflightError, match="no pending"):
        owner.consume(grant, now_ns=reading.finished_ns)
    newer = sample(start=reading.started_ns + 1, origin="local_probe")
    invalid = owner.offer(newer, work(), now_ns=reading.finished_ns)["admission"]
    assert invalid["status"] == "no_grant"
    assert "nonadvancing_offer_clock" in invalid["blockers"]


def test_runtime_policy_and_source_bindings_cannot_be_reassigned():
    owner = controller()
    with pytest.raises(AttributeError):
        owner.policy = replace(POLICY, maximum_workers=256)
    with pytest.raises(AttributeError):
        owner.source = source((GIB,))
    from skeleton.ai.model_runtime.iteration_scheduler import IterationWork
    malformed = (IterationWork("typed", "prefill", 2),)
    reading = sample()
    with pytest.raises(RuntimePreflightError, match="typed iteration work and phase"):
        owner.offer(reading, malformed, now_ns=reading.finished_ns)


def test_scoped_headroom_intersects_host_and_windows_commit_without_false_credit():
    from skeleton.ai.runtime.inference.adaptive_serving import ServingResources
    from skeleton.app.offline_runtime_preflight import intersect_scoped_headroom
    memory = MemoryTopology(16 * GIB, 12 * GIB, "host-fixture")
    narrow = ServingResources(available_memory_bytes=3 * GIB, commit_available_bytes=2 * GIB)
    assert intersect_scoped_headroom(memory, narrow).available_bytes == 2 * GIB
    unknown = ServingResources(commit_available_bytes=10 * GIB)
    assert intersect_scoped_headroom(memory, unknown).available_bytes is None
    wide = ServingResources(available_memory_bytes=30 * GIB)
    assert intersect_scoped_headroom(memory, wide).available_bytes == 12 * GIB


def test_all_live_probes_use_scoped_evidence_and_reject_critical_pressure(monkeypatch):
    from skeleton.ai.runtime.inference.adaptive_serving import ServingResources
    from skeleton.app import offline_runtime_preflight as owner

    fixture = sample()
    monkeypatch.setattr(owner, "probe_cpu_topology", lambda: fixture.cpu)
    monkeypatch.setattr(owner, "probe_memory_topology", lambda: fixture.memory)
    monkeypatch.setattr(owner, "probe_power", lambda: fixture.power)
    monkeypatch.setattr(owner, "probe_linux_nvidia_memory", lambda: fixture.gpu)
    seen = []
    measured = ServingResources(available_memory_bytes=4 * GIB,
                                memory_used_fraction=0.25,
                                memory_full_stall_fraction=0.2,
                                source="scoped-fixture")

    def collect(*, fresh=False):
        seen.append(fresh)
        return measured

    monkeypatch.setattr("skeleton.ai.runtime.inference.local.sample_serving_resources", collect)
    observation = owner.sample_hardware()
    assert seen == [True]
    assert observation.memory.available_bytes == 4 * GIB
    assert observation.scoped_pressure == "critical"
    assert observation.scoped_observation_digest == digest(measured.as_dict())
    result = plan_preflight(source(), observation, POLICY, now_ns=observation.finished_ns)
    assert result["status"] == "blocked"
    assert "canonical_scoped_serving_pressure_critical" in result["blockers"]
    assert result["worker_ceiling"] == 0


def test_scoped_pressure_provenance_pair_is_validated():
    with pytest.raises(RuntimePreflightError, match="incomplete scoped"):
        replace(sample(), scoped_pressure="normal")
    with pytest.raises(RuntimePreflightError, match="invalid scoped"):
        replace(sample(), scoped_pressure="invented", scoped_observation_digest="a" * 64)
    recorded = replace(sample(), scoped_pressure="recovering", scoped_observation_digest="a" * 64)
    assert recorded.snapshot()["scoped_pressure"] == "recovering"


def test_failed_offer_discards_warmed_recovery_state():
    owner = controller()
    offer(owner, 0, origin="local_probe")
    candidate, reading = offer(owner, 1, origin="local_probe")
    assert candidate["status"] == "candidate"
    with pytest.raises(RuntimePreflightError):
        owner.offer(reading, work(), now_ns=True)
    assert not owner.status()["pending"]
    assert owner.status()["hysteresis_workers"] == 0
    recovered, _ = offer(owner, 2, origin="local_probe")
    assert recovered["status"] == "no_grant"
    recovered, _ = offer(owner, 3, origin="local_probe")
    assert recovered["status"] == "candidate"


def test_exact_expiry_instant_cannot_authorize_consumption():
    owner = controller()
    offer(owner, 0, origin="local_probe")
    receipt, _ = offer(owner, 1, origin="local_probe")
    with pytest.raises(RuntimePreflightError, match="stale or future"):
        owner.consume(receipt, now_ns=receipt["expires_ns"])
    assert not owner.status()["pending"]
