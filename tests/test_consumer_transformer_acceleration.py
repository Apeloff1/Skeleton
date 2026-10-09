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


def test_accelerated_logits_and_cache_receipt_are_from_one_state():
    pytest.importorskip("torch")
    from concurrent.futures import ThreadPoolExecutor
    from skeleton.cortex.torch_lm import TorchAccel

    model = TinyTransformer(
        vocab=("alpha", "beta", "gamma"), dim=8, ctx=6, seed=9,
        n_heads=2, n_layers=2, d_ff=12,
    )
    accel = TorchAccel(model, device="cpu").pin()
    inputs = [
        (1, 2, 3), (3, 1), (2, 1, 2, 3),
        (2, 3, 1, 2, 3), (1,), (1, 1, 1, 1),
    ] * 3

    def run(ids):
        return accel.logits_window_with_cache(ids)

    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(run, inputs))
    for ids, (logits, admitted_tokens) in zip(inputs, outputs):
        assert admitted_tokens == ids
        assert logits == pytest.approx(model._logits(ids), abs=2e-5)

    # The standalone compatibility path returns only logits, while resource
    # accounting must use the atomic (logits, occupancy) interface.
    model._accel = accel
    model.resident = True
    model.device = "cpu"
    from skeleton.cortex.transformer import KVCache
    cache = KVCache(model.n_layers, model.ctx)
    output = model._logits_window((1, 2, 3), cache)
    assert output == pytest.approx(model._logits((1, 2, 3)), abs=2e-5)
    assert cache.tokens == [1, 2, 3]


def test_partial_gpu_sgd_is_poisoned_not_silently_replayed_or_synced(monkeypatch):
    pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = _model()
    accel = TorchAccel(model, device="cpu").pin()
    real = accel._E

    class FailedLaterParameter:
        @property
        def grad(self):
            return real.grad

        def add_(self, grad, *, alpha):
            raise RuntimeError("injected failure after first parameter update")

    fake = FailedLaterParameter()
    monkeypatch.setattr(accel, "_params", lambda: iter((real, fake)))
    with pytest.raises(RuntimeError, match="injected failure"):
        accel.sgd((1, 2), target=1, lr=0.01)
    assert accel._training_failed and accel._weights_modified
    assert accel.cached_tokens == ()
    with pytest.raises(RuntimeError, match="partial training update"):
        accel.logits_window((1, 2, 3))
    with pytest.raises(RuntimeError, match="partial training update"):
        accel.logits((1, 2))
    with pytest.raises(RuntimeError, match="partial training update"):
        accel.pin()
    with pytest.raises(RuntimeError, match="partial training update"):
        accel.sync()


@pytest.mark.parametrize("kv_dtype", ["fp32", "fp16", "bf16"])
def test_opt_in_kv_precision_controls_only_cache_storage(kv_dtype):
    torch = pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = TinyTransformer(
        vocab=("alpha", "beta", "gamma"),
        dim=16, ctx=12, n_heads=4, n_layers=2, d_ff=24,
        norm="rms", ffn_kind="swiglu", position_mode="rope", seed=89,
    )
    reference = TinyTransformer.from_snapshot(model.snapshot())
    accel = TorchAccel(model, device="cpu", kv_dtype=kv_dtype).pin()
    windows = [
        (1, 2, 3), (1, 2, 3, 1), (1, 2, 3, 1, 2),
        (2, 3, 1), (2, 3, 1, 2),
    ]
    expected_dtype = {
        "fp32": torch.float32,
        "fp16": torch.float16,
        "bf16": torch.bfloat16,
    }[kv_dtype]
    max_delta = 0
    for window in windows:
        result = accel.logits_window(window)
        expected = reference._logits(window)
        max_delta = max(max_delta, max(abs(a - b) for a, b in zip(result, expected)))
        assert result == pytest.approx(expected, rel=3e-3, abs=3e-3)
        assert all(x.dtype == expected_dtype for x in accel._key_buffers)
        assert all(x.dtype == expected_dtype for x in accel._value_buffers)
    assert all(p.dtype == torch.float32 for p in accel._params())
    assert accel.kv_reserved_bytes == sum(
        x.numel() * x.element_size()
        for x in accel._key_buffers + accel._value_buffers
    )
    assert max_delta < 3e-3


