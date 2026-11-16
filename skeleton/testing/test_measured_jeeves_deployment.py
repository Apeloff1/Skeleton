"""Measured guarded startup and real llama.cpp launch-hook regressions.

The tiny GGUF framing and executable are deliberately not a working model.
These tests exercise the actual deployment/launch control flow without
starting a native subprocess. Hardware and tokenizer attestations used here
are explicit test fixtures, never operational qualification.
"""
from __future__ import annotations

import asyncio
import io
import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import struct
import sys
import threading
from types import SimpleNamespace
import time

import pytest

from skeleton.ai.model_runtime.flgb_model_runtime import WeightLoadPlan, WeightShard
from skeleton.ai.runtime.inference.adaptive_serving import ServingResources
from skeleton.ai.runtime.inference.deployment import (
    LocalModelDeploymentError, create_local_model_deployment,
)
from skeleton.ai.runtime.inference.guarded_composition import ProtectedLocalComponents
from skeleton.ai.runtime.inference.llama_cpp import LlamaCppModel, LlamaCppRuntimeError
from skeleton.ai.runtime.inference.local import LocalInferenceRequest
from skeleton.app.offline_runtime_llama_binding import (
    MeasuredLlamaCpuGate, MeasuredLocalDeployment,
)
from skeleton.app.offline_runtime_preflight import ModelSource, RuntimePreflightError
from skeleton.provider_runtime import ProviderRegistry, ProviderUnavailableError, ProviderPolicyError
from skeleton.testing.test_offline_runtime_admission import POLICY, GIB, sample


@pytest.fixture
def authored(tmp_path):
    path = tmp_path / "tiny.gguf"
    path.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 1, 0))
    deployment = create_local_model_deployment(
        tmp_path / "deployment.json", executable_path=Path(sys.executable).resolve(),
        model_path=path, model_id="jeeves", context_size=128, threads=2,
        gpu_layers=0, kv_cache_location="host", kv_bytes_per_token=64,
        runtime_scratch_bytes=0,
    )
    checksum = sha256(path.read_bytes()).hexdigest()
    model_identity = "a" * 64
    plan = WeightLoadPlan(model_identity, (WeightShard(0, checksum, 24, "local"),), 24)
    source = ModelSource(plan.digest, model_identity, "b" * 64, plan, (
        {"version": 3, "tensor_count": 1, "metadata_count": 0,
         "file_size": 24, "sha256": checksum},))
    policy = replace(POLICY, verify_gguf_headers=True)
    spec = MeasuredLocalDeployment(
        deployment.manifest_digest, sha256(deployment.manifest_path.read_bytes()).hexdigest(),
        1 << 40, tmp_path, plan.digest, model_identity, policy,
    )
    backend = LlamaCppModel(deployment.llama_cpp_config(rehash_artifacts_each_run=True))
    return SimpleNamespace(deployment=deployment, backend=backend, source=source,
                           policy=policy, spec=spec)


def install_probes(monkeypatch, *, available=12 * GIB, scoped=12 * GIB,
                   temperature=45, memory_stall=0.0, origin="local_probe"):
    # Timestamp and counters are synthetic in these tests. The actual gate
    # and actual backend control flow are not mocked.
    monkeypatch.setattr("skeleton.app.offline_runtime_llama_binding.sample_hardware",
                        lambda: sample(start=time.monotonic_ns() - 1000, available=available,
                                       temperature=temperature, origin=origin))
    monkeypatch.setattr("skeleton.app.offline_runtime_llama_binding.sample_serving_resources",
                        lambda *, fresh=False: ServingResources(memory_used_fraction=0.25,
                                                 available_memory_bytes=scoped,
                                                 memory_stall_fraction=memory_stall,
                                                 source="test-fixture"))


def protected_components():
    # This attestor is intentionally a fixture, not a production tokenizer.
    return ProtectedLocalComponents(
        snapshots=SimpleNamespace(resolve=lambda *args, **kw: None),
        reviewer=lambda *args, **kw: None,
        tokenize=lambda text: list(text.encode()),
        detokenize=lambda ids: bytes(ids).decode(),
        verify_native_tokenizer=lambda *args: True,
        sampler_support=lambda *args: False,
        projection_attestor=lambda *args: False,
    )


