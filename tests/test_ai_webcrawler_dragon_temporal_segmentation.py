"""Temporal segmentation regressions: real transitions, custody and limits."""
import pytest

from skeleton.ai.webcrawler.dragon_temporal_segmentation import (
    FeatureFrame, SegmentationConfig, segment_feature_trace,
)


def frames(values):
    return tuple(FeatureFrame(
        index * 100, (value,), f"frame-{index}",
    ) for index, value in enumerate(values))


def test_static_scene_has_no_events():
    assert segment_feature_trace(frames([0.2] * 30), authorized=True) == ()


def test_abrupt_transition_is_detected():
    result = segment_feature_trace(
        frames([0.1] * 12 + [0.9] * 5), authorized=True,
    )
    assert result
    assert result[0].interpretation == "unclassified_visual_transition"
    assert result[0].peak_change > 0.5


def test_transition_preserves_frame_provenance():
    result = segment_feature_trace(
        frames([0.1] * 12 + [0.9] * 5), authorized=True,
    )
    assert result[0].source_frame_ids
    assert result[0].peak_ms >= result[0].start_ms


def test_analysis_is_deterministic():
    sample = frames([0.1] * 12 + [0.9] * 5)
    assert segment_feature_trace(sample, authorized=True) == segment_feature_trace(
        sample, authorized=True,
    )


def test_out_of_order_timestamps_rejected():
    sample = (
        FeatureFrame(100, (0.1,), "a"),
        FeatureFrame(100, (0.9,), "b"),
    )
    with pytest.raises(ValueError, match="timestamps"):
        segment_feature_trace(sample, authorized=True)


def test_invalid_feature_values_rejected():
    with pytest.raises(ValueError, match="normalized"):
        segment_feature_trace((
            FeatureFrame(0, (0.1,), "a"),
            FeatureFrame(100, (float("nan"),), "b"),
        ), authorized=True)


def test_frame_budget_enforced():
    with pytest.raises(ValueError, match="budget"):
        segment_feature_trace(
            frames([0.1] * 10), authorized=True,
            config=SegmentationConfig(max_frames=5),
        )


def test_consent_required():
    with pytest.raises(PermissionError):
        segment_feature_trace(frames([0.1, 0.9]), authorized=False)


def test_feature_dimensions_must_match():
    with pytest.raises(ValueError, match="vector"):
        segment_feature_trace((
            FeatureFrame(0, (0.1,), "a"),
            FeatureFrame(100, (0.1, 0.2), "b"),
        ), authorized=True)
