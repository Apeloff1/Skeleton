"""Source-preserving GF-P0-15/18 native model gates with revision/VRAM custody.

Tests execute only fake local providers; no network or model weights are loaded.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from skeleton.provider_runtime import (
    ProviderAdapter, ProviderInvocationError, ProviderPolicyError,
    ProviderRequest, ProviderResponse, ProviderImageRequest,
)
from skeleton.provider_model_readiness import (
    LocalModelReadinessGate, LocalReadyProviderAdapter,
    EnvelopedLocalReadyAdapter, ResourceEnvelope,
)
from skeleton.shells.ai.model_registry import (
    AIModelRegistry, ModelCapability, ModelNotReadyError, ModelRegistryConflict,
)
from skeleton.ai.shell import model_registry as mirror


@dataclass(frozen=True)
class _Att:
    provider_id: str = "local"
    model_id: str = "m1"
    digest: str = "test-attestation-1"
    model_version: str = "1"
    adapter_version: str = "1"


READY = ModelCapability(
    weights_ready=True, weights_digest="sha256:weights-snapshot",
    license_id="apache-2.0", allowed_uses=frozenset({"model-inference"}),
    vram_required_mb=4000,
)


def registry(cap=READY):
    reg = AIModelRegistry()
    item = reg.register(_Att())
    if cap is not None:
        reg.set_capability(item.registry_id, cap, expected_revision=item.revision)
    return reg


class _Fake(ProviderAdapter):
    provider_id, model = "local", "m1"

    def __init__(self, *, delay=0.0, payload="locally-generated") -> None:
        self.calls = 0
        self.delay = delay
        self.payload = payload

    @property
    def available(self):
        return True

    async def generate(self, request):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return ProviderResponse(text=self.payload, provider="local", model="m1")


def test_unknown_and_unready_models_fail_closed():
    reg = registry(None)
    with pytest.raises(ModelNotReadyError, match="not declared"):
        reg.require_ready("local:m1", use="model-inference", available_vram_mb=9999)
    with pytest.raises(ModelNotReadyError, match="not registered"):
        reg.require_ready("local:missing", use="model-inference", available_vram_mb=9999)
    with pytest.raises(ModelNotReadyError, match="weights"):
        registry(ModelCapability()).require_ready("local:m1", use="model-inference")


@pytest.mark.parametrize("use,capacity,match", [
    ("training", 4000, "rights"),
    ("model-inference", None, "unknown"),
    ("model-inference", 100, "insufficient"),
    ("model-inference", -1, "unknown"),
])
def test_policy_and_capacity_denials(use,capacity,match):
    with pytest.raises(ModelNotReadyError, match=match):
        registry().require_ready("local:m1", use=use, available_vram_mb=capacity)


def test_revision_changes_revoke_grants():
    reg = registry()
    prior = reg.current("local:m1")
    assert reg.require_ready("local:m1", use="model-inference", available_vram_mb=5000) == prior
    newer = reg.register(_Att(digest="test-attestation-2"), expected_revision=prior.revision)
    assert newer.revision == prior.revision + 1
    assert reg.capability("local:m1") is None
    with pytest.raises(ModelNotReadyError):
        reg.require_ready("local:m1", use="model-inference", available_vram_mb=5000)
    with pytest.raises(ModelRegistryConflict):
        reg.set_capability("local:m1", READY, expected_revision=prior.revision)
    reg.set_capability("local:m1", READY, expected_revision=newer.revision)
    reg.deactivate("local:m1")
    assert reg.capability("local:m1") is None
    with pytest.raises(ModelNotReadyError):
        reg.set_capability("local:m1", READY)
    reg.activate("local:m1")
    with pytest.raises(ModelNotReadyError, match="not declared"):
        reg.require_ready("local:m1", use="model-inference", available_vram_mb=5000)


def test_cpu_local_model_requires_no_gpu_but_still_has_rights():
    cap = ModelCapability(
        weights_ready=True, weights_digest="offline-bytes", license_id="MIT",
        allowed_uses=frozenset({"model-inference"}), vram_required_mb=0,
    )
    assert registry(cap).require_ready("local:m1", use="model-inference") is not None
    assert registry(cap).capability_report()["local:m1"]["weights_ready"] is True


def test_model_registry_mirror_keeps_identity_and_policy():
    assert mirror.ModelCapability is not None
    assert tuple(mirror.ModelCapability.__dataclass_fields__) == tuple(ModelCapability.__dataclass_fields__)
    assert mirror.ModelNotReadyError is not None


def test_nonlocal_and_spoofed_model_never_invoked():
    good = registry()
    gate = LocalModelReadinessGate(good, available_vram_mb=lambda: 8000)
    fake = _Fake()
    wrapped = LocalReadyProviderAdapter(fake, gate)
    with pytest.raises(ProviderPolicyError, match="does not match"):
        asyncio.run(wrapped.generate(ProviderRequest(instructions="a", prompt="b", model="other")))
    assert fake.calls == 0
    with pytest.raises(ProviderPolicyError, match="local native"):
        gate.check("openai", "m1")
    with pytest.raises(ProviderPolicyError, match="local native"):
        LocalReadyProviderAdapter(type("Remote", (_Fake,), {"provider_id": "openai"})(), gate)


def test_gate_invokes_only_admitted_exact_model():
    gate = LocalModelReadinessGate(registry(), available_vram_mb=lambda: 5000)
    fake = _Fake()
    adapter = LocalReadyProviderAdapter(fake, gate)
    assert adapter.available
    out = asyncio.run(adapter.generate(ProviderRequest(instructions="local", prompt="work", model="m1")))
    assert out.text == "locally-generated"
    assert fake.calls == 1
    assert adapter.status()["local_ready_gate"] is True


def test_zero_implicit_vram_claim_and_image_denial():
    fake = _Fake()
    adapter = LocalReadyProviderAdapter(fake, LocalModelReadinessGate(registry()))
    assert adapter.available is False
    with pytest.raises(ProviderPolicyError):
        asyncio.run(adapter.generate(ProviderRequest(instructions="a", prompt="b")))
    assert fake.calls == 0
    image_adapter = LocalReadyProviderAdapter(
        fake, LocalModelReadinessGate(registry(), available_vram_mb=lambda: 9999)
    )
    with pytest.raises(ProviderPolicyError, match="rights"):
        asyncio.run(image_adapter.generate_image(ProviderImageRequest(prompt="x")))


def test_resource_envelope_rejects_invalid_bounds():
    for params in [
        {"max_seconds": 0}, {"max_seconds": float("nan")},
        {"max_seconds": 3601}, {"max_buffer_bytes": 0},
        {"max_buffer_bytes": 4 * 1024**3 + 1},
        {"max_buffer_bytes": True},
    ]:
        with pytest.raises(ValueError):
            ResourceEnvelope(**params)


def test_deadline_and_response_bytes_enforced():
    gate = LocalModelReadinessGate(registry(), available_vram_mb=lambda: 5000)
    slow = _Fake(delay=0.1)
    adapter = EnvelopedLocalReadyAdapter(slow, gate, ResourceEnvelope(max_seconds=0.01))
    with pytest.raises(ProviderInvocationError, match="deadline"):
        asyncio.run(adapter.generate(ProviderRequest(instructions="i", prompt="p")))
    large = _Fake(payload="hello")
    adapter2 = EnvelopedLocalReadyAdapter(large, gate, ResourceEnvelope(max_buffer_bytes=3))
    with pytest.raises(ProviderInvocationError, match="byte budget"):
        asyncio.run(adapter2.generate(ProviderRequest(instructions="i", prompt="p")))


def test_stream_is_denied_before_ungated_generate():
    gate = LocalModelReadinessGate(registry(None), available_vram_mb=lambda: 9000)
    adapter = EnvelopedLocalReadyAdapter(_Fake(), gate, ResourceEnvelope())
    async def drain():
        async for _ in adapter.stream(ProviderRequest(instructions="i", prompt="p")):
            pass
    with pytest.raises(ProviderPolicyError):
        asyncio.run(drain())