def test_real_backend_gate_binds_weight_and_explicit_native_profile(authored, monkeypatch):
    install_probes(monkeypatch)
    gate = MeasuredLlamaCpuGate(authored.backend, authored.source, authored.policy)
    authored.backend.install_prelaunch_resource_guard(gate)
    gate()
    status = gate.status()
    assert status["last"]["status"] == "candidate"
    assert status["last"]["kv_reserve_bytes"] == 128 * 64
    assert status["last"]["threads"] == 2
    assert status["last"]["model_digest"] == authored.backend.model_digest
    assert not status["native_qualified"]
    status["last"]["threads"] = 999
    assert gate.status()["last"]["threads"] == 2
    with pytest.raises(LlamaCppRuntimeError):
        authored.backend.install_prelaunch_resource_guard(lambda: None)
    gate.close()
    with pytest.raises(RuntimePreflightError, match="closed"):
        gate()


def test_critical_memory_stall_and_scoped_headroom_cannot_be_hidden_by_host_ram(authored, monkeypatch):
    gate = MeasuredLlamaCpuGate(authored.backend, authored.source, authored.policy)
    install_probes(monkeypatch, scoped=256 * 1024**2)
    with pytest.raises(RuntimePreflightError, match="launch denied"):
        gate()
    assert gate.status()["last"]["status"] == "blocked"
    install_probes(monkeypatch, memory_stall=0.6)
    with pytest.raises(RuntimePreflightError, match="launch denied"):
        gate()
    assert "canonical_serving_memory_stall_critical" in gate.status()["last"]["blockers"]
    install_probes(monkeypatch, scoped=None)
    with pytest.raises(RuntimePreflightError, match="launch denied"):
        gate()
    assert "host_memory_telemetry_unavailable" in gate.status()["last"]["blockers"]


def test_real_native_infer_rechecks_before_spawn_and_never_launches_under_new_pressure(authored, monkeypatch):
    gate = MeasuredLlamaCpuGate(authored.backend, authored.source, authored.policy)
    authored.backend.install_prelaunch_resource_guard(gate)
    reads = []

    def observe():
        reads.append(True)
        return sample(start=time.monotonic_ns() - 1000,
                      temperature=45 if len(reads) == 1 else 95, origin="local_probe")

    install_probes(monkeypatch)
    monkeypatch.setattr("skeleton.app.offline_runtime_llama_binding.sample_hardware", observe)
    monkeypatch.setattr("skeleton.ai.runtime.inference.llama_cpp.subprocess.Popen",
                        lambda *args, **kw: pytest.fail("native process must not start"))
    with pytest.raises(RuntimePreflightError, match="launch denied"):
        authored.backend.infer(LocalInferenceRequest("hello", max_output_tokens=1, tool_choice="none"),
                               threading.Event())
    assert len(reads) == 2
    assert gate.status()["checks"] == 2
    assert gate.status()["last"]["status"] == "blocked"


def test_gate_rejects_fixture_origin_and_disagreed_source(authored, monkeypatch):
    gate = MeasuredLlamaCpuGate(authored.backend, authored.source, authored.policy)
    install_probes(monkeypatch, origin="fixture")
    with pytest.raises(RuntimePreflightError, match="real local probe"):
        gate()
    shard = WeightShard(0, "c" * 64, 24, "local")
    plan = WeightLoadPlan(authored.source.model_identity_digest, (shard,), 24)
    wrong = ModelSource(plan.digest, plan.model_identity_digest, "b" * 64, plan,
                        ({**authored.source.headers[0], "sha256": shard.digest},))
    with pytest.raises(RuntimePreflightError, match="differs from verified"):
        MeasuredLlamaCpuGate(authored.backend, wrong, authored.policy)
    with pytest.raises(RuntimePreflightError, match="CPU and GGUF"):
        MeasuredLlamaCpuGate(authored.backend, authored.source, replace(authored.policy, verify_gguf_headers=False))


