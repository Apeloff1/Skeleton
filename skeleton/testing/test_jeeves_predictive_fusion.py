from __future__ import annotations

import pytest

from skeleton.jeeves.agent.predictive_fusion import (
    FusionPolicy,
    PredictiveFusionEngine,
    PredictiveSignal,
    PredictiveSource,
)


def _signal(
    signal_id: str,
    probability: float,
    *,
    group: str,
    source_key: str,
    weight: float = 0.6,
) -> PredictiveSignal:
    return PredictiveSignal(
        signal_id=signal_id,
        proposition="event-x",
        probability=probability,
        source=PredictiveSource.OTHER,
        source_key=source_key,
        independence_group=group,
        base_weight=weight,
        ambiguity=0.0,
    )


def test_correlated_signals_are_discounted_instead_of_counted_as_independent_votes() -> None:
    engine = PredictiveFusionEngine()
    signals = (
        _signal("a", 0.90, group="semantic-family", source_key="lens-a"),
        _signal("b", 0.88, group="semantic-family", source_key="lens-b"),
        _signal("c", 0.25, group="causal-model", source_key="causal"),
    )
    result = engine.fuse("event-x", signals)
    weights = {item.signal_id: item.effective_weight for item in result.attributions}
    assert weights["a"] < weights["c"]
    assert weights["b"] < weights["c"]
    assert result.independence_groups == ("causal-model", "semantic-family")
    assert result.robust_lower == pytest.approx(0.25)
    assert result.robust_upper == pytest.approx(0.90)
    assert result.disagreement == pytest.approx(0.65)


def test_single_dependence_group_is_explicitly_underidentified() -> None:
    engine = PredictiveFusionEngine(policy=FusionPolicy(minimum_independence_groups=2))
    result = engine.fuse(
        "event-x",
        (
            _signal("a", 0.70, group="same", source_key="a"),
            _signal("b", 0.72, group="same", source_key="b"),
        ),
    )
    assert result.underidentified is True
    assert result.independence_groups == ("same",)


def test_reliability_updates_change_future_signal_weight_without_becoming_evidence() -> None:
    engine = PredictiveFusionEngine()
    before = engine.reliability("model-a").mean
    for _ in range(6):
        engine.record_outcome("model-a", predicted_probability=0.8, outcome=True)
    after = engine.reliability("model-a").mean
    assert after > before
    signal = _signal("a", 0.8, group="g1", source_key="model-a")
    result = engine.fuse("event-x", (signal,))
    attribution = result.attributions[0]
    assert attribution.reliability == pytest.approx(after)
    assert result.evidence_ids == ()


def test_neutral_prediction_updates_symmetrically_and_rejects_invalid_weight() -> None:
    engine = PredictiveFusionEngine()
    posterior = engine.record_outcome("neutral", predicted_probability=0.5, outcome=True, weight=2.0)
    assert posterior.successes == pytest.approx(2.0)
    assert posterior.failures == pytest.approx(2.0)
    assert posterior.mean == pytest.approx(0.5)
    with pytest.raises(Exception):
        engine.record_outcome("bad", predicted_probability=0.7, outcome=True, weight=0.0)


def test_high_cross_source_disagreement_is_preserved_not_averaged_away() -> None:
    engine = PredictiveFusionEngine(policy=FusionPolicy(high_disagreement_threshold=0.20))
    result = engine.fuse(
        "event-x",
        (
            _signal("memory", 0.85, group="memory", source_key="memory"),
            _signal("causal", 0.20, group="causal", source_key="causal"),
            _signal("game", 0.65, group="game", source_key="game"),
        ),
    )
    assert result.underidentified is True
    assert result.disagreement == pytest.approx(0.65)
    assert result.robust_lower == pytest.approx(0.20)
    assert result.robust_upper == pytest.approx(0.85)
    assert 0.20 < result.probability < 0.85
