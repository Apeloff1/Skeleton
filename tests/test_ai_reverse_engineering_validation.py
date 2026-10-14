from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.multimodal_alignment import (
    MultimodalAlignmentPair,
    analyze_multimodal_alignment,
)
from skeleton.ai.research.model_internals.reverse_engineering.probe_calibration import (
    ProbeControlResult,
    calibrate_probes,
)
from skeleton.ai.research.model_internals.reverse_engineering.routing_stability import (
    RoutingWindow,
    analyze_routing_stability,
)
from skeleton.ai.research.model_internals.reverse_engineering.subspace_overlap import (
    SubspaceBasis,
    analyze_subspace_overlap,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_subspace_overlap_recovers_shared_basis_direction():
    left = SubspaceBasis("a", "l1", d("feature-a"), ((1.0, 0.0), (0.0, 1.0)))
    right = SubspaceBasis("b", "l2", d("feature-b"), ((1.0, 0.0), (1.0, 1.0)))
    report = analyze_subspace_overlap(left, right)
    assert report.dimension == 2
    assert report.max_absolute_cosine == 1.0
    assert report.symmetric_overlap_score > 0.8


def test_multimodal_alignment_canonicalizes_modality_order():
    pairs = (
        MultimodalAlignmentPair("a", d("s1"), 3, "vision", "text", (1.0, 0.0), (1.0, 0.0)),
        MultimodalAlignmentPair("b", d("s2"), 3, "text", "vision", (0.0, 1.0), (0.0, 1.0)),
    )
    report = analyze_multimodal_alignment(pairs)[0]
    assert report.modality_a == "text"
    assert report.modality_b == "vision"
    assert report.pair_count == 2
    assert report.mean_cosine_similarity == 1.0


def test_long_horizon_routing_stability_tracks_route_shift():
    report = analyze_routing_stability(
        (
            RoutingWindow("w0", 0, (("a", 90), ("b", 10))),
            RoutingWindow("w1", 1, (("a", 85), ("b", 15))),
            RoutingWindow("w2", 2, (("a", 20), ("b", 80))),
        ),
        stable_threshold=0.1,
    )
    assert report.window_count == 3
    assert report.dominant_route_change_count == 1
    assert report.max_adjacent_total_variation > 0.6
    assert report.stable_below_threshold_ratio == 0.5


def test_probe_calibration_computes_balanced_accuracy_from_controls():
    report = calibrate_probes(
        (
            ProbeControlResult("a", "p", True, True),
            ProbeControlResult("b", "p", True, True),
            ProbeControlResult("c", "p", True, False),
            ProbeControlResult("d", "p", False, False),
            ProbeControlResult("e", "p", False, False),
            ProbeControlResult("f", "p", False, True),
        )
    )[0]
    assert report.true_positive == 2
    assert report.true_negative == 2
    assert report.false_positive == 1
    assert report.false_negative == 1
    assert report.sensitivity == 2 / 3
    assert report.specificity == 2 / 3
    assert report.balanced_accuracy == 2 / 3