def use_source(authored, monkeypatch):
    def read_source(path, *, plan_digest, model_identity_digest, policy):
        assert plan_digest == authored.spec.plan_digest
        assert model_identity_digest == authored.spec.model_identity_digest
        return authored.source
    monkeypatch.setattr("skeleton.app.offline_runtime_llama_binding.inspect_source", read_source)


def test_raw_manifest_pin_is_enforced_before_model_activation(authored, monkeypatch):
    use_source(authored, monkeypatch)
    original = authored.deployment.manifest_path.read_bytes()
    authored.deployment.manifest_path.write_bytes(original + b" ")
    with pytest.raises(LocalModelDeploymentError, match="digest pin"):
        authored.spec.activate(authored.deployment.manifest_path, components=protected_components(),
                               default_seed=0, max_queue_size=2, max_batch_size=1)


def local_environment(authored, monkeypatch):
    for name in ("AI_LOCAL_MODEL_PATH", "AI_LOCAL_MODEL_CATALOG_PATH", "AI_SECONDARY_API_KEY",
                 "AI_SECONDARY_BASE_URL", "AI_SECONDARY_MODEL", "AI_VERIFICATION_MODEL",
                 "AI_LOCAL_MODEL_CACHE_SIZE", "AI_LOCAL_MODEL_MAX_CONCURRENCY",
                 "AI_LOCAL_MODEL_MAX_QUEUE_SIZE", "AI_LOCAL_MODEL_MAX_BATCH_SIZE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JEEVES_LOCAL_ONLY", "1")
    monkeypatch.setenv("JEEVES_PRIMARY_MODEL_ID", "jeeves")
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("AI_LOCAL_GUARD_REQUIRED", "1")
    monkeypatch.setenv("AI_LOCAL_DEPLOYMENT_PATH", str(authored.deployment.manifest_path))
    use_source(authored, monkeypatch)


def test_provider_registry_activates_existing_protected_jeeves_route(authored, monkeypatch):
    local_environment(authored, monkeypatch)
    registry = ProviderRegistry.from_env(guarded_components=protected_components(),
                                         measured_local_deployment=authored.spec)
    active = registry.active
    assert active.provider_id == "local" and active.model == "jeeves"
    assert active.require_guarded_inference
    assert active.engine.require_guarded_context
    assert active.engine.max_concurrency == 1 and active.engine.cache_size == 0
    assert registry.measured_local_status()["checks"] == 0
    assert registry.redundancy_status()["fallback_providers"] == []
    # The actual registered engine may not be invoked outside its guard.
    with pytest.raises(ProviderPolicyError):
        asyncio.run(active.engine.generate(LocalInferenceRequest("hello")))
    asyncio.run(active.close())
    assert registry.measured_local_status()["closed"]
    assert not active.available


@pytest.mark.parametrize("variable,value", [
    ("AI_LOCAL_MODEL_CACHE_SIZE", "1"),
    ("AI_LOCAL_MODEL_MAX_CONCURRENCY", "2"),
    ("AI_LOCAL_GUARD_REQUIRED", "0"),
    ("AI_PROVIDER", "openai"),
])
def test_measured_registry_refuses_downgrade_and_preserves_no_fallback(authored, monkeypatch, variable, value):
    local_environment(authored, monkeypatch)
    monkeypatch.setenv(variable, value)
    with pytest.raises(ProviderUnavailableError):
        ProviderRegistry.from_env(guarded_components=protected_components(),
                                  measured_local_deployment=authored.spec)


def test_measured_registry_unavailable_not_legacy_fallback_on_pin_failure(authored, monkeypatch):
    local_environment(authored, monkeypatch)
    broken = replace(authored.spec, manifest_sha256="0" * 64)
    registry = ProviderRegistry.from_env(guarded_components=protected_components(),
                                         measured_local_deployment=broken, retain_unavailable=True)
    assert not registry.active.available
    assert registry.measured_local_status() is None
    assert registry.redundancy_status()["fallback_providers"] == []


