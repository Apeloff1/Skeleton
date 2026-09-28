from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.p1_failure_journeys import (
    FailureJourneyObservation,
    P1FailureJourneyError,
    qualify_p1_failure_journeys,
)


REPOSITORY = "Apeloff1/Skeleton"
HEAD = "a" * 40
PROM01 = "b" * 64
FAMILIES = (
    "adversarial",
    "clean_machine",
    "partition",
    "provider_failover",
    "restore",
    "rollback",
    "saturation",
    "stale_evidence",
)
CLASSES = {
    "adversarial_integrity": ("adversarial",),
    "clean_machine_installation": ("clean_machine",),
    "distributed_degradation": ("partition", "saturation"),
    "evidence_freshness": ("stale_evidence",),
    "provider_resilience": ("provider_failover",),
    "state_recovery": ("restore", "rollback"),
}


def _observation(family: str, **overrides: object) -> FailureJourneyObservation:
    values: dict[str, object] = {
        "family": family,
        "repository": REPOSITORY,
        "commit_sha": HEAD,
        "verifier_id": f"pytest:{family}",
        "verifier_digest": "c" * 64,
        "test_manifest_digest": "d" * 64,
        "passed": True,
        "independent": True,
        "evidence_refs": (
            EvidenceRef(
                source=f"pytest://{family}",
                digest="e" * 64,
                category="failure_journey",
            ),
        ),
    }
    values.update(overrides)
    return FailureJourneyObservation(**values)


def _observations() -> tuple[FailureJourneyObservation, ...]:
    return tuple(_observation(family) for family in FAMILIES)


def _qualify(observations=None, **overrides):
    values = {
        "observations": _observations() if observations is None else observations,
        "expected_repository": REPOSITORY,
        "expected_head": HEAD,
        "required_families": FAMILIES,
        "required_journey_classes": tuple(sorted(CLASSES)),
        "journey_class_families": CLASSES,
        "prom01_bundle_digest": PROM01,
    }
    values.update(overrides)
    return qualify_p1_failure_journeys(**values)


def test_all_failure_families_qualify_on_exact_head() -> None:
    decision = _qualify()
    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.required_families == tuple(sorted(FAMILIES))
    assert len(decision.observation_digests) == len(FAMILIES)
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "p1_terminal_failure_journeys"
    assert evidence.digest == decision.decision_digest


def test_missing_family_rejects() -> None:
    decision = _qualify(_observations()[1:])
    assert decision.accepted is False
    assert "missing-family:adversarial" in decision.reasons


def test_duplicate_family_rejects() -> None:
    rows = _observations()
    decision = _qualify((*rows, rows[0]))
    assert decision.accepted is False
    assert "duplicate-family:adversarial" in decision.reasons


def test_unknown_family_rejects() -> None:
    decision = _qualify(
        (*_observations(), _observation("not-required"))
    )
    assert decision.accepted is False
    assert "unknown-family:not-required" in decision.reasons


def test_stale_head_and_wrong_repository_reject() -> None:
    rows = list(_observations())
    rows[0] = replace(rows[0], commit_sha="f" * 40)
    rows[1] = replace(rows[1], repository="Other/Skeleton")
    decision = _qualify(tuple(rows))
    assert decision.accepted is False
    assert "exact-head-mismatch:adversarial" in decision.reasons
    assert "repository-mismatch:clean_machine" in decision.reasons


def test_failed_or_non_independent_journey_rejects() -> None:
    rows = list(_observations())
    rows[0] = replace(rows[0], passed=False)
    rows[1] = replace(rows[1], independent=False)
    decision = _qualify(tuple(rows))
    assert decision.accepted is False
    assert "journey-failed:adversarial" in decision.reasons
    assert "journey-not-independent:clean_machine" in decision.reasons


def test_unmapped_required_journey_class_rejects() -> None:
    decision = _qualify(
        required_journey_classes=(
            *tuple(sorted(CLASSES)),
            "missing_class",
        )
    )
    assert decision.accepted is False
    assert "journey-class-unmapped:missing_class" in decision.reasons


def test_journey_class_unknown_family_rejects() -> None:
    classes = {**CLASSES, "bad": ("not-required",)}
    decision = _qualify(
        required_journey_classes=tuple(sorted(classes)),
        journey_class_families=classes,
    )
    assert decision.accepted is False
    assert "journey-class-unknown-family:bad:not-required" in decision.reasons


def test_journey_class_uncovered_when_member_observation_missing() -> None:
    rows = tuple(
        row for row in _observations()
        if row.family != "restore"
    )
    decision = _qualify(rows)
    assert decision.accepted is False
    assert "journey-class-uncovered:state_recovery:restore" in decision.reasons


def test_rejected_decision_cannot_materialize_evidence() -> None:
    decision = _qualify(_observations()[1:])
    assert decision.accepted is False
    with pytest.raises(
        P1FailureJourneyError,
        match="cannot become promotion evidence",
    ):
        decision.accepted_evidence_ref()
