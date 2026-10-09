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


@pytest.mark.parametrize("layers", [1, 2])
def test_rotary_only_sliding_cache_is_reference_equivalent(layers):
    model = TinyTransformer(
        vocab=("alpha", "beta", "gamma"), dim=8, ctx=4,
        seed=101, n_heads=2, n_layers=layers, d_ff=12,
        position_mode="rope", norm="rms", ffn_kind="swiglu",
    )
    cache = KVCache(layers, model.ctx)
    windows = [(1, 2), (1, 2, 3), (1, 2, 3, 1),
               (2, 3, 1, 2), (3, 1, 2, 3), (1, 2, 3, 1)]
    for window in windows:
        assert model._logits_window(window, cache) == pytest.approx(
            model._logits_window(window, None), abs=1e-8, rel=1e-8
        )
        assert cache.tokens == list(window)
    # Single-layer RoPE-only K/V are history-independent: eviction preserves
    # cache positions. Deeper layers need a re-prime for reference parity.
    assert cache.next_position == (7 if layers == 1 else 4)
    snapshot = model.snapshot()
    assert snapshot["position_mode"] == "rope"
    restored = TinyTransformer.from_snapshot(snapshot)
    assert restored.position_mode == "rope"
    assert restored._logits((1, 2, 3)) == pytest.approx(model._logits((1, 2, 3)))
    assert NativeLLMRuntime(model).architecture.positional == "rope-only"


def test_rotary_only_training_does_not_update_unused_absolute_positions():
    model = TinyTransformer(vocab=("x", "y"), dim=8, ctx=4, n_heads=2,
                            seed=27, position_mode="rope")
    before = [row[:] for row in model.P]
    assert model._sgd([1, 2], target=1, lr=0.01) > 0
    assert model.P == before


def test_rotary_only_torch_and_reference_parity():
    pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = TinyTransformer(
        vocab=("alpha", "beta", "gamma"), dim=8, ctx=4,
        n_heads=2, n_layers=2, d_ff=12, seed=101,
        position_mode="rope", norm="rms", ffn_kind="swiglu",
    )
    cpu_logits = model._logits((1, 2, 3))
    accel = TorchAccel(model, device="cpu").pin()
    assert accel.logits((1, 2, 3)) == pytest.approx(
        cpu_logits, rel=2e-5, abs=2e-5
    )


@pytest.mark.parametrize("norm,ffn,position_mode,layers", [
    ("ln", "gelu", "learned_rope", 1),
    ("ln", "gelu", "learned_rope", 2),
    ("rms", "swiglu", "rope", 1),
    ("rms", "swiglu", "rope", 2),
])
def test_torch_resident_incremental_decode_parity(norm, ffn, position_mode, layers):
    pytest.importorskip("torch")
    model = TinyTransformer(
        vocab=("alpha", "beta", "gamma"),
        dim=8, ctx=4, seed=127, n_heads=2, n_layers=layers,
        d_ff=12, norm=norm, ffn_kind=ffn, position_mode=position_mode,
    )
    reference = TinyTransformer.from_snapshot(model.snapshot())
    model.to("torch")
    assert model.resident and model._accel is not None
    cache = KVCache(model.n_layers, model.ctx)
    windows = [
        (1,), (1, 2), (1, 2, 3), (1, 2, 3, 1),
        (2, 3, 1, 2), (3, 1, 2, 3), (1, 2, 3, 1),
        (1, 3, 2, 1),  # unrelated window forces fresh prefill
    ]
    for window in windows:
        cached = model._logits_window(window, cache)
        full = reference._logits_window(window)
        assert cached == pytest.approx(full, rel=2e-5, abs=2e-5)
        assert model._accel is not None and model.resident
    assert model._accel._cached_ids == list(windows[-1])


def test_torch_decode_cache_is_invalidated_after_training():
    pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = _model(norm="rms", ffn_kind="swiglu")
    accel = TorchAccel(model, device="cpu").pin()
    _ = accel.logits_window((1, 2, 3))
    assert accel._cached_ids == [1, 2, 3]
    accel.sgd((1, 2), target=3, lr=0.05)
    assert accel._cached_ids == []
    assert accel.logits_window((1, 2, 3)) == pytest.approx(
        accel.logits((1, 2, 3)), rel=2e-5, abs=2e-5
    )


