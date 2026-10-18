"""AdamW training, min-p sampling, and lossless speculative verification."""

from __future__ import annotations

import random

import numpy as np
import pytest

from skeleton.ai.model_runtime.runtime_contracts import (
    GenerationConfig,
    RuntimeContractError,
    RuntimeLimits,
)
from skeleton.ai.runtime.inference.local import LocalInferenceRequest
from skeleton.ai.runtime.inference.neural import NeuralLMConfig, NeuralLMError, NumpyRecurrentLM
from skeleton.cortex.attn import sample_logits
from skeleton.cortex.speculative import greedy_speculative
from skeleton.cortex.transformer import TinyTransformer


def _mouth(**kwargs) -> TinyTransformer:
    model = TinyTransformer(
        vocab=("alpha", "beta", "gamma", "delta"),
        dim=8,
        ctx=6,
        n_heads=2,
        n_layers=1,
        d_ff=16,
        seed=11,
        **kwargs,
    )
    model.tie()
    return model


def test_adamw_sequence_lowers_loss_and_rejects_bad_policy():
    torch = pytest.importorskip("torch")
    model = _mouth()
    model.to("torch", prefill_query_chunk=4, max_grad_norm=1.0)
    ids = [1, 2, 3, 2, 1]
    before = model.perplexity("alpha beta gamma")
    for _ in range(25):
        model.adamw_sequence(ids, 0.001, weight_decay=0.001, z_loss=1e-4)
    after = model.perplexity("alpha beta gamma")
    assert after < before
    assert model.steps >= 25
    with pytest.raises(ValueError):
        model.adamw_sequence(ids, 0.0)
    with pytest.raises(ValueError):
        model.adamw_sequence([1], 0.01)
    fresh = _mouth()
    with pytest.raises(RuntimeError):
        fresh.adamw_sequence(ids, 0.01)
    assert torch.is_floating_point(model._accel._E)


def test_adamw_moments_survive_snapshot_sync():
    pytest.importorskip("torch")
    model = _mouth()
    model.to("torch", prefill_query_chunk=4, max_grad_norm=1.0)
    ids = [1, 2, 3, 1]
    model.adamw_sequence(ids, 0.01)
    moments = len(model._accel._adam_moments)
    assert moments > 0
    model.snapshot()
    model.adamw_sequence(ids, 0.01)
    assert model._accel._adam_moments
    model.to("torch", prefill_query_chunk=4, max_grad_norm=1.0)
    assert model._accel._adam_moments == {}


def test_byte_adamw_is_deterministic_and_not_serialized():
    config = NeuralLMConfig(hidden_size=8, seed=5)
    first = NumpyRecurrentLM(model_id="edge", config=config)
    second = NumpyRecurrentLM(model_id="edge", config=config)
    corpus = ("ab ab ab", "abab")
    first.train(corpus, epochs=3, learning_rate=0.05, optimizer="adamw", weight_decay=0.01)
    second.train(corpus, epochs=3, learning_rate=0.05, optimizer="adamw", weight_decay=0.01)
    assert first.model_digest == second.model_digest
    assert first.loss(corpus) < NumpyRecurrentLM(model_id="edge", config=config).loss(corpus)
    assert "adam" not in first.to_dict()["parameters"]
    with pytest.raises(NeuralLMError):
        first.train_document("ab", optimizer="lion")


def test_default_byte_sampling_digest_is_unchanged_by_policy_defaults():
    plain = LocalInferenceRequest(prompt="ab", max_output_tokens=4, seed=3)
    explicit = LocalInferenceRequest(
        prompt="ab",
        max_output_tokens=4,
        seed=3,
        temperature=1,
        top_k=0,
        top_p=1,
        min_p=0,
        repetition_penalty=1,
    )
    assert plain.digest == explicit.digest
    shifted = LocalInferenceRequest(prompt="ab", max_output_tokens=4, seed=3, min_p=0.1)
    assert shifted.digest != plain.digest
    model = NumpyRecurrentLM(config=NeuralLMConfig(hidden_size=8, seed=9))
    model.train(("abcabc",), epochs=2, learning_rate=0.08)
    import threading
    base = model.infer(plain, threading.Event())
    again = model.infer(plain, threading.Event())
    assert base.text == again.text
    peaked = model.infer(
        LocalInferenceRequest(prompt="ab", max_output_tokens=4, seed=3, temperature=0.0),
        threading.Event(),
    )
    assert peaked.text


def test_min_p_keeps_only_the_peak_and_preserves_default_digest():
    logits = [0.0, 4.0, 0.2]
    rng = random.Random(1)
    assert sample_logits(logits, rng, min_p=0.9) == 1
    with pytest.raises(ValueError):
        sample_logits(logits, rng, min_p=1.5)
    limits = RuntimeLimits(max_context=32, max_new_tokens=8, max_total_tokens=40)
    config = GenerationConfig(max_new_tokens=4, min_p=0.05).validate(limits=limits, vocab_size=8)
    assert config.to_dict()["min_p"] == 0.05
    historical = GenerationConfig(max_new_tokens=4).validate(limits=limits, vocab_size=8)
    assert "min_p" not in historical.to_dict()
    with pytest.raises(RuntimeContractError):
        GenerationConfig(max_new_tokens=4, min_p=2).validate(limits=limits, vocab_size=8)


def test_speculative_publication_matches_verifier_greedy():
    verifier = _mouth()
    draft = _mouth(norm="rms", ffn_kind="swiglu")
    prefix = verifier._ids("alpha beta")
    published, result = greedy_speculative(verifier, draft, prefix, 5, proposals=3)
    greedy = []
    context = list(prefix)
    for _ in range(5):
        window = context[-verifier.ctx:]
        logits = verifier._logits(window)
        nxt = max(range(len(logits)), key=lambda index: (logits[index], -index))
        greedy.append(nxt)
        context.append(nxt)
    assert list(published) == greedy
    assert result.proposed >= result.accepted_count
    assert 0.0 <= result.acceptance_rate <= 1.0


def test_numpy_policy_min_p_is_deterministic():
    model = NumpyRecurrentLM(config=NeuralLMConfig(hidden_size=6, seed=2))
    request = LocalInferenceRequest(prompt="zz", max_output_tokens=3, seed=4, min_p=1.0)
    import threading
    first = model.infer(request, threading.Event())
    second = model.infer(request, threading.Event())
    assert first.text == second.text
    assert np.isfinite(model.loss(("zz",)))
