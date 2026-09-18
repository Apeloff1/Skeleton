"""Bridge semantic-topology research debt into Jeeves' epistemic agenda.

Topology learning owns the scientific lifecycle of candidate lens relations.
The epistemic research control plane owns gap discovery, probe ranking, durable
agenda state, and assurance-gated completion.

This adapter composes those systems without conflating their authority:
an ACTIVE topology bridge may stop appearing as *current topology debt*, but
that does not automatically issue a research completion certificate or resolve
an already-queued agenda item.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .epistemic_frontier import FrontierSnapshot, KnowledgeObligation
from .frontier_control_plane import FrontierCognitiveControlPlane
from .research_agenda import AgendaSnapshot
from .semantic_topology_learning import SemanticTopologyLearningLab
from .types import AgentContractError, stable_fingerprint


@dataclass(frozen=True, slots=True)
class SemanticTopologyResearchUpdate:
    obligations: tuple[KnowledgeObligation, ...]
    frontier: FrontierSnapshot
    agenda: AgendaSnapshot
    topology_agenda_ids: tuple[str, ...]
    fingerprint: str


class SemanticTopologyResearchBridge:
    """Map unresolved topology bridges into the existing research program."""

    def __init__(
        self,
        topology_learning: SemanticTopologyLearningLab,
        control_plane: FrontierCognitiveControlPlane,
    ) -> None:
        if not isinstance(topology_learning, SemanticTopologyLearningLab):
            raise TypeError(
                "topology_learning must be SemanticTopologyLearningLab"
            )
        if not isinstance(control_plane, FrontierCognitiveControlPlane):
            raise TypeError(
                "control_plane must be FrontierCognitiveControlPlane"
            )
        self.topology_learning = topology_learning
        self.control_plane = control_plane

    def refresh(
        self,
        *,
        limit: int = 24,
        minimum_candidate_score: float = 0.18,
        include_rejected: bool = False,
        dependencies: Mapping[str, Sequence[str]] | None = None,
    ) -> SemanticTopologyResearchUpdate:
        frontier = self.control_plane.map_semantic_topology_frontier(
            self.topology_learning,
            limit=limit,
            minimum_candidate_score=minimum_candidate_score,
            include_rejected=include_rejected,
            dependencies=dependencies,
        )
        obligations = frontier.obligations
        if any(
            not bool(item.metadata.get("semantic_topology"))
            for item in obligations
        ):
            raise AgentContractError(
                "topology research bridge received non-topology obligation"
            )
        agenda = self.control_plane.research_agenda.snapshot()
        agenda_ids = tuple(
            sorted(
                {
                    item.agenda_id
                    for obligation in obligations
                    for item in self.control_plane.research_agenda.items_for_obligation(
                        obligation.obligation_id
                    )
                }
            )
        )
        fingerprint = stable_fingerprint(
            {
                "topology_learning": self.topology_learning.fingerprint,
                "obligations": [
                    item.fingerprint for item in obligations
                ],
                "frontier": frontier.fingerprint,
                "agenda": agenda.fingerprint,
                "topology_agenda_ids": agenda_ids,
            }
        )
        return SemanticTopologyResearchUpdate(
            obligations=obligations,
            frontier=frontier,
            agenda=agenda,
            topology_agenda_ids=agenda_ids,
            fingerprint=fingerprint,
        )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "topology_contract": (
                    self.topology_learning.contract_fingerprint
                ),
                "frontier_policy": {
                    name: getattr(
                        self.control_plane.epistemic_frontier.policy,
                        name,
                    )
                    for name in self.control_plane.epistemic_frontier.policy.__dataclass_fields__
                },
                "agenda_policy": {
                    name: getattr(
                        self.control_plane.research_agenda.policy,
                        name,
                    )
                    for name in self.control_plane.research_agenda.policy.__dataclass_fields__
                },
                "assurance_policy": {
                    name: getattr(
                        self.control_plane.research_assurance.policy,
                        name,
                    )
                    for name in self.control_plane.research_assurance.policy.__dataclass_fields__
                },
            }
        )


__all__ = [
    "SemanticTopologyResearchBridge",
    "SemanticTopologyResearchUpdate",
]
