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