def test_latest_evidence_failure_never_leaves_old_candidate(authored, monkeypatch):
    install_probes(monkeypatch)
    gate = MeasuredLlamaCpuGate(authored.backend, authored.source, authored.policy)
    gate()
    assert gate.status()["last"]["status"] == "candidate"
    install_probes(monkeypatch, origin="fixture")
    with pytest.raises(RuntimePreflightError, match="real local probe"):
        gate()
    assert gate.status()["checks"] == 2
    assert gate.status()["last"]["status"] == "blocked"
    assert gate.status()["last"]["blockers"] == ["native_evidence_check_failed"]
    assert gate.status()["last"]["worker_ceiling"] == 0


def test_spawn_fence_requests_uncached_collection(authored, monkeypatch):
    install_probes(monkeypatch)
    samples = []

    def scoped(*, fresh=False):
        samples.append(fresh)
        return ServingResources(memory_used_fraction=0.25 if len(samples) == 1 else 0.995,
                                available_memory_bytes=12 * GIB, source="test-fixture")

    monkeypatch.setattr("skeleton.app.offline_runtime_llama_binding.sample_serving_resources", scoped)
    gate = MeasuredLlamaCpuGate(authored.backend, authored.source, authored.policy)
    gate()
    with pytest.raises(RuntimePreflightError, match="launch denied"):
        gate()
    assert samples == [True, True]
    assert gate.status()["last"]["serving_pressure"] == "critical"


def test_serving_sampler_fresh_bypasses_existing_cache(monkeypatch):
    from skeleton.ai.runtime.inference import local
    calls = []
    now = time.monotonic()
    old = ServingResources(available_memory_bytes=GIB, source="cached-test")
    new = ServingResources(available_memory_bytes=0, source="fresh-test")

    def collect():
        calls.append(True)
        return new

    monkeypatch.setattr(local, "_RESOURCE_COLLECTION", (now, old))
    monkeypatch.setattr(local.time, "monotonic", lambda: now)
    monkeypatch.setattr(local.os, "name", "posix")
    monkeypatch.setattr(local.sys, "platform", "linux")
    monkeypatch.setattr(local, "_sample_linux_resources", collect)
    assert local.sample_serving_resources() is old
    assert local.sample_serving_resources(fresh=True) is new
    assert calls == [True]
    assert local.sample_serving_resources() is new


def test_pre_activation_inspection_is_neither_provider_nor_transferable_grant(authored, monkeypatch):
    use_source(authored, monkeypatch)
    install_probes(monkeypatch)
    monkeypatch.setattr("skeleton.ai.runtime.inference.llama_cpp.subprocess.Popen",
                        lambda *args, **kw: pytest.fail("inspection must not start a child"))
    candidate = authored.spec.inspect(authored.deployment.manifest_path)
    assert candidate["status"] == "candidate"
    assert candidate["model_is_jeeves"]
    assert candidate["provider_activation"] == "not_performed"
    assert candidate["protected_authorities"] == "not_assessed"
    assert not candidate["transferable_grant"] and not candidate["native_qualified"]
    assert str(authored.deployment.manifest_path) not in json.dumps(candidate)
    install_probes(monkeypatch, scoped=0)
    blocked = authored.spec.inspect(authored.deployment.manifest_path)
    assert blocked["status"] == "blocked"
    assert blocked["observation"]["worker_ceiling"] == 0
    authored.deployment.manifest_path.write_bytes(b"{}")
    with pytest.raises(RuntimePreflightError, match="source or profile unavailable"):
        authored.spec.inspect(authored.deployment.manifest_path)


