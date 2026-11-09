from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.objective_normalization import (
    NormalizedObjective,
    ObjectiveAmbiguity,
    ObjectiveAssumption,
    normalize_objective,
)
from skeleton.contracts.canonical import canonical_json_bytes


def test_normalization_preserves_original_and_records_interpretation() -> None:
    assumption = ObjectiveAssumption("scope", "repository only", "explicit user constraint")
    result = normalize_objective("Build   the system", assumptions=(assumption,))
    assert result.original == "Build   the system"
    assert result.canonical == "Build the system"
    assert result.assumptions == (assumption,)


def test_identity_uses_shared_canonical_bytes() -> None:
    result = normalize_objective("Build safely")
    assert result.identity == hashlib.sha256(canonical_json_bytes(result.canonical_payload())).hexdigest()


def test_high_impact_ambiguity_requires_clarification_or_bounded_alternative() -> None:
    with pytest.raises(ValueError):
        normalize_objective("Delete old state", ambiguity=ObjectiveAmbiguity.HIGH_IMPACT)

    clarification = normalize_objective(
        "Delete old state",
        ambiguity=ObjectiveAmbiguity.HIGH_IMPACT,
        clarification_required=True,
    )
    assert clarification.clarification_required

    bounded = normalize_objective(
        "Change production",
        ambiguity=ObjectiveAmbiguity.HIGH_IMPACT,
        bounded_alternatives=("prepare dry-run only", "produce reviewable proposal"),
    )
    assert bounded.bounded_alternatives == ("prepare dry-run only", "produce reviewable proposal")


def test_non_high_impact_objective_cannot_spuriously_require_clarification() -> None:
    with pytest.raises(ValueError):
        normalize_objective("Document module", clarification_required=True)


def test_alternatives_are_bounded_unique_and_explicit() -> None:
    with pytest.raises(ValueError):
        normalize_objective(
            "Choose",
            ambiguity=ObjectiveAmbiguity.HIGH_IMPACT,
            bounded_alternatives=("a", "b", "c", "d"),
        )
    with pytest.raises(ValueError):
        normalize_objective(
            "Choose",
            ambiguity=ObjectiveAmbiguity.HIGH_IMPACT,
            bounded_alternatives=("a", "a"),
        )


def test_assumption_provenance_is_mandatory_and_unique() -> None:
    with pytest.raises(ValueError):
        ObjectiveAssumption("scope", "repository", "")
    assumption = ObjectiveAssumption("scope", "repository", "request")
    with pytest.raises(ValueError):
        NormalizedObjective(
            "Build",
            "Build",
            (assumption, assumption),
            ObjectiveAmbiguity.NONE,
        )


def test_unicode_is_canonicalized_without_losing_original() -> None:
    result = normalize_objective("Ｂuild safely")
    assert result.original == "Ｂuild safely"
    assert result.canonical == "Build safely"


@pytest.mark.parametrize("requested", ["", " leading", "trailing "])
def test_malformed_requested_objective_fails_closed(requested: str) -> None:
    with pytest.raises(ValueError):
        normalize_objective(requested)
