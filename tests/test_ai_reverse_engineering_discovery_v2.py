from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.causal_directionality import (
    DirectionalEffect,
    analyze_causal_directionality,
)
from skeleton.ai.research.model_internals.reverse_engineering.information_gain import (
    analyze_information_gain,
)
from skeleton.ai.research.model_internals.reverse_engineering.intervention_specificity import (
    SpecificityObservation,
    analyze_intervention_specificity,
)
from skeleton.ai.research.model_internals.reverse_engineering.probe_redundancy import (
    ProbeOutcomeVector,
    analyze_probe_redundancy,
)
from skeleton.ai.research.model_internals.reverse_engineering.signature_distance import (
    analyze_signature_distance,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_directionality_finds_stronger_forward_effect():
    probe = d("probe")
    report = analyze_causal_directionality(
        (
            DirectionalEffect("a", probe, "x", "y", 0.9),
            DirectionalEffect("b", probe, "x", "y", 0.7),
            DirectionalEffect("c", probe, "y", "x", 0.2),
            DirectionalEffect("d", probe, "y", "x", 0.1),
        )
    )[0]
    assert report.dominant_direction == "x->y"
    assert report.asymmetry is not None and report.asymmetry > 0.6


def test_intervention_specificity_separates_target_and_off_target_effects():
    report = analyze_intervention_specificity(
        (
            SpecificityObservation("a", "u1", "u1", 1.0),
            SpecificityObservation("b", "u1", "u2", 0.1),
            SpecificityObservation("c", "u1", "u3", 0.05),
        )
    )
    assert report.on_target_count == 1
    assert report.off_target_count == 2
    assert report.specificity_ratio is not None and report.specificity_ratio > 10.0


def test_probe_redundancy_suggests_duplicate_probe_drop():
    report = analyze_probe_redundancy(
        (
            ProbeOutcomeVector("a", (True, False, True, False)),
            ProbeOutcomeVector("b", (True, False, True, False)),
            ProbeOutcomeVector("c", (False, False, True, True)),
        )
    )
    assert len(report.redundant_pairs) == 1
    assert report.suggested_drop_ids == ("b",)


def test_information_gain_reduces_entropy():
    report = analyze_information_gain(
        {"a": 0.5, "b": 0.5},
        {"a": 0.9, "b": 0.1},
    )
    assert report.information_gain_bits > 0.0
    assert report.normalized_information_gain > 0.0


def test_signature_distance_identifies_close_signatures():
    report = analyze_signature_distance(
        {"a": 0.1, "b": 0.2, "c": 0.3},
        {"a": 0.11, "b": 0.19, "c": 0.29},
        closeness_threshold=0.02,
    )
    assert report.closest is True
    assert report.max_absolute_distance <= 0.02
