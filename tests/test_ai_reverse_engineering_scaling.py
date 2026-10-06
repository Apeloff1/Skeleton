from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.latency_scaling import (
    LatencyObservation,
    analyze_latency_scaling,
)
from skeleton.ai.research.model_internals.reverse_engineering.model_correspondence import (
    CorrespondencePair,
    analyze_model_correspondence,
)
from skeleton.ai.research.model_internals.reverse_engineering.position_sensitivity import (
    PositionTrial,
    analyze_position_sensitivity,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_position_sensitivity_tracks_decay_with_offset():
    report = analyze_position_sensitivity(
        (
            PositionTrial("a", "p", d("content"), 0, 1.0, d("o0")),
            PositionTrial("b", "p", d("content"), 128, 0.98, d("o1")),
            PositionTrial("c", "p", d("content"), 256, 0.90, d("o2")),
            PositionTrial("d", "p", d("content"), 512, 0.70, d("o3")),
        )
    )[0]
    assert report.anchor_offset == 0
    assert report.max_offset == 512
    assert abs(report.similarity_drop - 0.3) < 1e-12
    assert report.monotonicity_violations == 0
    assert report.invariant_above_095_ratio == 0.5


def test_latency_scaling_recovers_linear_exponent():
    report = analyze_latency_scaling(
        (
            LatencyObservation("a", "prefill", 100, 0, 10.0),
            LatencyObservation("b", "prefill", 200, 0, 20.0),
            LatencyObservation("c", "prefill", 400, 0, 40.0),
            LatencyObservation("d", "prefill", 800, 0, 80.0),
        )
    )[0]
    assert report.log_log_exponent is not None
    assert abs(report.log_log_exponent - 1.0) < 1e-12
    assert report.r_squared is not None and abs(report.r_squared - 1.0) < 1e-12
    assert report.mean_ms_per_scale_unit == 0.1


def test_model_correspondence_is_order_independent_across_model_labels():
    pairs = (
        CorrespondencePair("a", d("a"), "model-a", "model-b", (1.0, 0.0), (1.0, 0.0)),
        CorrespondencePair("b", d("b"), "model-b", "model-a", (0.0, 2.0), (0.0, 1.0)),
    )
    report = analyze_model_correspondence(pairs)[0]
    assert report.left_model == "model-a"
    assert report.right_model == "model-b"
    assert report.pair_count == 2
    assert report.mean_cosine_similarity == 1.0
    assert report.dimension == 2
