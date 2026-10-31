"""Deterministic native CPU execution boundary tests; not device qualification."""
from __future__ import annotations

from dataclasses import replace
import pytest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.fair_stream_session import DispatchPermit
from skeleton.ai.model_runtime.native_fair_stream_backend import (
    NativeFairStreamBackend, NativeFairStreamDenied, NativePromptRegistry,
    pin_native_prompt,
)
from skeleton.app.offline_native_fair_stream import stage_native_cpu_prompt

SESSION = "a" * 32
LEASE = "b" * 64
CHECKPOINT = "c" * 64


def native():
    return NativeLLMRuntime(
        TinyTransformer(vocab=("hello", "world"), dim=8, ctx=24, seed=3),
    )


def permit(tokens=2):
    return DispatchPermit(
        lease_id=LEASE, request_id="request-1", generation=3,
        checkpoint_digest=CHECKPOINT, tokens=tokens,
        bytes_reserved=tokens * 16,
    )


def state(lease=None, *, tenant="alice"):
    p = lease or permit()
    return {
        "session_id": SESSION, "generation": p.generation,
        "checkpoint_digest": p.checkpoint_digest,
        "checkpoint": {
            "pending": [{
                "lease_id": p.lease_id, "request_id": p.request_id,
                "tenant_id": tenant, "tokens": p.tokens,
                "bytes_reserved": p.bytes_reserved,
            }],
            "requests": [{
                "request_id": p.request_id, "tenant_id": tenant,
                "bytes_per_token": 16,
            }],
        },
    }


def setup():
    runtime = native()
    registry = NativePromptRegistry(session_id=SESSION)
    stage_native_cpu_prompt(
        runtime=runtime, registry=registry,
        request_id="request-1", tenant_id="alice",
        prompt="hello", max_output_tokens=2,
    )
    return runtime, registry, NativeFairStreamBackend(runtime, registry)


def test_real_native_cpu_generation_consumes_one_grant():
    _, registry, backend = setup()
    consumed, output = backend.generate(permit(), state())
    assert type(consumed) is int and 0 <= consumed <= 2
    assert type(output) is bytes
    assert len(output) <= (1 << 20)
    assert registry.status()["consumed_or_revoked"] == 1
    with pytest.raises(NativeFairStreamDenied, match="missing authorized"):
        backend.generate(permit(), state())


def test_wrong_tenant_fails_without_consuming_authorization():
    _, registry, backend = setup()
    with pytest.raises(NativeFairStreamDenied, match="missing authorized"):
        backend.generate(permit(), state(tenant="bob"))
    assert registry.status()["staged"] == 1


def test_stale_checkpoint_fails_before_claim():
    _, registry, backend = setup()
    invalid = state()
    invalid["checkpoint_digest"] = "d" * 64
    with pytest.raises(NativeFairStreamDenied, match="generation mismatch"):
        backend.generate(permit(), invalid)
    assert registry.status()["staged"] == 1


def test_memory_accounting_mismatch_denies_before_native_call():
    _, registry, backend = setup()
    p = replace(permit(), bytes_reserved=31)
    with pytest.raises(NativeFairStreamDenied, match="memory accounting"):
        backend.generate(p, state(p))
    assert registry.status()["staged"] == 1


def test_unqualified_device_receipt_fails_closed():
    runtime, registry, backend = setup()
    runtime.model.device = "mps"
    with pytest.raises(NativeFairStreamDenied, match="device"):
        backend.generate(permit(), state())
    assert registry.status()["staged"] == 1


def test_model_mutation_fails_before_claim():
    runtime, registry, backend = setup()
    runtime.model.E[0][0] += 1.0
    with pytest.raises(NativeFairStreamDenied, match="identity drift"):
        backend.generate(permit(), state())
    assert registry.status()["staged"] == 1


