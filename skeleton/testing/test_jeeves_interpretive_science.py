from __future__ import annotations

import pytest

from skeleton.jeeves.agent.interpretive_science import (
    JuxtapositionTrial,
    LensOutcomeTrial,
    ScientificLensLab,
    ScientificLensStatus,
)


def _trial(
    index: int,
    *,
    lens: str = "kuleshov_context",
    probability: float,
    outcome: bool,
    domain: str,
    run: str,
    control: bool = False,
) -> LensOutcomeTrial:
    return LensOutcomeTrial(
        trial_id=f"trial-{lens}-{index}",
        lens_key=lens,
        probability=probability,
        outcome=outcome,
        domain=domain,
        independent_run=run,
        proposition="Context changes the interpretation of an otherwise ambiguous item.",
        negative_control=control,
    )


def test_well_calibrated_replicated_transfer_lens_becomes_active() -> None:
    lab = ScientificLensLab()
    for index in range(24):
        outcome = index % 2 == 0
        probability = 0.9 if outcome else 0.1
        domain = "film" if index < 12 else "literature"
        run = f"run-{index % 3}"
        lab.record(
            _trial(
                index,
                probability=probability,
                outcome=outcome,
                domain=domain,
                run=run,
            )
        )
    report = lab.report("kuleshov_context")
    assert report.status is ScientificLensStatus.ACTIVE
    assert report.trial_count == 24
    assert report.independent_runs == 3
    assert set(report.domains) == {"film", "literature"}
    assert report.brier < report.baseline_brier
    assert report.brier_gain > 0.01
    assert report.ece <= 0.15
    assert 0.0 < report.predictive_weight <= 0.60
    assert report.fingerprint


def test_small_sample_lens_stays_shadow_even_if_predictions_look_good() -> None:
    lab = ScientificLensLab()
    for index in range(6):
        outcome = index % 2 == 0
        lab.record(
            _trial(
                index,
                lens="rare_game_lens",
                probability=0.9 if outcome else 0.1,
                outcome=outcome,
                domain="game",
                run="single-run",
            )
        )
    report = lab.report("rare_game_lens")
    assert report.status is ScientificLensStatus.SHADOW
    assert report.predictive_weight <= 0.20
    assert "insufficient replicated outcome data" in report.reasons


def test_badly_miscalibrated_lens_is_rejected() -> None:
    lab = ScientificLensLab()
    for index in range(24):
        outcome = index % 2 == 0
        lab.record(
            _trial(
                index,
                lens="bad_lens",
                probability=0.01 if outcome else 0.99,
                outcome=outcome,
                domain="film" if index < 12 else "game",
                run=f"run-{index % 3}",
            )
        )
    report = lab.report("bad_lens")
    assert report.status is ScientificLensStatus.REJECTED
    assert report.predictive_weight == 0.0
    assert report.brier >= 0.40


def test_negative_controls_restrict_over_sensitive_lens() -> None:
    lab = ScientificLensLab()
    for index in range(24):
        control = index < 5
        if control:
            outcome = True
        else:
            outcome = index % 2 == 0
        probability = 0.9 if outcome else 0.1
        lab.record(
            _trial(
                index,
                lens="over_sensitive_lens",
                probability=probability,
                outcome=outcome,
                domain="film" if index < 12 else "game",
                run=f"run-{index % 3}",
                control=control,
            )
        )
    report = lab.report("over_sensitive_lens")
    assert report.status is ScientificLensStatus.RESTRICTED
    assert report.control_count == 5
    assert report.negative_control_positive_rate == pytest.approx(1.0)
    assert report.predictive_weight <= 0.15


def test_domain_calibration_serializes_without_slots_introspection() -> None:
    lab = ScientificLensLab()
    for index in range(24):
        outcome = index % 2 == 0
        lab.record(
            _trial(
                index,
                lens="serializable_lens",
                probability=0.85 if outcome else 0.15,
                outcome=outcome,
                domain="film" if index < 12 else "literature",
                run=f"run-{index % 3}",
            )
        )
    report = lab.report("serializable_lens")
    assert len(report.domain_calibration) == 2
    assert report.domain_calibration[0].as_json()["domain"] in {"film", "literature"}
    assert report.fingerprint == lab.report("serializable_lens").fingerprint


def test_juxtaposition_trials_preserve_same_target_and_refuse_causal_upgrade() -> None:
    lab = ScientificLensLab()
    for index in range(8):
        lab.record(
            JuxtapositionTrial(
                trial_id=f"juxtaposition-{index}",
                lens_key="kuleshov_context",
                target_fingerprint="same-target",
                context_a_fingerprint=f"context-a-{index}",
                context_b_fingerprint=f"context-b-{index}",
                predicted_change_probability=0.8,
                observed_interpretation_changed=index < 6,
                independent_run=f"run-{index % 3}",
                negative_control=index >= 6,
            )
        )
    effect = lab.juxtaposition_effect_report("kuleshov_context")
    assert effect["trial_count"] == 8
    assert effect["observed_change_rate"] == pytest.approx(0.75)
    assert effect["negative_control_count"] == 2
    assert effect["causal_claim_authorized"] is False
    low, high = effect["wilson_95"]
    assert 0.0 <= low <= effect["observed_change_rate"] <= high <= 1.0
