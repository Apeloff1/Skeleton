from __future__ import annotations

import math

from skeleton.jeeves.agent.epistemic_frontier import (
    EpistemicFrontierEngine,
    KnowledgeObligation,
)
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
