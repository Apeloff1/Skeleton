from __future__ import annotations

import math

from skeleton.jeeves.agent.epistemic_frontier import (
    EpistemicFrontierEngine,
    KnowledgeObligation,
)
from skeleton.jeeves.agent.frontier_control_plane import FrontierCognitiveControlPlane
from skeleton.jeeves.agent.hypothesis_tournament import (
    CompetingHypothesis,
    DiscriminatingProbe,
    HypothesisPrediction,
    HypothesisTournament,
)
from skeleton.jeeves.agent.research_agenda import (
    AgendaStatus,
    ResearchAgenda,
)
from skeleton.jeeves.agent.research_assurance import (
    ResearchEvidenceSummary,
    ResearchResolution,
)
from skeleton.jeeves.agent.research_synthesis import (
    HypothesisProposal,
    HypothesisSynthesisGate,
)
from skeleton.jeeves.agent.types import RiskTier


def _hypothesis(
    hypothesis_id: str,
    prior: float,
    *,
    cheap_yes: float,
    expensive_yes: float,
) -> CompetingHypothesis:
    return CompetingHypothesis(
        hypothesis_id=hypothesis_id,
        statement=f"Explanation {hypothesis_id}",
        prior_weight=prior,
        predictions=(
            HypothesisPrediction(
                probe_id="cheap-check",
                distribution={"yes": cheap_yes, "no": 1.0 - cheap_yes},
            ),
            HypothesisPrediction(
                probe_id="expensive-check",
                distribution={"yes": expensive_yes, "no": 1.0 - expensive_yes},
            ),
        ),
    )



def _certifiable_summary() -> ResearchEvidenceSummary:
    return ResearchEvidenceSummary(
        obligation_id="deploy-safety",
        decision_impact=0.95,
        evidence_coverage=0.95,
        freshness=0.95,
        contradiction_strength=0.05,
        independent_source_count=3,
        leading_hypothesis_id="h-a",
        leading_posterior=0.96,
        effective_hypotheses=1.10,
        unresolved_assumptions=(),
        predictive_brier_scores=(0.08, 0.10, 0.09),
        predictive_surprise_bits=(0.20, 0.30, 0.25),
        evidence_refs=("ev-1", "ev-2", "ev-probe"),
    )

def test_tournament_prefers_safe_discriminating_probe_over_expensive_low_value_probe() -> None:
    tournament = HypothesisTournament(
        (
            _hypothesis("h-a", 0.5, cheap_yes=0.95, expensive_yes=0.60),
            _hypothesis("h-b", 0.5, cheap_yes=0.05, expensive_yes=0.40),
        ),
        (
            DiscriminatingProbe(
                probe_id="cheap-check",
                question="Does the cheap observable occur?",
                outcome_support=("yes", "no"),
                expected_cost=0.05,
                risk=RiskTier.READ_ONLY,
            ),
            DiscriminatingProbe(
                probe_id="expensive-check",
                question="Does the expensive observable occur?",
                outcome_support=("yes", "no"),
                expected_cost=2.0,
                risk=RiskTier.HIGH_IMPACT,
                reversible=False,
            ),
        ),
        decision_impact=0.9,
    )

    round_ = tournament.round()

    assert round_.selected_probe_id == "cheap-check"
    cheap = next(item for item in round_.evaluations if item.probe_id == "cheap-check")
    expensive = next(item for item in round_.evaluations if item.probe_id == "expensive-check")
    assert cheap.expected_information_gain_bits > expensive.expected_information_gain_bits
    assert cheap.score > expensive.score


def test_tournament_observation_updates_posterior_and_marks_near_impossible_hypothesis() -> None:
    tournament = HypothesisTournament(
        (
            _hypothesis("h-a", 0.5, cheap_yes=0.99, expensive_yes=0.5),
            _hypothesis("h-b", 0.5, cheap_yes=0.01, expensive_yes=0.5),
        ),
        (
            DiscriminatingProbe(
                probe_id="cheap-check",
                question="Observed?",
                outcome_support=("yes", "no"),
            ),
            DiscriminatingProbe(
                probe_id="expensive-check",
                question="Secondary?",
                outcome_support=("yes", "no"),
            ),
        ),
    )

    update = tournament.observe("cheap-check", "yes", falsification_threshold=0.02)

    assert update.winner_id == "h-a"
    assert update.winner_probability > 0.98
    assert "h-b" in update.falsified_ids
    assert update.information_gain_bits > 0.0
    assert math.isclose(sum(update.posterior.values()), 1.0)


