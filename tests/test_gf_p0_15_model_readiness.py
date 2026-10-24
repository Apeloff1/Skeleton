"""GF-P0-15: registry readiness/rights/VRAM and no-bypass gate tests."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass

import pytest

from skeleton.provider_runtime import (
    GatedProviderAdapter,
    ModelReadinessGate,
    ProviderAdapter,
    ProviderPolicyError,
    ProviderRequest,
)
from skeleton.shells.ai import model_registry as mr
from skeleton.ai.shell import model_registry as mirror


@dataclass(frozen=True)
class _Att:
    provider_id: str = "local"
    model_id: str = "m1"
    digest: str = "d1"
    model_version: str = "1"
    adapter_version: str = "1"


READY = mr.ModelCapability(
    weights_ready=True, weights_digest="sha256:x", license_id="apache-2.0",
    allowed_uses=frozenset({"model-inference"}), vram_required_mb=4000,
)


def _registry(cap=READY):
    reg = mr.AIModelRegistry()
    item = reg.register(_Att())
    if cap is not None:
        reg.set_capability(item.registry_id, cap)
    return reg


def test_ready_model_passes():
    assert _registry().require_ready("local:m1", use="model-inference", available_vram_mb=8000).revision == 1


@pytest.mark.parametrize(
    "cap,use,vram,msg",
    [
        (None, "model-inference", 8000, "not declared"),
        (mr.ModelCapability(), "model-inference", 8000, "weights"),
        (mr.ModelCapability(weights_ready=True, weights_digest="x"), "model-inference", 8000, "rights"),
        (READY, "training", 8000, "permit"),
        (READY, "model-inference", None, "unknown"),
        (READY, "model-inference", 100, "insufficient"),
    ],
)
def test_deny_by_default(cap, use, vram, msg):
    with pytest.raises(mr.ModelNotReadyError, match=msg):
        _registry(cap).require_ready("local:m1", use=use, available_vram_mb=vram)


def test_unregistered_and_inactive_denied():
    reg = _registry()
    with pytest.raises(mr.ModelNotReadyError):
        reg.require_ready("x:y", use="model-inference", available_vram_mb=1)
    reg.deactivate("local:m1")
    with pytest.raises(mr.ModelNotReadyError, match="active"):
        reg.require_ready("local:m1", use="model-inference", available_vram_mb=8000)


def test_set_capability_requires_registration_and_report():
    reg = _registry()
    with pytest.raises(KeyError):
        reg.set_capability("nope:x", READY)
    assert reg.capability_report()["local:m1"]["license_id"] == "apache-2.0"


def test_vram_discovery(monkeypatch):
    monkeypatch.delenv("SKELETON_VRAM_MB", raising=False)
    assert mr.discover_vram_mb(runner=lambda: "1000\n24000\n") == 24000
    assert mr.discover_vram_mb(runner=lambda: "garbage") is None
    monkeypatch.setenv("SKELETON_VRAM_MB", "512")
    assert mr.discover_vram_mb() == 512


def test_mirror_in_sync():
    assert inspect.getsource(mr) == inspect.getsource(mirror)


class _Inner(ProviderAdapter):
    provider_id = "local"
    model = "m1"
    calls = 0

    @property
    def available(self):
        return True

    async def generate(self, request):
        type(self).calls += 1
        return "ok"


def _req():
    return ProviderRequest(instructions="i", prompt="p")


def test_gate_allows_ready_model():
    gated = GatedProviderAdapter(_Inner(), ModelReadinessGate(_registry(), vram_probe=lambda: 8000))
    assert asyncio.run(gated.generate(_req())) == "ok"


def test_no_bypass_generate_and_stream_denied():
    _Inner.calls = 0
    gated = GatedProviderAdapter(_Inner(), ModelReadinessGate(_registry(), vram_probe=lambda: 10))
    with pytest.raises(ProviderPolicyError):
        asyncio.run(gated.generate(_req()))

    async def drain():
        async for _ in gated.stream(_req()):
            pass

    with pytest.raises(ProviderPolicyError):
        asyncio.run(drain())
    assert _Inner.calls == 0


def test_no_bypass_every_invocation_method_is_gated():
    invocation = {
        name for name, fn in inspect.getmembers(ProviderAdapter)
        if not name.startswith("_") and (inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn))
    }
    assert invocation
    for name in invocation:
        assert name in GatedProviderAdapter.__dict__, name
        src = inspect.getsource(GatedProviderAdapter.__dict__[name])
        assert "self._check(" in src, name


def test_no_bypass_inner_not_exposed():
    gated = GatedProviderAdapter(_Inner(), ModelReadinessGate(_registry(), vram_probe=lambda: 10))
    assert not hasattr(gated, "inner")
    assert not any(isinstance(getattr(gated, a, None), _Inner) for a in dir(gated) if not a.startswith("_Gated"))