def test_duplicate_request_rejected_and_revocation_is_irreversible():
    runtime, registry, _ = setup()
    pinned = pin_native_prompt(
        runtime, session_id=SESSION, request_id="request-1",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    with pytest.raises(NativeFairStreamDenied, match="duplicate"):
        registry.stage(pinned)
    registry.revoke("request-1")
    with pytest.raises(NativeFairStreamDenied, match="duplicate"):
        registry.stage(pinned)


def test_prompt_digest_tamper_is_rejected():
    runtime = native()
    good = pin_native_prompt(
        runtime, session_id=SESSION, request_id="request-1",
        tenant_id="alice", prompt="hello", max_output_tokens=2,
    )
    with pytest.raises(NativeFairStreamDenied, match="identity mismatch"):
        replace(good, prompt_digest="0" * 64)


@pytest.mark.parametrize("prompt", ["", "hello" * 100_000, "\ud800"])
def test_invalid_prompt_never_admitted(prompt):
    runtime = native()
    with pytest.raises(NativeFairStreamDenied):
        pin_native_prompt(
            runtime, session_id=SESSION, request_id="r",
            tenant_id="alice", prompt=prompt, max_output_tokens=2,
        )


def test_token_cap_and_session_boundaries():
    runtime = native()
    with pytest.raises(NativeFairStreamDenied, match="output"):
        pin_native_prompt(
            runtime, session_id=SESSION, request_id="r",
            tenant_id="alice", prompt="hello", max_output_tokens=True,
        )
    registry = NativePromptRegistry(session_id=SESSION)
    other = pin_native_prompt(
        runtime, session_id="f" * 32, request_id="r",
        tenant_id="alice", prompt="hello", max_output_tokens=1,
    )
    with pytest.raises(NativeFairStreamDenied, match="session mismatch"):
        registry.stage(other)


def test_cpu_only_not_a_gpu_qualification():
    runtime, registry, backend = setup()
    p = replace(permit(), device_qualified=True)
    with pytest.raises(NativeFairStreamDenied, match="CPU-only"):
        backend.generate(p, state(p))
    assert registry.status()["staged"] == 1


def test_invalid_native_result_never_marks_pressure_guard_success(monkeypatch):
    """A native return value is not an attested execution receipt."""
    from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
    from skeleton.ai.model_runtime.fair_stream_queue import MeasuredStreamBudget
    from skeleton.ai.model_runtime.native_token_pressure import NativeTokenPressureGuard

    def sample(self, *, token_budget, storage_path):
        return MeasuredStreamBudget(
            available_ram_bytes=4096, reserved_ram_bytes=0,
            token_budget=token_budget, stream_slots=1,
            pressure_ppm=0, thermal_hold=False, measurement="os_probe",
        ), {
            "measurement": "os_probe", "gpu_device_qualified": False,
            "physical_memory_reserved": False,
            "auxiliary_telemetry_incomplete": True,
        }

    def invalid_native(self, sequence, config, *, interrupt=None):
        assert interrupt is not None
        interrupt()
        return object()

    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", sample)
    monkeypatch.setattr(NativeLLMRuntime, "generate_sequence", invalid_native)
    runtime, registry, _ = setup()
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    backend = NativeFairStreamBackend(runtime, registry, pressure_guard=guard)
    with pytest.raises(NativeFairStreamDenied, match="untrusted native"):
        backend.generate(permit(), state())
    assert guard.status().stopped
    assert guard.status().samples == 1
    assert registry.status()["consumed_or_revoked"] == 1


def test_postflight_pressure_hold_fences_attested_native_output(monkeypatch):
    """The last OS sample runs after native result validation, before return."""
    from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
    from skeleton.ai.model_runtime.fair_stream_queue import MeasuredStreamBudget
    from skeleton.ai.model_runtime.native_token_pressure import NativeTokenPressureGuard
    from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig

    runtime, registry, _ = setup()
    baseline = runtime.generate("hello", GenerationConfig(max_new_tokens=2))
    readings = iter((1, 0))

    def sample(self, *, token_budget, storage_path):
        slots = next(readings)
        return MeasuredStreamBudget(
            available_ram_bytes=4096, reserved_ram_bytes=0,
            token_budget=token_budget, stream_slots=slots,
            pressure_ppm=0, thermal_hold=False, measurement="os_probe",
        ), {
            "measurement": "os_probe", "gpu_device_qualified": False,
            "physical_memory_reserved": False,
            "auxiliary_telemetry_incomplete": True,
        }

    def native_once(self, sequence, config, *, interrupt=None):
        interrupt()
        return baseline

    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", sample)
    monkeypatch.setattr(NativeLLMRuntime, "generate_sequence", native_once)
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    backend = NativeFairStreamBackend(runtime, registry, pressure_guard=guard)
    with pytest.raises(NativeFairStreamDenied, match="no retry"):
        backend.generate(permit(), state())
    assert guard.status().stopped
    assert guard.status().samples == 2
    assert registry.status()["consumed_or_revoked"] == 1


def test_forged_native_output_digest_never_reaches_result_vault(monkeypatch):
    """Result bytes must match the signed native output trajectory."""
    from skeleton.ai.model_runtime.fair_stream_live_budget import LiveStreamBudgetSampler
    from skeleton.ai.model_runtime.fair_stream_queue import MeasuredStreamBudget
    from skeleton.ai.model_runtime.native_token_pressure import NativeTokenPressureGuard
    from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig

    runtime, registry, _ = setup()
    original = runtime.generate("hello", GenerationConfig(max_new_tokens=2))
    forged = replace(original, text=original.text + "forged")

    def sample(self, *, token_budget, storage_path):
        return MeasuredStreamBudget(
            available_ram_bytes=4096, reserved_ram_bytes=0,
            token_budget=token_budget, stream_slots=1,
            pressure_ppm=0, thermal_hold=False, measurement="os_probe",
        ), {
            "measurement": "os_probe", "gpu_device_qualified": False,
            "physical_memory_reserved": False,
            "auxiliary_telemetry_incomplete": True,
        }

    def tampered(self, sequence, config, *, interrupt=None):
        interrupt()
        return forged

    monkeypatch.setattr(LiveStreamBudgetSampler, "sample", sample)
    monkeypatch.setattr(NativeLLMRuntime, "generate_sequence", tampered)
    guard = NativeTokenPressureGuard(LiveStreamBudgetSampler(), storage_path=".")
    backend = NativeFairStreamBackend(runtime, registry, pressure_guard=guard)
    with pytest.raises(NativeFairStreamDenied, match="attestation mismatch"):
        backend.generate(permit(), state())
    assert guard.status().stopped
    assert registry.status()["consumed_or_revoked"] == 1


def test_pending_lease_cannot_change_tenant_after_durable_admission():
    _, registry, backend = setup()
    forged = state()
    forged["checkpoint"]["pending"][0]["tenant_id"] = "bob"
    with pytest.raises(NativeFairStreamDenied, match="tenant mismatch"):
        backend.generate(permit(), forged)
    assert registry.status()["staged"] == 1


def test_bool_pending_token_count_cannot_alias_integer_permit():
    _, registry, backend = setup()
    p = permit(tokens=1)
    forged = state(p)
    forged["checkpoint"]["pending"][0]["tokens"] = True
    with pytest.raises(NativeFairStreamDenied, match="lease identity mismatch"):
        backend.generate(p, forged)
    assert registry.status()["staged"] == 1
