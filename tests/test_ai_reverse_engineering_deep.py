from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering import (
    ContextTrial,
    DecodeSample,
    InferenceClaim,
    ReplicationAttempt,
    RoutingObservation,
    StateTrial,
    analyze_state_memory,
    build_experiment_matrix,
    characterize_context,
    decoding_signatures,
    replication_status,
    routing_fingerprint,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_context_characterization_brackets_high_fidelity_boundary():
    trials = (
        ContextTrial("a", 1024, True, 1.0, d("a")),
        ContextTrial("b", 4096, True, 0.96, d("b")),
        ContextTrial("c", 8192, True, 0.88, d("c")),
        ContextTrial("d", 16384, False, 0.0, d("d")),
    )
    report = characterize_context(trials)[0]
    assert report.lower_bound_units == 4096
    assert report.upper_bound_units == 8192
    assert report.first_failure_units == 16384
    assert report.monotonicity_violations == 0


def test_context_characterization_detects_non_monotonic_trials():
    trials = (
        ContextTrial("a", 100, False, 0.0, d("a")),
        ContextTrial("b", 200, True, 1.0, d("b")),
    )
    assert characterize_context(trials)[0].monotonicity_violations == 1


def test_routing_fingerprint_is_deterministic_and_class_sensitive():
    observations = (
        RoutingObservation("1", "short", "fast", d("1")),
        RoutingObservation("2", "short", "fast", d("2")),
        RoutingObservation("3", "deep", "reasoning", d("3")),
        RoutingObservation("4", "mixed", "fast", d("4")),
        RoutingObservation("5", "mixed", "reasoning", d("5")),
    )
    first = routing_fingerprint(observations)
    second = routing_fingerprint(tuple(reversed(observations)))
    assert first.digest == second.digest
    assert first.deterministic_class_ratio == 2 / 3
    assert first.route_entropy_proxy > 0.0


def test_state_memory_report_surfaces_cross_reset_recall():
    repeated_input = d("same")
    trials = (
        StateTrial("1", "s", 0, repeated_input, d("o1")),
        StateTrial("2", "s", 1, repeated_input, d("o2"), recall_marker=True),
        StateTrial("3", "s", 2, d("reset"), d("o3"), reset_before=True, recall_marker=True),
    )
    report = analyze_state_memory(trials)
    assert report.repeated_input_divergence_ratio > 0.0
    assert report.cross_reset_carryover_count == 1
    assert report.reset_count == 1


def test_decoding_signature_measures_black_box_variability():
    samples = (
        DecodeSample("1", "temperature-low", d("same"), 10, "stop"),
        DecodeSample("2", "temperature-low", d("same"), 10, "stop"),
        DecodeSample("3", "temperature-low", d("different"), 12, "length"),
    )
    sig = decoding_signatures(samples)[0]
    assert sig.unique_output_count == 2
    assert sig.diversity_ratio == 2 / 3
    assert sig.collision_ratio == 1 / 3
    assert sig.max_output_units == 12


def test_experiment_matrix_has_stable_protocol_ids():
    factors = {"temperature": ("low", "high"), "prompt": ("a", "b")}
    first = build_experiment_matrix(factors, replicates=2, seed=7)
    second = build_experiment_matrix(dict(reversed(tuple(factors.items()))), replicates=2, seed=7)
    assert len(first) == 8
    assert [cell.protocol_digest for cell in first] == [cell.protocol_digest for cell in second]
    assert len({cell.cell_id for cell in first}) == 8


def test_replication_requires_supported_claim_and_independent_actors():
    claim = InferenceClaim(
        "observable.route-boundary",
        "A route boundary is observable.",
        0.9,
        ("p1",),
        status="supported",
    )
    attempts = (
        ReplicationAttempt("a", claim.claim_id, d("protocol"), d("e1"), "actor-a", True),
        ReplicationAttempt("b", claim.claim_id, d("protocol"), d("e2"), "actor-b", True),
        ReplicationAttempt("c", claim.claim_id, d("protocol"), d("e3"), "actor-c", False),
    )
    status = replication_status(claim, attempts, minimum_ratio=0.66)
    assert status.independent_actors == 3
    assert status.reproduction_ratio == 2 / 3
    assert status.independently_replicated is True


def test_replication_does_not_promote_hypothesis():
    claim = InferenceClaim(
        "observable.maybe",
        "Only a hypothesis.",
        0.9,
        ("p1",),
        status="hypothesis",
    )
    attempts = (
        ReplicationAttempt("a", claim.claim_id, d("protocol"), d("e1"), "actor-a", True),
        ReplicationAttempt("b", claim.claim_id, d("protocol"), d("e2"), "actor-b", True),
    )
    assert replication_status(claim, attempts).independently_replicated is False