def test_tournament_is_order_invariant() -> None:
    hypotheses = (
        _hypothesis("h-a", 0.5, cheap_yes=0.9, expensive_yes=0.3),
        _hypothesis("h-b", 0.5, cheap_yes=0.1, expensive_yes=0.7),
    )
    probes = (
        DiscriminatingProbe(
            probe_id="cheap-check",
            question="Cheap?",
            outcome_support=("yes", "no"),
        ),
        DiscriminatingProbe(
            probe_id="expensive-check",
            question="Expensive?",
            outcome_support=("yes", "no"),
        ),
    )

    left = HypothesisTournament(hypotheses, probes).round()
    right = HypothesisTournament(tuple(reversed(hypotheses)), tuple(reversed(probes))).round()

    assert left.fingerprint == right.fingerprint
    assert [item.probe_id for item in left.evaluations] == [
        item.probe_id for item in right.evaluations
    ]


def _frontier() -> object:
    engine = EpistemicFrontierEngine(clock=lambda: 100.0)
    return engine.discover(
        (
            KnowledgeObligation(
                obligation_id="deploy-safety",
                question="Is deployment safe?",
                decision_impact=0.95,
                confidence=0.88,
                evidence_coverage=0.20,
                freshness=0.90,
                novelty=0.4,
                evidence_refs=("ev-1",),
            ),
        )
    )


def test_research_agenda_persists_frontier_and_resolves_on_information_gain() -> None:
    agenda = ResearchAgenda(clock=lambda: 1000.0)
    snapshot = agenda.ingest_frontier(_frontier())
    assert snapshot.queued_count >= 1

    claimed = agenda.claim_next()
    assert claimed is not None
    assert claimed.status is AgendaStatus.ACTIVE

    result = agenda.record_attempt(
        claimed.agenda_id,
        information_gain_bits=0.5,
        evidence_refs=("ev-2",),
        successful=True,
        resolution_note="Independent evidence resolved the gap.",
    )
    assert result.status is AgendaStatus.RESOLVED

    dumped = agenda.dump_state()
    restored = ResearchAgenda.from_state(dumped, clock=lambda: 1000.0)

    assert restored.snapshot().fingerprint == agenda.snapshot().fingerprint
    assert restored.item(claimed.agenda_id).evidence_refs == ("ev-1", "ev-2")


def test_recurring_gap_reopens_resolved_research_and_increases_priority() -> None:
    agenda = ResearchAgenda(clock=lambda: 1000.0)
    frontier = _frontier()
    agenda.ingest_frontier(frontier)
    claimed = agenda.claim_next()
    assert claimed is not None
    agenda.record_attempt(
        claimed.agenda_id,
        information_gain_bits=0.5,
        successful=True,
    )
    resolved = agenda.item(claimed.agenda_id)
    assert resolved.status is AgendaStatus.RESOLVED
    recurrence_before = resolved.recurrence_count

    agenda.ingest_frontier(frontier)
    reopened = agenda.item(claimed.agenda_id)

    assert reopened.status is AgendaStatus.QUEUED
    assert reopened.recurrence_count == recurrence_before + 1


def test_large_forecast_surprise_reopens_resolved_obligation() -> None:
    agenda = ResearchAgenda(clock=lambda: 1000.0)
    agenda.ingest_frontier(_frontier())
    claimed = agenda.claim_next()
    assert claimed is not None
    agenda.record_attempt(
        claimed.agenda_id,
        information_gain_bits=0.5,
        successful=True,
    )

    reopened = agenda.reopen_on_surprise(
        "deploy-safety",
        surprise_bits=4.0,
    )

    assert reopened
    assert all(item.status is AgendaStatus.QUEUED for item in reopened)
    assert agenda.item(claimed.agenda_id).maximum_surprise_bits == 4.0


