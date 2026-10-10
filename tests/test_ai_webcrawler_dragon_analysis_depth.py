"""Adversarial knowledge stress and gameplay causal analysis tests."""
import pytest
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import EvidencePass
from skeleton.ai.webcrawler.dragon_belief_stress import stress_test_belief
from skeleton.ai.webcrawler.dragon_mechanic_causal_analysis import (
    MechanicTrial, analyze_mechanic_trials,
)


def reading(group, number=1, supports=True):
    return EvidencePass(
        group, "v1", f"pass-{number}", "jump-buffer",
        supports, .9, .9, group, f"frame:{number}", "observed timing",
    )


def test_stress_report_detects_single_source_dependency():
    report = stress_test_belief(
        "jump-buffer", tuple(reading("same", i) for i in (1, 2, 3)),
        authorized=True,
    )
    assert report.requires_adversarial_review
    assert report.largest_group_fraction == 1
    assert report.independent_groups == 1


def test_stress_report_detects_contradictions():
    report = stress_test_belief(
        "jump-buffer", (
            reading("a"), reading("b", supports=False),
        ), authorized=True,
    )
    assert report.requires_adversarial_review
    assert any("Conflicting" in issue for issue in report.failure_modes)


def test_stress_report_deterministic():
    evidence = (reading("a"), reading("b"))
    assert stress_test_belief(
        "jump-buffer", evidence, authorized=True,
    ) == stress_test_belief(
        "jump-buffer", evidence, authorized=True,
    )


def test_stress_requires_authorization():
    with pytest.raises(PermissionError):
        stress_test_belief("jump-buffer", (), authorized=False)


def trials(randomized=True, treated_success=True):
    return tuple(MechanicTrial(
        f"trial-{i}", "jump_buffering", i < 20,
        treated_success if i < 20 else False,
        randomized, "same-level", f"session-{i % 3}",
    ) for i in range(40))


def test_randomization_claim_without_verified_protocol_cannot_be_causal():
    report = analyze_mechanic_trials(trials(), authorized=True)
    assert not report.causal_claim_permitted
    assert any("verified experimental protocol" in warning for warning in report.warnings)
    assert report.observed_difference == 1
    assert report.difference_interval[0] > 0


def test_observational_trials_not_called_causal():
    report = analyze_mechanic_trials(
        trials(randomized=False), authorized=True,
    )
    assert not report.causal_claim_permitted
    assert any("Observational" in x for x in report.warnings)


def test_low_sample_count_restricts_causal_claims():
    report = analyze_mechanic_trials(
        trials()[:5] + trials()[20:25],
        authorized=True,
    )
    assert not report.causal_claim_permitted


def test_duplicate_trial_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        analyze_mechanic_trials(
            (trials()[0], trials()[0]), authorized=True,
        )


def test_trials_require_both_arms():
    with pytest.raises(ValueError, match="both"):
        analyze_mechanic_trials(
            trials()[:20], authorized=True,
        )
