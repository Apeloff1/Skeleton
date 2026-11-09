from __future__ import annotations

from hashlib import sha256

import pytest

from skeleton.ai.research.model_internals.reverse_engineering.activation_geometry import (
    ActivationSample,
    analyze_activation_geometry,
)
from skeleton.ai.research.model_internals.reverse_engineering.architecture_family import (
    ArchitectureSignals,
    classify_architecture_family,
)
from skeleton.ai.research.model_internals.reverse_engineering.attention_geometry import (
    AttentionLayerShape,
    AttentionMode,
    analyze_attention_geometry,
)
from skeleton.ai.research.model_internals.reverse_engineering.embedding_geometry import (
    EmbeddingSample,
    analyze_embedding_geometry,
)
from skeleton.ai.research.model_internals.reverse_engineering.kv_cache import (
    KVCacheObservation,
    analyze_kv_cache,
)
from skeleton.ai.research.model_internals.reverse_engineering.tokenizer_fingerprint import (
    TokenizationSample,
    fingerprint_tokenizer,
)
from skeleton.ai.research.model_internals.reverse_engineering.contracts import (
    ReverseEngineeringError,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_tokenizer_fingerprint_is_order_independent_and_uses_digests():
    samples = (
        TokenizationSample("a", d("raw-a"), 10, (1, 2, 3)),
        TokenizationSample("b", d("raw-b"), 6, (2, 4)),
    )
    first = fingerprint_tokenizer(samples)[0]
    second = fingerprint_tokenizer(tuple(reversed(samples)))[0]
    assert first.digest == second.digest
    assert first.total_tokens == 5
    assert first.unique_token_ids == 4
    assert first.mean_characters_per_token == 16 / 5


def test_embedding_geometry_rejects_dimension_mismatch():
    samples = (
        EmbeddingSample("a", d("a"), (1.0, 0.0)),
        EmbeddingSample("b", d("b"), (1.0, 0.0, 0.0)),
    )
    with pytest.raises(ReverseEngineeringError, match="dimensions must match"):
        analyze_embedding_geometry(samples)


def test_embedding_geometry_measures_cosine_and_centroid():
    report = analyze_embedding_geometry(
        (
            EmbeddingSample("a", d("a"), (1.0, 0.0)),
            EmbeddingSample("b", d("b"), (0.0, 1.0)),
        )
    )[0]
    assert report.dimension == 2
    assert report.mean_pairwise_cosine == 0.0
    assert report.zero_norm_count == 0
    assert report.centroid_norm > 0.0


def test_kv_cache_linear_scaling_matches_theoretical_geometry():
    observations = (
        KVCacheObservation("a", 100, 1, 2, 4, 2, 8, 2.0, observed_bytes=19200),
        KVCacheObservation("b", 200, 1, 2, 4, 2, 8, 2.0, observed_bytes=38400),
        KVCacheObservation("c", 400, 1, 2, 4, 2, 8, 2.0, observed_bytes=76800),
    )
    report = analyze_kv_cache(observations)
    assert report.approximately_linear is True
    assert report.coefficient_of_variation == 0.0
    assert report.mean_theory_ratio == 1.0
    assert report.max_relative_theory_error == 0.0


def test_attention_geometry_distinguishes_gqa():
    report = analyze_attention_geometry(
        (
            AttentionLayerShape(0, 16, 4, 64, 1024),
            AttentionLayerShape(1, 16, 4, 64, 1024),
        )
    )
    assert report.uniform_mode == AttentionMode.GQA.value
    assert report.query_to_kv_ratios == (4,)
    assert report.width_mismatch_count == 0


def test_activation_geometry_reports_sparsity_per_layer():
    report = analyze_activation_geometry(
        (
            ActivationSample("a", "layer-0", d("a"), (1.0, 0.0, 0.0)),
            ActivationSample("b", "layer-0", d("b"), (0.0, 1.0, 0.0)),
        )
    )[0]
    assert report.dimension == 3
    assert report.zero_fraction == 4 / 6
    assert report.mean_pairwise_cosine == 0.0


def test_architecture_family_scores_gqa_from_independent_signals():
    report = classify_architecture_family(
        ArchitectureSignals(
            indexed_layer_count=24,
            recurrent_shape_group_count=4,
            attention_mode_counts=((AttentionMode.GQA.value, 24),),
            kv_cache_approximately_linear=True,
        )
    )
    assert report.best_family == "transformer_gqa"
    assert report.candidates[0].score > report.candidates[1].score


def test_architecture_family_can_surface_moe_when_expert_evidence_dominates():
    report = classify_architecture_family(
        ArchitectureSignals(
            indexed_layer_count=32,
            attention_mode_counts=((AttentionMode.GQA.value, 32),),
            expert_tensor_count=64,
            kv_cache_approximately_linear=True,
        )
    )
    assert report.best_family == "mixture_of_experts_transformer"
