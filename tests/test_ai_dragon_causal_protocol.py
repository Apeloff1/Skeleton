"""Protocol-verification regressions for mechanic causal analysis."""
from skeleton.ai.webcrawler.dragon_mechanic_causal_analysis import (
    MechanicTrial, TrialProtocol, analyze_mechanic_trials,
)


def trials():
    return tuple(
        MechanicTrial(
            f"t-{i}", "jump-window", i % 2 == 0, i % 3 != 0,
            True, "same-build", f"source-{i % 2}",
        )
        for i in range(24)
    )


def protocol(**changes):
    values = dict(
        protocol_id="protocol-1", assignment_digest="a" * 64,
        preregistered=True, allocation_verified=True,
        outcome_definition_locked=True, attrition_accounted=True,
        interference_assessed=True,
    )
    values.update(changes)
    return TrialProtocol(**values)


def test_randomized_flag_alone_never_permits_causal_claim():
    effect = analyze_mechanic_trials(trials(), authorized=True)
    assert effect.randomized_effect_estimate_eligible
    assert not effect.causal_claim_permitted
    assert effect.protocol_id is None


def test_verified_protocol_permits_bounded_randomized_interpretation():
    effect = analyze_mechanic_trials(
        trials(), authorized=True, protocol=protocol(),
    )
    assert effect.randomized_effect_estimate_eligible
    assert effect.causal_claim_permitted
    assert effect.protocol_id == "protocol-1"


def test_incomplete_protocol_fails_closed():
    effect = analyze_mechanic_trials(
        trials(), authorized=True,
        protocol=protocol(interference_assessed=False),
    )
    assert not effect.causal_claim_permitted
    assert "verification incomplete" in " ".join(effect.warnings).lower()
