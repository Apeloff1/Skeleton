from skeleton.jeeves.agent.interpretive_science import (
    LensOutcomeTrial,
    ScientificLensLab,
    ScientificLensPolicy,
    ScientificLensStatus,
)
from skeleton.jeeves.agent.lens_governance import (
    LensPermission,
    LensScienceRegistry,
    ScientificGrade,
)
from skeleton.jeeves.agent.lens_system import (
    LensActivation,
    LensAuthority,
    LensDefinition,
    LensFamily,
)


def _activation(lens_id: str, authority: LensAuthority, *, score: float = 0.8) -> LensActivation:
    definition = LensDefinition(
        lens_id=lens_id,
        name=lens_id,
        family=LensFamily.LUDIC,
        authority=authority,
        description="test lens",
        cues=("test",),
        outputs=("hypothesis",),
    )
    return LensActivation(
        lens=definition,
        score=score,
        cue_score=score,
        relation_score=0.0,
        novelty_score=0.5,
        matched_cues=("test",),
        rationale="fixture",
    )


def test_kuleshov_is_empirical_but_shadow_mode_cannot_drive_decisions():
    registry = LensScienceRegistry()
    decision = registry.assess(_activation("kuleshov_juxtaposition", LensAuthority.INTERPRETIVE))
    profile = registry.profile(_activation("kuleshov_juxtaposition", LensAuthority.INTERPRETIVE).lens)
    assert profile.grade is ScientificGrade.EMPIRICAL
    assert profile.references[0].locator == "doi:10.1371/journal.pone.0308295"
    assert decision.scientific_status is ScientificLensStatus.SHADOW
    assert LensPermission.HYPOTHESIS_GENERATION in decision.permissions
    assert decision.decision_feature_authorized is False
    assert decision.factual_assertion_authorized is False
    assert decision.causal_assertion_authorized is False


def test_formal_partial_observability_can_be_a_decision_feature_without_becoming_truth():
    registry = LensScienceRegistry()
    decision = registry.assess(_activation("partial_observability", LensAuthority.FORMAL))
    assert decision.grade is ScientificGrade.FORMAL
    assert decision.decision_feature_authorized is True
    assert LensPermission.DECISION_FEATURE in decision.permissions
    assert decision.factual_assertion_authorized is False
    assert decision.causal_assertion_authorized is False


def test_interpretive_procedural_rhetoric_never_gets_direct_decision_authority_by_default():
    registry = LensScienceRegistry()
    decision = registry.assess(_activation("procedural_rhetoric", LensAuthority.INTERPRETIVE))
    assert decision.grade is ScientificGrade.INTERPRETIVE
    assert decision.decision_feature_authorized is False
    assert LensPermission.QUERY_SELECTION in decision.permissions
    assert LensPermission.HYPOTHESIS_GENERATION in decision.permissions


def test_empirical_lens_must_earn_active_calibration_before_decision_use():
    policy = ScientificLensPolicy(
        minimum_trials=4,
        minimum_independent_runs=2,
        minimum_domains_for_transfer=2,
        minimum_transfer_trials_per_domain=2,
        maximum_brier=0.25,
        maximum_ece=0.20,
        minimum_brier_gain_over_base_rate=0.01,
    )
    lab = ScientificLensLab(policy=policy)
    rows = (
        ("a", 0.9, True, "film", "r1"),
        ("b", 0.8, True, "film", "r2"),
        ("c", 0.1, False, "dialogue", "r1"),
        ("d", 0.2, False, "dialogue", "r2"),
    )
    for trial_id, p, outcome, domain, run in rows:
        lab.record(
            LensOutcomeTrial(
                trial_id=trial_id,
                lens_key="kuleshov_juxtaposition",
                probability=p,
                outcome=outcome,
                domain=domain,
                independent_run=run,
                proposition="adjacent context changes interpretation",
            )
        )
    assert lab.report("kuleshov_juxtaposition").status is ScientificLensStatus.ACTIVE
    decision = LensScienceRegistry(lab=lab).assess(
        _activation("kuleshov_juxtaposition", LensAuthority.INTERPRETIVE)
    )
    assert decision.decision_feature_authorized is True
    assert LensPermission.DECISION_FEATURE in decision.permissions
    assert decision.factual_assertion_authorized is False
    assert decision.causal_assertion_authorized is False


def test_rejected_lens_is_confined_to_query_and_counter_hypothesis_work():
    policy = ScientificLensPolicy(
        minimum_trials=4,
        minimum_independent_runs=2,
        minimum_domains_for_transfer=1,
        minimum_transfer_trials_per_domain=1,
        reject_brier=0.30,
        reject_ece=0.30,
    )
    lab = ScientificLensLab(policy=policy)
    for index, outcome in enumerate((False, False, True, True)):
        lab.record(
            LensOutcomeTrial(
                trial_id=f"bad-{index}",
                lens_key="kuleshov_juxtaposition",
                probability=0.99 if not outcome else 0.01,
                outcome=outcome,
                domain="film",
                independent_run=f"r{index % 2}",
                proposition="bad forecast",
            )
        )
    decision = LensScienceRegistry(lab=lab).assess(
        _activation("kuleshov_juxtaposition", LensAuthority.INTERPRETIVE)
    )
    assert decision.scientific_status is ScientificLensStatus.REJECTED
    assert set(decision.permissions) == {
        LensPermission.QUERY_SELECTION,
        LensPermission.HYPOTHESIS_GENERATION,
    }
    assert decision.predictive_weight == 0.0
