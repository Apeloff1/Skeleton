"""Production composition of Jeeves' robust cognitive control plane.

``CognitiveControlPlane`` contains the policy/learning architecture. This module
binds it to sparse Bayesian causal inference and adds a research layer that can
map unknowns, preserve them across runs, and choose observations that separate
competing hypotheses.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence
import time

from .causal_inference import InferencePolicy
from .cognitive_control_plane import CognitiveControlPlane, ControlPlanePolicy
from .epistemic_frontier import (
    EpistemicFrontierEngine,
    EpistemicFrontierPolicy,
    ForecastContract,
    ForecastSettlement,
    FrontierSnapshot,
    KnowledgeObligation,
)
from .hypothesis_tournament import (
    CompetingHypothesis,
    DiscriminatingProbe,
    HypothesisTournament,
    TournamentPolicy,
    TournamentUpdate,
)
from .live_supervisor import LiveSupervisor
from .research_agenda import (
    AgendaSnapshot,
    AttemptResult,
    ResearchAgenda,
    ResearchAgendaPolicy,
)
from .research_assurance import (
    CompletionCertificate,
    ResearchAssuranceGate,
    ResearchEvidenceSummary,
    ResearchStopPolicy,
)
from .research_synthesis import (
    HypothesisProposal,
    HypothesisSynthesisGate,
    HypothesisSynthesisPolicy,
    SynthesisReport,
)
from .scalable_causal_ensemble import FactorizedBayesianCausalEnsemble
from .semantic_topology_learning import SemanticTopologyLearningLab
from .types import AgentContractError, json_safe, stable_fingerprint
from .unknown_unknowns import (
    SurpriseScoutPolicy,
    UnknownUnknownScout,
)


class FrontierCognitiveControlPlane(CognitiveControlPlane):
    """Cognitive control plane with sparse causal inference and active research."""

    def __init__(
        self,
        baseline: LiveSupervisor | None = None,
        *,
        policy: ControlPlanePolicy | None = None,
        inference_policy: InferencePolicy | None = None,
        epistemic_policy: EpistemicFrontierPolicy | None = None,
        agenda_policy: ResearchAgendaPolicy | None = None,
        tournament_policy: TournamentPolicy | None = None,
        synthesis_policy: HypothesisSynthesisPolicy | None = None,
        research_stop_policy: ResearchStopPolicy | None = None,
        surprise_scout_policy: SurpriseScoutPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(baseline, policy=policy, clock=clock)
        self.inference_policy = inference_policy or InferencePolicy(
            maximum_sparse_entries=300_000,
            maximum_dense_capacity=8_000_000,
            ancestor_pruning=True,
        )
        # The base constructor creates an empty ensemble. Replacing it before
        # any learning cycle is lossless and keeps the control-plane logic
        # independent from its exact inference backend.
        self._ensemble = FactorizedBayesianCausalEnsemble(
            preferences=self._preferences,
            policy=self.policy.ensemble_policy,
            clock=clock,
            history_limit=self.policy.history_limit,
            inference_policy=self.inference_policy,
        )
        self.epistemic_frontier = EpistemicFrontierEngine(
            policy=epistemic_policy,
            clock=clock,
        )
        effective_agenda_policy = agenda_policy or ResearchAgendaPolicy(
            require_assurance_for_resolution=True,
        )
        self.research_agenda = ResearchAgenda(
            policy=effective_agenda_policy,
            clock=clock,
        )
        self.tournament_policy = tournament_policy or TournamentPolicy()
        self.hypothesis_synthesis = HypothesisSynthesisGate(
            policy=synthesis_policy,
        )
        self.research_assurance = ResearchAssuranceGate(
            policy=research_stop_policy,
        )
        self.unknown_unknown_scout = UnknownUnknownScout(
            policy=surprise_scout_policy,
            clock=clock,
        )
        self._completion_certificates: dict[str, CompletionCertificate] = {}
        self._forecast_settlements: list[ForecastSettlement] = []
        self._restored_frontier_audit: Mapping[str, Any] | None = None
        self._last_frontier_snapshot: FrontierSnapshot | None = None
        self._last_agenda_snapshot: AgendaSnapshot | None = None
        self._tournaments: dict[str, HypothesisTournament] = {}

    def map_epistemic_frontier(
        self,
        obligations: Sequence[KnowledgeObligation],
        *,
        dependencies: Mapping[str, Sequence[str]] | None = None,
    ) -> FrontierSnapshot:
        """Discover gaps and compound them into the durable research agenda.

        Model confidence alone cannot mark an obligation resolved: weak evidence
        coverage can create a blind-spot gap even when confidence is high.
        Repeated gaps are not discarded; ingestion increases recurrence and can
        reopen previously resolved agenda items.
        """

        snapshot = self.epistemic_frontier.discover(obligations)
        self._last_frontier_snapshot = snapshot
        self._last_agenda_snapshot = self.research_agenda.ingest_frontier(
            snapshot,
            dependencies=dependencies,
        )
        return snapshot

    def map_semantic_topology_frontier(
        self,
        topology_learning: SemanticTopologyLearningLab,
        *,
        limit: int = 24,
        minimum_candidate_score: float = 0.18,
        include_rejected: bool = False,
        dependencies: Mapping[str, Sequence[str]] | None = None,
    ) -> FrontierSnapshot:
        """Promote unresolved semantic topology questions into research debt.

        The bridge candidates remain non-executable unless the topology-learning
        lab independently promotes them. This method only feeds their unresolved
        knowledge obligations into the existing epistemic frontier and agenda.
        """

        if not isinstance(
            topology_learning,
            SemanticTopologyLearningLab,
        ):
            raise TypeError(
                "topology_learning must be SemanticTopologyLearningLab"
            )
        obligations = topology_learning.research_obligations(
            limit=limit,
            minimum_candidate_score=minimum_candidate_score,
            include_rejected=include_rejected,
        )
        return self.map_epistemic_frontier(
            obligations,
            dependencies=dependencies,
        )

    def start_hypothesis_tournament(
        self,
        hypotheses: Sequence[CompetingHypothesis],
        probes: Sequence[DiscriminatingProbe],
        *,
        decision_impact: float = 1.0,
    ) -> HypothesisTournament:
        """Create a predictive tournament whose evidence updates are host-side."""

        tournament = HypothesisTournament(
            hypotheses,
            probes,
            policy=self.tournament_policy,
            decision_impact=decision_impact,
        )
        self._tournaments[tournament.tournament_id] = tournament
        return tournament

    def start_synthesized_tournament(
        self,
        proposals: Sequence[HypothesisProposal],
        probes: Sequence[DiscriminatingProbe],
        *,
        decision_impact: float = 1.0,
    ) -> tuple[SynthesisReport, HypothesisTournament]:
        """Strict tournament admission with anti-collapse synthesis checks."""

        report, tournament = self.hypothesis_synthesis.build_tournament(
            proposals,
            probes,
            tournament_policy=self.tournament_policy,
            decision_impact=decision_impact,
        )
        self._tournaments[tournament.tournament_id] = tournament
        return report, tournament

    def hypothesis_tournament(self, tournament_id: str) -> HypothesisTournament:
        try:
            return self._tournaments[tournament_id]
        except KeyError as exc:
            raise KeyError(f"unknown hypothesis tournament {tournament_id}") from exc

    def observe_hypothesis_probe(
        self,
        tournament_id: str,
        probe_id: str,
        observed_outcome: str,
        *,
        agenda_id: str | None = None,
        evidence_refs: Sequence[str] = (),
        successful: bool = True,
    ) -> tuple[TournamentUpdate, AttemptResult | None]:
        """Update a tournament and feed measured learning back into the agenda."""

        update = self.hypothesis_tournament(tournament_id).observe(
            probe_id,
            observed_outcome,
        )
        attempt: AttemptResult | None = None
        if agenda_id is not None:
            attempt = self.research_agenda.record_attempt(
                agenda_id,
                information_gain_bits=update.information_gain_bits,
                surprise_bits=update.surprise_bits,
                evidence_refs=evidence_refs,
                successful=successful,
            )
            self._last_agenda_snapshot = self.research_agenda.snapshot()
        return update, attempt

    def certify_research_completion(
        self,
        summary: ResearchEvidenceSummary,
        *,
        resolution_note: str = "",
    ) -> CompletionCertificate:
        """Apply the fail-closed research stop gate to one obligation."""

        certificate = self.research_assurance.evaluate(summary)
        self._completion_certificates[certificate.certificate_id] = certificate
        if certificate.accepted:
            for item in self.research_agenda.items_for_obligation(
                certificate.obligation_id
            ):
                self.research_agenda.apply_completion_certificate(
                    item.agenda_id,
                    certificate_id=certificate.certificate_id,
                    accepted=True,
                    resolution_note=resolution_note,
                )
            self._last_agenda_snapshot = self.research_agenda.snapshot()
        return certificate

    def completion_certificate(
        self,
        certificate_id: str,
    ) -> CompletionCertificate:
        try:
            return self._completion_certificates[certificate_id]
        except KeyError as exc:
            raise KeyError(
                f"unknown research completion certificate {certificate_id}"
            ) from exc

    def precommit_research_forecast(
        self,
        obligation_id: str,
        distribution: Mapping[str, float],
        *,
        forecast_id: str | None = None,
    ) -> ForecastContract:
        """Seal a prediction before the outcome is available."""

        return self.epistemic_frontier.precommit_forecast(
            obligation_id,
            distribution,
            forecast_id=forecast_id,
        )

    def settle_research_forecast(
        self,
        forecast_id: str,
        observed_outcome: str,
    ) -> ForecastSettlement:
        """Score a sealed forecast and reopen agenda work after large surprise."""

        contract = self.epistemic_frontier.forecast(forecast_id)
        settlement = self.epistemic_frontier.settle_forecast(
            forecast_id,
            observed_outcome,
        )
        reopened = self.research_agenda.reopen_on_surprise(
            contract.obligation_id,
            surprise_bits=settlement.surprise_bits,
        )
        if reopened:
            self._last_agenda_snapshot = self.research_agenda.snapshot()
        self._forecast_settlements.append(settlement)
        decision_impact = 0.50
        if self._last_frontier_snapshot is not None:
            for obligation in self._last_frontier_snapshot.obligations:
                if obligation.obligation_id == contract.obligation_id:
                    decision_impact = obligation.decision_impact
                    break
        self.unknown_unknown_scout.observe(
            channel=contract.obligation_id,
            context_key=contract.forecast_id,
            expected_probability=settlement.probability_assigned,
            decision_impact=decision_impact,
            evidence_ref=contract.forecast_id,
            outcome=settlement.observed_outcome,
            explanation_coverage=0.0,
            metadata={
                "settlement_fingerprint": settlement.settlement_fingerprint,
                "source": "precommitted-forecast",
            },
        )
        return settlement

    def surface_unknown_unknowns(self) -> tuple[KnowledgeObligation, ...]:
        """Promote recurrent predictive residuals into new research questions."""

        return self.unknown_unknown_scout.promote_all()

    def map_unknown_unknowns_into_frontier(self) -> FrontierSnapshot:
        """Promote anomaly clusters and immediately feed them into the frontier."""

        obligations = self.surface_unknown_unknowns()
        return self.map_epistemic_frontier(obligations)

    def unknown_unknown_summary(self) -> dict[str, Any]:
        snapshot = self.unknown_unknown_scout.snapshot()
        return {
            "engine": "unknown-unknown-scout",
            "observations": len(snapshot.observations),
            "candidates": len(snapshot.candidates),
            "promoted_channels": len(snapshot.promoted_channels),
            "snapshot_fingerprint": snapshot.fingerprint,
        }

    def dump_research_state(self) -> dict[str, Any]:
        """Checkpoint the full epistemic research program with an integrity hash."""

        agenda_state = self.research_agenda.dump_state()
        forecast_state = self.epistemic_frontier.dump_forecasts()
        scout_state = self.unknown_unknown_scout.dump_state()
        tournaments = [
            item.dump_state()
            for item in sorted(
                self._tournaments.values(),
                key=lambda value: value.tournament_id,
            )
        ]
        certificates = [
            item.as_json()
            for item in sorted(
                self._completion_certificates.values(),
                key=lambda value: value.certificate_id,
            )
        ]
        settlements = [
            {
                "forecast_id": item.forecast_id,
                "observed_outcome": item.observed_outcome,
                "probability_assigned": item.probability_assigned,
                "brier_score": item.brier_score,
                "surprise_bits": item.surprise_bits,
                "settlement_fingerprint": item.settlement_fingerprint,
            }
            for item in self._forecast_settlements
        ]
        frontier_audit = (
            self._last_frontier_snapshot.as_json()
            if self._last_frontier_snapshot is not None
            else self._restored_frontier_audit
        )
        component_fingerprint = stable_fingerprint(
            {
                "agenda": agenda_state["fingerprint"],
                "forecasts": forecast_state["fingerprint"],
                "unknown_unknown_scout": scout_state["fingerprint"],
                "tournaments": [
                    stable_fingerprint(item) for item in tournaments
                ],
                "certificates": [
                    item["fingerprint"] for item in certificates
                ],
                "settlements": [
                    item["settlement_fingerprint"] for item in settlements
                ],
                "frontier": (
                    frontier_audit.get("fingerprint")
                    if isinstance(frontier_audit, Mapping)
                    else None
                ),
            }
        )
        return {
            "version": 2,
            "agenda": agenda_state,
            "forecasts": forecast_state,
            "unknown_unknown_scout": scout_state,
            "tournaments": tournaments,
            "certificates": certificates,
            "settlements": settlements,
            "frontier_audit": frontier_audit,
            "fingerprint": component_fingerprint,
        }

    def restore_research_state(self, state: Mapping[str, Any]) -> AgendaSnapshot:
        """Restore a research program and verify deterministic replay integrity."""

        payload = json_safe(dict(state))
        # Backward-compatible agenda-only checkpoints from the first research
        # agenda implementation.
        if payload.get("version") == 1 and "items" in payload:
            self.research_agenda = ResearchAgenda.from_state(
                payload,
                clock=self._clock,
            )
            self._tournaments = {}
            self._completion_certificates = {}
            self._forecast_settlements = []
            self.unknown_unknown_scout = UnknownUnknownScout(clock=self._clock)
            self._restored_frontier_audit = None
            self._last_frontier_snapshot = None
            self._last_agenda_snapshot = self.research_agenda.snapshot()
            return self._last_agenda_snapshot
        if payload.get("version") != 2:
            raise AgentContractError("unsupported research program state version")

        self.research_agenda = ResearchAgenda.from_state(
            dict(payload["agenda"]),
            clock=self._clock,
        )
        self.epistemic_frontier.restore_forecasts(
            dict(payload["forecasts"]),
            replace_existing=True,
        )
        self.unknown_unknown_scout = UnknownUnknownScout.from_state(
            dict(payload["unknown_unknown_scout"]),
            clock=self._clock,
        )

        tournaments: dict[str, HypothesisTournament] = {}
        for value in payload.get("tournaments", ()):
            tournament = HypothesisTournament.from_state(dict(value))
            if tournament.tournament_id in tournaments:
                raise AgentContractError(
                    "duplicate tournament_id in research checkpoint"
                )
            tournaments[tournament.tournament_id] = tournament
        self._tournaments = tournaments

        certificates: dict[str, CompletionCertificate] = {}
        for value in payload.get("certificates", ()):
            certificate = CompletionCertificate.from_json(dict(value))
            if certificate.certificate_id in certificates:
                raise AgentContractError(
                    "duplicate completion certificate in research checkpoint"
                )
            certificates[certificate.certificate_id] = certificate
        self._completion_certificates = certificates

        settlements: list[ForecastSettlement] = []
        for value in payload.get("settlements", ()):
            settlement = ForecastSettlement(
                forecast_id=value["forecast_id"],
                observed_outcome=value["observed_outcome"],
                probability_assigned=value["probability_assigned"],
                brier_score=value["brier_score"],
                surprise_bits=value["surprise_bits"],
                settlement_fingerprint=value["settlement_fingerprint"],
            )
            expected = stable_fingerprint(
                {
                    "commitment": self.epistemic_frontier.forecast(
                        settlement.forecast_id
                    ).commitment,
                    "observed": settlement.observed_outcome,
                    "assigned": settlement.probability_assigned,
                    "brier": settlement.brier_score,
                    "surprise_bits": settlement.surprise_bits,
                }
            )
            if expected != settlement.settlement_fingerprint:
                raise AgentContractError(
                    "forecast settlement fingerprint mismatch during restore"
                )
            settlements.append(settlement)
        self._forecast_settlements = settlements
        self._last_frontier_snapshot = None
        self._restored_frontier_audit = payload.get("frontier_audit")

        rebuilt = self.dump_research_state()
        if rebuilt["fingerprint"] != payload.get("fingerprint"):
            raise AgentContractError(
                "research program fingerprint mismatch after deterministic replay"
            )
        self._last_agenda_snapshot = self.research_agenda.snapshot()
        return self._last_agenda_snapshot

    def epistemic_summary(
        self,
        snapshot: FrontierSnapshot | None = None,
    ) -> dict[str, Any]:
        current = snapshot or self._last_frontier_snapshot
        policy = self.epistemic_frontier.policy
        value: dict[str, Any] = {
            "engine": "epistemic-frontier",
            "minimum_signal": policy.minimum_signal,
            "blind_spot_minimum_impact": policy.blind_spot_minimum_impact,
            "blind_spot_maximum_coverage": policy.blind_spot_maximum_coverage,
            "blind_spot_minimum_confidence": policy.blind_spot_minimum_confidence,
            "maximum_probes": policy.maximum_probes,
        }
        if current is not None:
            value.update(
                {
                    "obligations": len(current.obligations),
                    "open_gaps": len(current.gaps),
                    "ranked_probes": len(current.probes),
                    "frontier_pressure": current.frontier_pressure,
                    "unresolved_decision_value": current.unresolved_decision_value,
                    "snapshot_fingerprint": current.fingerprint,
                }
            )
        return value

    def agenda_summary(
        self,
        snapshot: AgendaSnapshot | None = None,
    ) -> dict[str, Any]:
        current = snapshot or self._last_agenda_snapshot
        if current is None:
            current = self.research_agenda.snapshot()
        return {
            "engine": "persistent-research-agenda",
            "queued": current.queued_count,
            "active": current.active_count,
            "blocked": current.blocked_count,
            "resolved": current.resolved_count,
            "deferred": current.deferred_count,
            "unresolved_priority": current.unresolved_priority,
            "snapshot_fingerprint": current.fingerprint,
            "assurance_required": self.research_agenda.policy.require_assurance_for_resolution,
            "completion_certificates": len(self._completion_certificates),
        }

    def tournament_summary(self) -> dict[str, Any]:
        active = tuple(sorted(self._tournaments.values(), key=lambda item: item.tournament_id))
        return {
            "engine": "hypothesis-tournament",
            "active_tournaments": len(active),
            "strict_synthesis": {
                "minimum_hypotheses": self.hypothesis_synthesis.policy.minimum_hypotheses,
                "minimum_mechanism_families": self.hypothesis_synthesis.policy.minimum_mechanism_families,
                "require_null_hypothesis": self.hypothesis_synthesis.policy.require_null_hypothesis,
                "minimum_pairwise_separation": self.hypothesis_synthesis.policy.minimum_pairwise_separation,
            },
            "tournaments": [
                {
                    "tournament_id": item.tournament_id,
                    "posterior_entropy_bits": item.posterior_entropy_bits,
                    "effective_hypotheses": item.effective_hypotheses,
                    "observations": len(item.history()),
                }
                for item in active
            ],
        }

    def inference_summary(self) -> dict[str, Any]:
        return {
            "backend": "sparse-variable-elimination",
            "heuristic": self.inference_policy.heuristic.value,
            "maximum_sparse_entries": self.inference_policy.maximum_sparse_entries,
            "maximum_dense_capacity": self.inference_policy.maximum_dense_capacity,
            "ancestor_pruning": self.inference_policy.ancestor_pruning,
            "ensemble_models": len(self._ensemble.hypotheses()),
        }

    def summary(self) -> dict[str, Any]:
        value = super().summary()
        value["inference"] = self.inference_summary()
        value["epistemic_frontier"] = self.epistemic_summary()
        value["research_agenda"] = self.agenda_summary()
        value["hypothesis_tournaments"] = self.tournament_summary()
        value["unknown_unknowns"] = self.unknown_unknown_summary()
        return value