def test_mixture_of_depths_model_never_executes_unimplemented_torch_graph():
    pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = TinyTransformer(
        vocab=("alpha", "beta"), dim=8, ctx=4,
        n_heads=2, n_layers=1, seed=7, use_mod=True,
    )
    with pytest.raises(ValueError, match="Mixture of Depths"):
        TorchAccel(model).pin()
    model.to("torch")
    assert model.device == "cpu" and not model.resident
    assert model._accel is None


def test_native_serving_accounts_for_resident_torch_kv_cache():
    pytest.importorskip("torch")
    from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig

    model = _model(norm="rms", ffn_kind="swiglu")
    runtime = NativeLLMRuntime(
        model, device_policy=DevicePolicy(requested="torch", allow_fallback=False)
    )
    seq = runtime.encode("alpha beta gamma")
    result = runtime.infer_sequence(seq, use_cache=True)
    assert result.cache_tokens == len(seq.token_ids)
    assert model._accel is not None
    assert model._accel.cached_tokens == seq.token_ids
    generation = runtime.generate(
        "alpha beta",
        GenerationConfig(max_new_tokens=2, temperature=0.0, use_cache=True),
    )
    assert generation.usage.kv_peak_bytes >= runtime.estimate_kv_bytes(1)
    assert any(event.cache_tokens > 0 for event in generation.events if event.kind == "token")


def test_torch_prefill_is_batched_before_incremental_decode(monkeypatch):
    pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = _model(norm="rms", ffn_kind="swiglu")
    accel = TorchAccel(model, device="cpu").pin()
    original = accel._cached_step
    calls = []

    def traced(token_id):
        calls.append(token_id)
        return original(token_id)

    monkeypatch.setattr(accel, "_cached_step", traced)
    expected = accel.logits((1, 2, 3))
    assert accel.logits_window((1, 2, 3)) == pytest.approx(expected, abs=2e-5)
    assert calls == []  # fused prefill, no per-token launch loop
    assert accel.cached_tokens == (1, 2, 3)
    assert len(accel._cached_keys) == model.n_layers
    assert all(tensor.shape[-2] == 3 for tensor in accel._cached_keys)
    assert accel.logits_window((1, 2, 3, 1)) == pytest.approx(
        accel.logits((1, 2, 3, 1)), abs=2e-5
    )
    assert calls == [1]  # one resident decoder step


def test_float32_accelerator_binding_never_mutates_canonical_weight_identity():
    pytest.importorskip("torch")
    from skeleton.ai.model_runtime.runtime_checkpoint import (
        portable_model_snapshot, snapshot_digest,
    )

    model = _model(norm="rms", ffn_kind="swiglu", tied=True)
    before = snapshot_digest(portable_model_snapshot(model))
    runtime = NativeLLMRuntime(
        model, device_policy=DevicePolicy(requested="torch", allow_fallback=False)
    )
    assert runtime.model_digest == before
    assert runtime.assert_model_unchanged() is None
    assert snapshot_digest(portable_model_snapshot(model)) == before
    _ = runtime.infer_text("alpha beta")
    assert snapshot_digest(portable_model_snapshot(model)) == before
    assert model._accel is not None and not model._accel._weights_modified


def test_torch_training_sync_marks_real_weight_mutations():
    pytest.importorskip("torch")
    from skeleton.ai.model_runtime.runtime_checkpoint import (
        portable_model_snapshot, snapshot_digest,
    )

    model = _model(norm="rms", ffn_kind="swiglu")
    model.to("torch")
    accel = model._accel
    assert accel is not None
    before = snapshot_digest(portable_model_snapshot(model))
    accel.sgd((1, 2, 3), target=2, lr=0.04)
    assert accel._weights_modified
    after = snapshot_digest(portable_model_snapshot(model))
    assert after != before
    assert accel._weights_modified is False
    assert snapshot_digest(portable_model_snapshot(model)) == after


