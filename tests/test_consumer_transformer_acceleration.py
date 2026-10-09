"""Parity and consumer-device regressions for Skeleton's owned transformer.

These tests intentionally use tiny weights. They validate arithmetic, kernel
dispatch and cache semantics, not end-user model quality or speed claims.
"""
from __future__ import annotations

import pytest

from skeleton.cortex import device as device_harness
from skeleton.cortex.transformer import KVCache, TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import DevicePolicy, RuntimeContractError


def _model(*, norm="ln", ffn_kind="gelu", tied=False):
    model = TinyTransformer(
        vocab=("alpha", "beta", "gamma"),
        dim=8, ctx=6, n_heads=2, n_layers=2, d_ff=12,
        seed=83, norm=norm, ffn_kind=ffn_kind,
    )
    if tied:
        model.tie()
    return model


@pytest.mark.parametrize(
    "norm,ffn_kind,tied",
    [
        ("ln", "gelu", False),
        ("rms", "swiglu", False),
        ("rms", "swiglu", True),
    ],
)
def test_torch_fused_attention_matches_native_reference(norm, ffn_kind, tied):
    torch = pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = _model(norm=norm, ffn_kind=ffn_kind, tied=tied)
    ids = (1, 2, 3, 1)
    native = model._logits(ids)
    accel = TorchAccel(model, device="cpu").pin()
    optimized = accel.logits(ids)
    assert optimized == pytest.approx(native, rel=2e-5, abs=2e-5)

    if hasattr(torch.nn.functional, "scaled_dot_product_attention"):
        # Ensure correctness comes from the actual optimized dispatch path.
        assert accel.resident
    if tied:
        assert accel._Wout is accel._E
        assert len({id(x) for x in accel._params()}) == len(tuple(accel._params()))


def test_fused_sdpa_is_reached_when_available(monkeypatch):
    torch = pytest.importorskip("torch")
    if not hasattr(torch.nn.functional, "scaled_dot_product_attention"):
        pytest.skip("SDPA is not available on this torch version")
    from skeleton.cortex.torch_lm import TorchAccel

    model = _model()
    accel = TorchAccel(model, device="cpu").pin()
    sdpa = torch.nn.functional.scaled_dot_product_attention
    calls = []

    def counted(*args, **kwargs):
        calls.append(kwargs)
        return sdpa(*args, **kwargs)

    monkeypatch.setattr(torch.nn.functional, "scaled_dot_product_attention", counted)
    assert len(accel.logits((1, 2, 3))) == model.V
    assert len(calls) == model.n_layers
    assert all(call["is_causal"] is True and call["dropout_p"] == 0 for call in calls)


def test_swiglu_up_projection_receives_updates_and_syncs():
    pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = _model(norm="rms", ffn_kind="swiglu")
    before = [row[:] for row in model.layers[0].Wu]
    accel = TorchAccel(model, device="cpu").pin()
    loss = accel.sgd((1, 2, 3), target=2, lr=0.5)
    assert loss > 0
    accel.sync()
    assert any(a != b for row0, row1 in zip(before, model.layers[0].Wu)
               for a, b in zip(row0, row1))
    assert accel.logits((1, 2)) == pytest.approx(model._logits((1, 2)), abs=2e-5)


def test_window_relative_rotary_cache_parity_on_extension_and_shift():
    model = _model(norm="rms", ffn_kind="swiglu")
    cache = KVCache(model.n_layers, model.ctx)
    for ids in [
        (1, 2, 3),
        (1, 2, 3, 1),
        (1, 2, 3, 1, 2),
        (1, 2, 3, 1, 2, 3),
        (2, 3, 1, 2, 3, 1),  # window rolls; cache must reset and re-prime
    ]:
        fast = model._logits_window(ids, cache)
        full = model._logits_window(ids, None)
        assert fast == pytest.approx(full, rel=1e-9, abs=1e-9)
        assert cache.tokens == list(ids)


def test_resolve_honors_mps_and_explicit_fallback(monkeypatch):
    def hardware(*, mps=False, cuda=False):
        return dict(
            name="cuda" if cuda else ("mps" if mps else "cpu"),
            backend="torch", torch=True, cuda=cuda, mps=mps,
            gpu=None, count=1 if cuda else 0, capability="test", memory=0,
        )

    monkeypatch.setattr(device_harness, "probe", lambda: hardware(mps=True))
    assert device_harness.resolve("auto")["actual"] == "mps"
    assert device_harness.resolve("mps")["actual"] == "mps"
    monkeypatch.setattr(device_harness, "probe", lambda: hardware())
    assert device_harness.resolve("mps")["degraded"] is True
    assert device_harness.resolve("auto")["actual"] == "cpu"
    monkeypatch.setattr(device_harness, "probe", lambda: hardware(cuda=True))
    assert device_harness.resolve("auto")["actual"] == "cuda"


def test_re_admit_mutated_native_model_only_on_explicit_refresh():
    model = _model()
    runtime = NativeLLMRuntime(model)
    original = runtime.model_digest
    model.bout[1] += 0.25
    with pytest.raises(RuntimeContractError, match="mutated"):
        runtime.assert_model_unchanged()
    digest = runtime.refresh_model_identity()
    assert digest != original and digest == runtime.model_digest
    runtime.assert_model_unchanged()


def test_mps_policy_no_silent_downgrade(monkeypatch):
    model = _model()
    def degraded_to(model_device):
        model.device = "cpu"
        model.resident = False
        return model

    monkeypatch.setattr(model, "to", degraded_to)
    with pytest.raises(RuntimeContractError, match="fallback"):
        NativeLLMRuntime(model, device_policy=DevicePolicy(requested="mps", allow_fallback=False))


def test_mps_snapshot_is_portable_and_not_falsely_resident():
    model = _model()
    snapshot = model.snapshot()
    snapshot["device"] = "mps"
    snapshot["resident"] = True
    restored = TinyTransformer.from_snapshot(snapshot)
    assert restored.device == "cpu"
    assert restored.requested == "mps"
    assert restored.resident is False
    assert restored._accel is None