def test_consumer_kv_fp16_halves_reserved_storage_for_same_shape():
    pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = _model()
    baseline = TorchAccel(model, kv_dtype="fp32").pin()
    compact = TorchAccel(model, kv_dtype="fp16").pin()
    baseline.logits_window((1, 2, 3))
    compact.logits_window((1, 2, 3))
    assert baseline.kv_reserved_bytes == 2 * compact.kv_reserved_bytes
    assert baseline.cached_tokens == compact.cached_tokens == (1, 2, 3)


def test_kv_budget_bounds_peak_allocation_and_fails_closed_instead_of_cpu_fallback():
    pytest.importorskip("torch")
    model = TinyTransformer(
        vocab=("alpha", "beta"), dim=8, ctx=32,
        n_heads=2, n_layers=2, seed=77, d_ff=8,
    )
    model.to("torch", kv_dtype="fp16", max_kv_bytes=300)
    assert model.resident
    cache = KVCache(model.n_layers, model.ctx)
    with pytest.raises(MemoryError, match="max_kv_bytes"):
        model._logits_window((1, 2, 1, 2), cache)
    assert cache.tokens == []
    assert model._accel is not None  # did not switch to an unbudgeted backend
    assert model._accel.kv_reserved_bytes <= 300


@pytest.mark.parametrize("kv_dtype", ["invalid", "", "FP16", None])
def test_kv_precision_rejects_unknown_formats(kv_dtype):
    pytest.importorskip("torch")
    model = _model()
    with pytest.raises(ValueError, match="kv_dtype"):
        model.to("torch", kv_dtype=kv_dtype)


@pytest.mark.parametrize("invalid", [0, -1, True, 1.3, "1024"])
def test_kv_budget_rejects_invalid_limits(invalid):
    pytest.importorskip("torch")
    model = _model()
    with pytest.raises(ValueError, match="max_kv_bytes"):
        model.to("torch", max_kv_bytes=invalid)


def test_runtime_device_policy_admits_compact_kv_and_restores_checkpoint():
    torch = pytest.importorskip("torch")
    model = _model(norm="rms", ffn_kind="swiglu")
    policy = DevicePolicy(
        requested="torch", allow_fallback=False,
        kv_dtype="bf16", kv_limit_bytes=4096,
    )
    runtime = NativeLLMRuntime(model, device_policy=policy)
    assert runtime.device.resident
    assert runtime.device.kv_dtype == "bf16"
    assert runtime.device.kv_limit_bytes == 4096
    assert runtime.model._accel.kv_dtype == torch.bfloat16
    original_receipt = runtime.device.digest
    result = runtime.infer_text("alpha beta gamma")
    assert result.cache_tokens == len(runtime.encode("alpha beta gamma").token_ids)
    assert runtime.model._accel.kv_reserved_bytes <= 4096

    restored = NativeLLMRuntime.restore(runtime.checkpoint())
    assert restored.device_policy.to_dict() == policy.to_dict()
    assert restored.device.digest == original_receipt
    assert restored.model._accel is not None
    assert restored.model._accel.kv_dtype == torch.bfloat16
    assert restored.infer_text("alpha beta gamma").logits == pytest.approx(
        result.logits, rel=3e-3, abs=3e-3
    )


def test_native_policy_default_serialization_preserves_legacy_identity():
    from skeleton.ai.model_runtime.runtime_contracts import DeviceReceipt

    assert DevicePolicy().to_dict() == {
        "requested": "cpu", "allow_fallback": True,
    }
    assert DeviceReceipt("cpu", "cpu", False, False).to_dict() == {
        "requested": "cpu",
        "actual": "cpu",
        "resident": False,
        "degraded": False,
    }
    assert DevicePolicy(
        requested="torch", kv_dtype="fp16", kv_limit_bytes=512
    ).to_dict()["kv_limit_bytes"] == 512


@pytest.mark.parametrize("policy", [
    dict(requested="cpu", kv_dtype="bf16"),
    dict(requested="cpu", kv_limit_bytes=2048),
])
def test_cpu_reference_rejects_inapplicable_kv_backend_policy(policy):
    model = _model()
    with pytest.raises(RuntimeContractError, match="requires a Torch"):
        NativeLLMRuntime(model, device_policy=DevicePolicy(**policy))


@pytest.mark.parametrize("bad", ["fp64", "", None, 3, "BF16"])
def test_device_policy_validates_compact_cache_dtype(bad):
    with pytest.raises(RuntimeContractError, match="KV cache precision"):
        DevicePolicy(requested="torch", kv_dtype=bad)