def test_installed_deployment_check_reports_pressure_and_no_activation(authored, monkeypatch):
    from skeleton.app.offline_runtime_cli import main
    use_source(authored, monkeypatch)
    install_probes(monkeypatch, scoped=0)
    args = ["deployment-check", "--store", str(authored.spec.store_path),
            "--plan-sha", authored.spec.plan_digest,
            "--model-identity-sha", authored.spec.model_identity_digest,
            "--deployment", str(authored.deployment.manifest_path),
            "--manifest-sha256", authored.spec.manifest_sha256,
            "--manifest-digest", authored.spec.manifest_digest,
            "--deployment-budget-mib", "1048576", "--require-candidate"]
    out, err = io.StringIO(), io.StringIO()
    assert main(args, stdout=out, stderr=err) == 3
    result = json.loads(out.getvalue())
    assert result["status"] == "blocked" and not result["transferable_grant"]
    assert not err.getvalue()
    out, err = io.StringIO(), io.StringIO()
    assert main(args + ["--skip-gguf-framing"], stdout=out, stderr=err) == 2
    assert not out.getvalue() and str(authored.spec.store_path) not in err.getvalue()


def test_server_startup_requires_trusted_bootstrap_and_typed_model_pin(authored):
    from skeleton.api.server import ServerState, create_app
    with pytest.raises(RuntimeError, match="trusted protected bootstrap"):
        create_app(measured_local_deployment=authored.spec)
    with pytest.raises(TypeError, match="preconfigured"):
        create_app(measured_local_deployment={})
    state = ServerState()
    with pytest.raises(TypeError):
        state.configure_engine_measured_deployment({})
    state.configure_engine_measured_deployment(authored.spec)
    with pytest.raises(RuntimeError, match="rebound"):
        state.configure_engine_measured_deployment(authored.spec)
    with pytest.raises(RuntimeError, match="requires native guard and canonical Mongo"):
        state.bind_engine_execution_service()
    assert state.engine_execution_service is None
    assert state.engine_execution_coordinator is None
    state = ServerState()
    state._engine_shutdown_pending = True
    with pytest.raises(RuntimeError, match="before engine startup"):
        state.configure_engine_measured_deployment(authored.spec)


def test_server_registry_factory_preserves_canonical_governed_route(authored, monkeypatch):
    from skeleton.api.server import ServerState
    from skeleton.intelligence.admission_runtime import AdmissionRuntime
    local_environment(authored, monkeypatch)
    registry = ServerState._activate_engine_provider_registry(
        admission_runtime=AdmissionRuntime(),
        guarded_local_components=protected_components(),
        measured_local_deployment=authored.spec,
    )
    assert registry.active.model == "jeeves"
    assert registry.active.require_guarded_inference
    assert registry.measured_local_status()["checks"] == 0
    asyncio.run(registry.active.close())


def test_guarded_deployment_binds_shared_native_slot(authored, monkeypatch, tmp_path):
    import os
    from skeleton.app.offline_native_process_lease import NativeCpuLeaseOwner, NativeLeaseError

    if os.name != "posix":
        pytest.skip("POSIX native lease required")
    local_environment(authored, monkeypatch)
    install_probes(monkeypatch)
    directory = tmp_path / "native-slot"
    directory.mkdir(mode=0o700)
    spec = replace(authored.spec, lease_directory=directory.resolve())
    registry = ProviderRegistry.from_env(guarded_components=protected_components(),
                                         measured_local_deployment=spec)
    backend = registry.active.engine.model
    assert registry.measured_local_status()["shared_native_lease"]["acquired"] == 0
    # Exercise the actual activated launch-owner callback without generating
    # text or invoking the framing-only fixture as a native model.
    lease = backend._resource_lease_factory()
    try:
        assert len(lease.child_pass_fds()) == 1
        observed = registry.measured_local_status()
        assert observed["checks"] == 1
        assert observed["shared_native_lease"]["owned_parent_references"] == 1
        other = NativeCpuLeaseOwner(directory.resolve(), lambda: None)
        with pytest.raises(NativeLeaseError, match="already held"):
            other.acquire()
    finally:
        lease()
        asyncio.run(registry.active.close())
    assert registry.measured_local_status()["shared_native_lease"]["owned_parent_references"] == 0
