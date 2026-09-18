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
from .scalable_causal_ensemble import FactorizedBayesianCausalEnsemble


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
        research_stop_policy: ResearchStopPolicy | None = None,
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
        self.research_assurance = ResearchAssuranceGate(
            policy=research_stop_policy,
        )
        self._completion_certificates: dict[str, CompletionCertificate] = {}
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
        return settlement

    def dump_research_state(self) -> dict[str, Any]:
        """Return JSON-safe agenda state suitable for context/database storage."""

        return self.research_agenda.dump_state()

    def restore_research_state(self, state: Mapping[str, Any]) -> AgendaSnapshot:
        """Replace the agenda from a deterministic serialized checkpoint."""

        self.research_agenda = ResearchAgenda.from_state(
            state,
            clock=self._clock,
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
        return value