def test_accelerator_sync_failure_never_silently_publishes_stale_weights(monkeypatch):
    pytest.importorskip("torch")
    model = _model()
    model.to("torch")
    accel = model._accel
    assert accel is not None

    def fail_sync():
        raise OSError("device transfer failed")

    monkeypatch.setattr(accel, "sync", fail_sync)
    with pytest.raises(RuntimeError, match="refusing stale model weights"):
        model.snapshot()
    with pytest.raises(RuntimeError, match="refusing stale model weights"):
        model.to("cpu")
    assert model._accel is accel  # failed migration did not discard authority


def test_hidden_sequence_avoids_duplicate_gpu_forward(monkeypatch):
    pytest.importorskip("torch")
    model = _model()
    model.to("torch")
    accel = model._accel
    assert accel is not None
    monkeypatch.setattr(
        accel, "hidden",
        lambda ids: (_ for _ in ()).throw(AssertionError("redundant GPU pass")),
    )
    output = model.hidden_seq("alpha beta")
    assert len(output) == 2 and all(len(row) == model.dim for row in output)


def test_resident_kv_decode_reuses_buffer_without_per_token_concat(monkeypatch):
    torch = pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = TinyTransformer(
        vocab=("alpha", "beta", "gamma"), dim=8, ctx=40,
        n_heads=2, n_layers=2, d_ff=12, seed=71,
        norm="rms", ffn_kind="swiglu",
    )
    reference = TinyTransformer.from_snapshot(model.snapshot())
    accel = TorchAccel(model, device="cpu").pin()
    assert accel.logits_window((1, 2)) == pytest.approx(
        reference._logits((1, 2)), abs=2e-5
    )
    first_pointer = accel._key_buffers[0].data_ptr()
    first_capacity = accel._key_buffers[0].shape[-2]
    assert 2 <= first_capacity < model.ctx
    for length in range(3, first_capacity + 1):
        ids = tuple((i % 3) + 1 for i in range(length))
        # A prefix must match the existing cache for true decode progression.
        if length == 3:
            ids = (1, 2, 3)
        assert accel.logits_window(ids) == pytest.approx(
            reference._logits(ids), abs=2e-5
        )
        assert accel._key_buffers[0].data_ptr() == first_pointer
        assert accel._key_buffers[0].shape[-2] == first_capacity
        assert accel.cached_tokens == ids
    next_ids = tuple((i % 3) + 1 for i in range(first_capacity + 1))
    assert accel.logits_window(next_ids) == pytest.approx(
        reference._logits(next_ids), abs=2e-5
    )
    assert accel._key_buffers[0].shape[-2] > first_capacity
    assert accel._key_buffers[0].shape[-2] <= model.ctx
    assert all(buf.shape[-2] <= model.ctx for buf in accel._key_buffers)


def test_rotary_single_layer_eviction_reuses_gpu_buffers():
    pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = TinyTransformer(
        vocab=("alpha", "beta"), dim=8, ctx=4,
        seed=37, n_heads=2, n_layers=1, d_ff=8,
        norm="rms", ffn_kind="swiglu", position_mode="rope",
    )
    accel = TorchAccel(model, device="cpu").pin()
    windows = ((1, 2, 1, 2), (2, 1, 2, 1), (1, 2, 1, 2))
    pointer = None
    for window in windows:
        result = accel.logits_window(window)
        assert result == pytest.approx(model._logits(window), rel=2e-5, abs=2e-5)
        if pointer is None:
            pointer = accel._key_buffers[0].data_ptr()
        assert accel._key_buffers[0].data_ptr() == pointer
        assert accel.cached_tokens == window
    assert accel._cached_next_position == 6