def test_control_plane_feeds_tournament_learning_back_into_research_agenda() -> None:
    control = FrontierCognitiveControlPlane(clock=lambda: 1000.0)
    control.map_epistemic_frontier(
        (
            KnowledgeObligation(
                obligation_id="deploy-safety",
                question="Is deployment safe?",
                decision_impact=0.95,
                confidence=0.55,
                evidence_coverage=0.70,
                model_disagreement=0.75,
                evidence_refs=("ev-1",),
            ),
        )
    )
    agenda_item = control.research_agenda.claim_next()
    assert agenda_item is not None

    tournament = control.start_hypothesis_tournament(
        (
            _hypothesis("h-a", 0.5, cheap_yes=0.99, expensive_yes=0.5),
            _hypothesis("h-b", 0.5, cheap_yes=0.01, expensive_yes=0.5),
        ),
        (
            DiscriminatingProbe(
                probe_id="cheap-check",
                question="Observed?",
                outcome_support=("yes", "no"),
            ),
            DiscriminatingProbe(
                probe_id="expensive-check",
                question="Secondary?",
                outcome_support=("yes", "no"),
            ),
        ),
        decision_impact=0.95,
    )

    update, attempt = control.observe_hypothesis_probe(
        tournament.tournament_id,
        "cheap-check",
        "yes",
        agenda_id=agenda_item.agenda_id,
        evidence_refs=("ev-probe",),
    )

    assert update.information_gain_bits > 0.0
    assert update.surprise_bits >= 0.0
    assert attempt is not None
    assert attempt.information_gain_bits == update.information_gain_bits
    assert control.research_agenda.item(agenda_item.agenda_id).status is AgendaStatus.QUEUED

    certificate = control.certify_research_completion(
        _certifiable_summary(),
        resolution_note="Coverage, predictive record, and independent evidence passed.",
    )
    assert certificate.resolution is ResearchResolution.RESOLVED
    assert certificate.accepted is True
    assert control.research_agenda.item(agenda_item.agenda_id).status is AgendaStatus.RESOLVED


def test_surprising_precommitted_forecast_reopens_resolved_research() -> None:
    control = FrontierCognitiveControlPlane(clock=lambda: 2000.0)
    control.map_epistemic_frontier(
        (
            KnowledgeObligation(
                obligation_id="deploy-safety",
                question="Is deployment safe?",
                decision_impact=0.95,
                confidence=0.90,
                evidence_coverage=0.20,
                evidence_refs=("ev-1",),
            ),
        )
    )
    item = control.research_agenda.claim_next()
    assert item is not None
    control.research_agenda.record_attempt(
        item.agenda_id,
        information_gain_bits=0.5,
        successful=True,
    )
    assert control.research_agenda.item(item.agenda_id).status is AgendaStatus.QUEUED
    certificate = control.certify_research_completion(_certifiable_summary())
    assert certificate.accepted is True
    assert control.research_agenda.item(item.agenda_id).status is AgendaStatus.RESOLVED

    control.precommit_research_forecast(
        "deploy-safety",
        {"safe": 0.99, "unsafe": 0.01},
        forecast_id="deploy-forecast",
    )
    settlement = control.settle_research_forecast(
        "deploy-forecast",
        "unsafe",
    )

    assert settlement.surprise_bits > 6.0
    assert control.research_agenda.item(item.agenda_id).status is AgendaStatus.QUEUED



def test_completion_gate_refuses_high_confidence_without_evidence_independence() -> None:
    control = FrontierCognitiveControlPlane(clock=lambda: 3000.0)
    summary = ResearchEvidenceSummary(
        obligation_id="deploy-safety",
        decision_impact=0.95,
        evidence_coverage=0.99,
        freshness=0.99,
        contradiction_strength=0.01,
        independent_source_count=1,
        leading_hypothesis_id="h-a",
        leading_posterior=0.99,
        effective_hypotheses=1.01,
        predictive_brier_scores=(0.01, 0.01, 0.01),
        predictive_surprise_bits=(0.01, 0.01, 0.01),
    )

    certificate = control.certify_research_completion(summary)

    assert certificate.accepted is False
    assert certificate.resolution is ResearchResolution.CONTINUE
    assert any(item.code == "source-independence" for item in certificate.errors)


