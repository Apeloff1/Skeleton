from __future__ import annotations

import pytest

from skeleton.ai.decision import DecisionContext, DecisionOption, decide


def option(oid, *, admissible=True, utility=0.0, evidence=("ev:1",), uncertainty=0.0):
    return DecisionOption(oid, oid + " description", admissible, utility, evidence, uncertainty)


def test_forbidden_high_utility_option_can_never_win() -> None:
    result = decide(
        DecisionContext(("safety", "quality")),
        (option("forbidden", admissible=False, utility=1_000_000), option("allowed", utility=1)),
    )
    assert result.selected_option_id == "allowed"
    assert result.rejected_option_ids == ("forbidden",)


def test_no_admissible_option_abstains() -> None:
    result = decide(DecisionContext(("policy",)), (option("x", admissible=False, utility=999),))
    assert result.abstained
    assert result.reason == "no_admissible_option"


def test_consequential_choice_requires_evidence() -> None:
    result = decide(
        DecisionContext(("impact",), consequential=True),
        (option("x", evidence=(), utility=5),),
    )
    assert result.abstained
    assert result.reason == "insufficient_evidence_or_certainty"


def test_uncertainty_threshold_causes_abstention() -> None:
    result = decide(
        DecisionContext(("confidence",), max_uncertainty=0.2),
        (option("x", utility=5, uncertainty=0.21),),
    )
    assert result.abstained


def test_preference_ranking_is_deterministic_after_admission() -> None:
    result = decide(
        DecisionContext(("quality",)),
        (option("b", utility=2, uncertainty=0.2), option("a", utility=2, uncertainty=0.1)),
    )
    assert result.selected_option_id == "a"


def test_exact_tie_abstains_instead_of_hiding_arbitrary_choice() -> None:
    result = decide(
        DecisionContext(("quality",)),
        (option("a", utility=2), option("b", utility=2)),
    )
    assert result.abstained
    assert result.reason == "unresolved_tie"


def test_decision_is_never_execution_authority() -> None:
    result = decide(DecisionContext(("quality",)), (option("a", utility=1),))
    assert result.selected_option_id == "a"
    assert result.executable is False


def test_duplicate_option_identity_fails_closed() -> None:
    with pytest.raises(ValueError):
        decide(DecisionContext(("quality",)), (option("a"), option("a")))


@pytest.mark.parametrize("uncertainty", [-0.01, 1.01])
def test_invalid_uncertainty_fails_closed(uncertainty: float) -> None:
    with pytest.raises(ValueError):
        option("a", uncertainty=uncertainty)