@pytest.mark.parametrize("bad", [True, 0, -1, 1.5, 2 ** 41])
def test_device_policy_validates_cache_byte_budget(bad):
    with pytest.raises(RuntimeContractError, match="KV cache byte ceiling"):
        DevicePolicy(requested="torch", kv_limit_bytes=bad)


def test_native_runtime_rejects_kv_ceiling_above_authorized_limit():
    from skeleton.ai.model_runtime.runtime_contracts import RuntimeLimits

    model = _model()
    limits = RuntimeLimits(
        max_context=model.ctx, max_new_tokens=2, max_total_tokens=12,
        max_kv_bytes=2048,
    )
    policy = DevicePolicy(requested="torch", kv_limit_bytes=4096)
    with pytest.raises(RuntimeContractError, match="exceeds native runtime"):
        NativeLLMRuntime(model, limits=limits, device_policy=policy)


def test_identical_prompt_reuses_logits_without_duplicate_device_forward(monkeypatch):
    pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = _model(norm="rms", ffn_kind="swiglu")
    accel = TorchAccel(model).pin()
    tokens = (1, 2, 3)
    first = accel.logits_window(tokens)
    assert accel._cached_logits is not None

    def should_not_run(*args, **kwargs):
        raise AssertionError("repeated input should reuse admitted KV logits")

    monkeypatch.setattr(accel, "_cached_step", should_not_run)
    monkeypatch.setattr(accel, "_forward_ids", should_not_run)
    second = accel.logits_window(tokens)
    assert second == first
    second[0] += 100.0  # defensive list copy: no cached mutable result
    assert accel.logits_window(tokens) == first
    accel.reset_decode_cache()
    assert accel._cached_logits is None


def test_short_prompt_extension_reuses_prefix_kv_without_full_prefill(monkeypatch):
    pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = TinyTransformer(
        vocab=("alpha", "beta", "gamma"), dim=8, ctx=16,
        n_heads=2, n_layers=2, d_ff=12, norm="rms",
        ffn_kind="swiglu", seed=103,
    )
    accel = TorchAccel(model).pin()
    assert accel.logits_window((1, 2)) == pytest.approx(model._logits((1, 2)), abs=2e-5)
    original = accel._cached_step
    visited = []

    def visited_step(token):
        visited.append(token)
        return original(token)

    def no_prefill(*args, **kwargs):
        raise AssertionError("continuation unexpectedly triggered full prefill")

    monkeypatch.setattr(accel, "_cached_step", visited_step)
    monkeypatch.setattr(accel, "_forward_ids", no_prefill)
    expected = (1, 2, 3, 1, 2)
    assert accel.logits_window(expected) == pytest.approx(
        model._logits(expected), abs=2e-5, rel=2e-5,
    )
    assert visited == [3, 1, 2]
    assert accel.cached_tokens == expected


def test_prompt_memoization_is_invalidated_on_sgd():
    pytest.importorskip("torch")
    from skeleton.cortex.torch_lm import TorchAccel

    model = _model()
    accel = TorchAccel(model).pin()
    prompt = (1, 2, 3)
    old_logits = accel.logits_window(prompt)
    accel.sgd((1, 2), target=1, lr=0.03)
    assert accel._cached_logits is None
    assert accel.cached_tokens == ()
    new_logits = accel.logits_window(prompt)
    assert new_logits != old_logits
    assert new_logits == pytest.approx(accel.logits(prompt), abs=2e-5)


def test_explicit_compact_kv_policy_never_degrades_after_kernel_failure(monkeypatch):
    pytest.importorskip("torch")
    model = _model()
    model.to("torch", kv_dtype="bf16", max_kv_bytes=4096)
    accel = model._accel
    assert accel is not None and model.resident

    def unavailable_kernel(*args, **kwargs):
        raise RuntimeError("backend does not implement requested kernel")

    monkeypatch.setattr(accel, "logits_window_with_cache", unavailable_kernel)
    cache = KVCache(model.n_layers, model.ctx)
    with pytest.raises(RuntimeError, match="forbids silent CPU fallback"):
        model._logits_window((1, 2), cache)
    assert cache.tokens == []
    assert model._accel is accel
    assert model.resident

    monkeypatch.setattr(accel, "logits", unavailable_kernel)
    with pytest.raises(RuntimeError, match="forbids silent CPU fallback"):
        model._logits((1, 2))
    assert model._accel is accel