def test_completion_gate_only_provisional_without_prediction_history() -> None:
    control = FrontierCognitiveControlPlane(clock=lambda: 4000.0)
    summary = ResearchEvidenceSummary(
        obligation_id="low-impact-question",
        decision_impact=0.50,
        evidence_coverage=0.90,
        freshness=0.90,
        contradiction_strength=0.05,
        independent_source_count=2,
        leading_hypothesis_id="h-a",
        leading_posterior=0.90,
        effective_hypotheses=1.10,
        predictive_brier_scores=(),
        predictive_surprise_bits=(),
    )

    certificate = control.certify_research_completion(summary)

    assert certificate.accepted is False
    assert certificate.provisional is True
    assert certificate.resolution is ResearchResolution.PROVISIONAL



def _proposal(
    hypothesis_id: str,
    mechanism_family: str,
    *,
    cheap_yes: float,
    expensive_yes: float,
    is_null: bool = False,
) -> HypothesisProposal:
    return HypothesisProposal(
        hypothesis_id=hypothesis_id,
        statement=f"Structured explanation {hypothesis_id}",
        mechanism_family=mechanism_family,
        prior_weight=1.0 / 3.0,
        predictions=(
            HypothesisPrediction(
                probe_id="cheap-check",
                distribution={"yes": cheap_yes, "no": 1.0 - cheap_yes},
            ),
            HypothesisPrediction(
                probe_id="expensive-check",
                distribution={"yes": expensive_yes, "no": 1.0 - expensive_yes},
            ),
        ),
        is_null=is_null,
        assumptions=(f"assumption-{hypothesis_id}",),
        provenance=(f"proposal-{hypothesis_id}",),
    )


def test_synthesis_gate_rejects_mechanism_collapse_even_with_many_hypotheses() -> None:
    gate = HypothesisSynthesisGate()
    proposals = (
        _proposal("h-1", "same-family", cheap_yes=0.9, expensive_yes=0.5, is_null=True),
        _proposal("h-2", "same-family", cheap_yes=0.1, expensive_yes=0.5),
        _proposal("h-3", "same-family", cheap_yes=0.5, expensive_yes=0.5),
    )
    probes = (
        DiscriminatingProbe(
            probe_id="cheap-check",
            question="Cheap observation?",
            outcome_support=("yes", "no"),
        ),
        DiscriminatingProbe(
            probe_id="expensive-check",
            question="Expensive observation?",
            outcome_support=("yes", "no"),
        ),
    )

    report = gate.assess(proposals, probes)

    assert report.accepted is False
    assert any(item.code == "mechanism-diversity" for item in report.errors)


def test_strict_synthesis_builds_tournament_only_after_diverse_admission() -> None:
    control = FrontierCognitiveControlPlane(clock=lambda: 5000.0)
    proposals = (
        _proposal("h-causal", "causal", cheap_yes=0.95, expensive_yes=0.60),
        _proposal("h-confound", "confounding", cheap_yes=0.10, expensive_yes=0.75),
        _proposal("h-null", "null", cheap_yes=0.50, expensive_yes=0.50, is_null=True),
    )
    probes = (
        DiscriminatingProbe(
            probe_id="cheap-check",
            question="Cheap observation?",
            outcome_support=("yes", "no"),
            expected_cost=0.05,
            risk=RiskTier.READ_ONLY,
        ),
        DiscriminatingProbe(
            probe_id="expensive-check",
            question="Expensive observation?",
            outcome_support=("yes", "no"),
            expected_cost=0.30,
            risk=RiskTier.REVERSIBLE,
        ),
    )

    report, tournament = control.start_synthesized_tournament(
        proposals,
        probes,
        decision_impact=0.9,
    )

    assert report.accepted is True
    assert set(report.mechanism_families) == {"causal", "confounding", "null"}
    assert report.null_hypothesis_ids == ("h-null",)
    assert tournament.round().selected_probe_id in {"cheap-check", "expensive-check"}
    assert control.hypothesis_tournament(tournament.tournament_id) is tournament