def test_runtime_identity_refresh_repins_updated_consumer_accelerator():
    pytest.importorskip("torch")
    model = _model(norm="rms", ffn_kind="swiglu")
    runtime = NativeLLMRuntime(
        model, device_policy=DevicePolicy(requested="torch", allow_fallback=False)
    )
    before = runtime.infer_text("alpha beta")
    accel = model._accel
    assert accel is not None and accel.cached_tokens
    model.bout[2] += 3.25
    with pytest.raises(RuntimeContractError, match="mutated"):
        runtime.assert_model_unchanged()
    new_digest = runtime.refresh_model_identity()
    assert new_digest != before.model_digest
    assert model._accel is accel
    assert accel.cached_tokens == ()  # stale resident keys are invalidated
    after = runtime.infer_text("alpha beta")
    assert after.model_digest == new_digest
    assert after.logits != before.logits
    reference = TinyTransformer.from_snapshot(model.snapshot())
    assert after.logits == pytest.approx(
        reference._logits(runtime.encode("alpha beta").token_ids),
        rel=2e-5, abs=2e-5,
    )


def test_runtime_identity_refresh_rejects_partial_accelerator_rebind(monkeypatch):
    pytest.importorskip("torch")
    model = _model()
    runtime = NativeLLMRuntime(
        model, device_policy=DevicePolicy(requested="torch", allow_fallback=False)
    )
    prior_digest = runtime.model_digest
    model.bout[1] += 0.2
    accel = model._accel
    assert accel is not None

    def partial_failure():
        raise RuntimeError("unavailable memory on device")

    monkeypatch.setattr(accel, "pin", partial_failure)
    with pytest.raises(RuntimeContractError, match="accelerator rebind failed"):
        runtime.refresh_model_identity()
    assert runtime.model_digest == prior_digest
    assert model._accel is None and not model.resident
    with pytest.raises(RuntimeContractError, match="mutated"):
        runtime.assert_model_unchanged()


def test_concurrent_transformer_inference_never_cross_contaminates_kv_history():
    pytest.importorskip("torch")
    from concurrent.futures import ThreadPoolExecutor
    from skeleton.cortex.torch_lm import TorchAccel

    model = TinyTransformer(
        vocab=("a", "b", "c"), dim=8, ctx=6, seed=199,
        n_heads=2, n_layers=2, d_ff=12, norm="rms",
        ffn_kind="swiglu",
    )
    accel = TorchAccel(model, device="cpu").pin()
    windows = [
        (1, 2, 3), (3, 2, 1), (1, 1, 1),
        (1, 2, 3, 1), (3, 1, 2, 3), (2, 3, 1, 2),
        (2, 2, 3, 1), (1, 3, 2, 1),
    ] * 3
    expected = [model._logits(window) for window in windows]
    with ThreadPoolExecutor(max_workers=4) as pool:
        actual = list(pool.map(accel.logits_window, windows))
    for result, reference in zip(actual, expected):
        assert result == pytest.approx(reference, abs=2e-5, rel=2e-5)


def test_training_serializes_against_resident_kv_decode(monkeypatch):
    pytest.importorskip("torch")
    from threading import Event, Thread
    from skeleton.cortex.torch_lm import TorchAccel

    model = _model()
    accel = TorchAccel(model, device="cpu").pin()
    accel.logits_window((1, 2))
    entered_step, release_step, training_done = Event(), Event(), Event()
    errors = []
    original_step = accel._cached_step

    def blocked_step(token):
        entered_step.set()
        if not release_step.wait(timeout=5):
            raise TimeoutError("test could not release blocked decoder")
        return original_step(token)

    monkeypatch.setattr(accel, "_cached_step", blocked_step)

    def decode():
        try:
            accel.logits_window((1, 2, 3))
        except Exception as exc:
            errors.append(exc)

    def train():
        try:
            accel.sgd((1, 2), target=3, lr=0.01)
        except Exception as exc:
            errors.append(exc)
        finally:
            training_done.set()

    first = Thread(target=decode)
    second = Thread(target=train)
    try:
        first.start()
        assert entered_step.wait(timeout=5)
        second.start()
        # Training must not mutate weights while the decoder is executing.
        assert not training_done.wait(timeout=0.05)
    finally:
        release_step.set()
        first.join(timeout=5)
        if second.ident is not None:
            second.join(timeout=5)
    assert not first.is_alive()
    assert not second.is_alive()
    assert not errors
    assert training_done.is_set()
    assert accel.cached_tokens == ()  # SGD invalidates the prior KV bank
