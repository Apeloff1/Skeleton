from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.attention_patterns import (
    AttentionPatternSample,
    analyze_attention_patterns,
)
from skeleton.ai.research.model_internals.reverse_engineering.logit_trajectory import (
    LogitLensSnapshot,
    analyze_logit_trajectory,
)
from skeleton.ai.research.model_internals.reverse_engineering.multimodal_adapter import (
    AdapterProjection,
    analyze_multimodal_adapters,
)
from skeleton.ai.research.model_internals.reverse_engineering.representation_drift import (
    LayerRepresentation,
    analyze_representation_drift,
)
from skeleton.ai.research.model_internals.reverse_engineering.tool_topology import (
    ToolCallObservation,
    analyze_tool_topology,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_representation_drift_tracks_adjacent_layer_change():
    reports = analyze_representation_drift(
        (
            LayerRepresentation("s", d("input"), 0, (1.0, 0.0)),
            LayerRepresentation("s", d("input"), 1, (1.0, 0.0)),
            LayerRepresentation("s", d("input"), 2, (0.0, 1.0)),
        )
    )
    assert len(reports) == 2
    assert reports[0].mean_cosine_drift == 0.0
    assert reports[1].mean_cosine_drift == 1.0


def test_logit_trajectory_finds_final_token_stabilization():
    report = analyze_logit_trajectory(
        (
            LogitLensSnapshot("s", d("input"), 0, 1, 0.2),
            LogitLensSnapshot("s", d("input"), 1, 2, 0.4),
            LogitLensSnapshot("s", d("input"), 2, 2, 0.6),
            LogitLensSnapshot("s", d("input"), 3, 2, 0.8),
        )
    )[0]
    assert report.final_top_token_id == 2
    assert report.stabilization_layer == 1
    assert report.top_token_change_count == 1


def test_attention_pattern_detects_first_position_sink_candidate():
    report = analyze_attention_patterns(
        (
            AttentionPatternSample("a", d("a"), 1, 0, (0.7, 0.1, 0.1, 0.1)),
            AttentionPatternSample("b", d("b"), 1, 0, (0.6, 0.2, 0.1, 0.1)),
        ),
        sink_threshold=0.5,
    )[0]
    assert report.sink_candidate_ratio == 1.0
    assert report.mean_first_position_weight > report.mean_last_position_weight
    assert report.mean_effective_support > 1.0


def test_multimodal_adapter_geometry_counts_projection_shapes():
    receipt = d("receipt")
    report = analyze_multimodal_adapters(
        (
            AdapterProjection("vision", "vision", "model", 768, 4096, 64, receipt),
            AdapterProjection("audio", "audio", "model", 1024, 4096, 128, receipt),
            AdapterProjection("model-out", "model", "vision", 4096, 768, None, receipt),
        )
    )
    assert report.projection_count == 3
    assert report.expansion_count == 2
    assert report.contraction_count == 1
    assert report.low_rank_projection_count == 2


def test_tool_topology_reconstructs_edges_and_success_rates():
    observations = (
        ToolCallObservation("1", "t1", 0, "agent", "search", d("i1"), d("o1"), True),
        ToolCallObservation("2", "t1", 1, "agent", "fetch", d("i2"), d("o2"), True),
        ToolCallObservation("3", "t1", 2, "agent", "search", d("i3"), d("o3"), False),
        ToolCallObservation("4", "t2", 0, "planner", "search", d("i4"), d("o4"), True),
        ToolCallObservation("5", "t2", 1, "planner", "fetch", d("i5"), d("o5"), True),
    )
    report = analyze_tool_topology(observations)
    assert report.trace_count == 2
    assert ("agent", "search", 2) in report.caller_tool_edges
    assert ("search", "fetch", 2) in report.tool_transition_edges
    assert ("fetch", "search", 1) in report.tool_transition_edges
    assert report.cycle_candidate_count == 1
    rates = dict(report.tool_success_rates)
    assert rates["fetch"] == 1.0
    assert rates["search"] == 2 / 3
