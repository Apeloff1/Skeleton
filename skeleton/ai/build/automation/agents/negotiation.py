"""Multi-agent negotiation — proposal rounds toward consensus.

Like the one-typing contract in messaging apps, negotiation keeps a shared
document: proposers draft values, peers accept/reject/modify, and a round
closes when acceptance reaches the quorum. Complements swarm-level
consensus with structured turn-taking.

- :class:`Proposal` — value draft from one agent
- :class:`Response` — ACCEPT / REJECT / MODIFY with optional amendment
- :class:`Negotiation` — tracks rounds and resolves on quorum
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.errors import AgentError


class NegotiationError(AgentError):
    code = "AGT.NEGOTIATION"


class Decision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    MODIFY = "MODIFY"


@dataclass(frozen=True)
class Proposal:
    proposer: str
    value: Any
    round_no: int


@dataclass(frozen=True)
class Response:
    responder: str
    decision: Decision
    amendment: Any = None


class Negotiation:
    """Round-based negotiation with quorum resolution."""

    def __init__(self, *, quorum: float = 0.5) -> None:
        if not 0.0 < quorum <= 1.0:
            raise NegotiationError("quorum must be in (0, 1]")
        self.quorum = quorum
        self._participants: List[str] = []
        self._proposals: List[Proposal] = []
        self._responses: Dict[int, List[Response]] = {}
        self._resolved: Optional[Any] = None
        self._round = 0

    def join(self, agent: str) -> None:
        self._participants.append(agent)

    def propose(self, proposer: str, value: Any) -> Proposal:
        if proposer not in self._participants:
            raise NegotiationError("unknown proposer", context={"agent": proposer})
        self._round = (self._round or 0) + 1
        prop = Proposal(proposer=proposer, value=value, round_no=self._round)
        self._proposals.append(prop)
        return prop

    def respond(
        self,
        proposal: Proposal,
        responder: str,
        decision: Decision,
        amendment: Any = None,
    ) -> Optional[Any]:
        if self._resolved is not None:
            raise NegotiationError("already resolved")
        bucket = self._responses.setdefault(proposal.round_no, [])
        bucket.append(Response(responder=responder, decision=decision, amendment=amendment))
        total = len(self._participants)
        accepts = sum(1 for r in bucket if r.decision is Decision.ACCEPT)
        if accepts / max(total, 1) >= self.quorum:
            self._resolved = proposal.value
        mods = [r.amendment for r in bucket if r.decision is Decision.MODIFY]
        if mods:
            self._resolved = mods[-1]
        return self._resolved

    @property
    def resolved(self) -> Optional[Any]:
        return self._resolved

    def transcript(self) -> Dict[str, Any]:
        return {
            "rounds": self._round,
            "resolved": self._resolved is not None,
            "proposals": [
                {
                    "proposer": p.proposer,
                    "round": p.round_no,
                    "responses": [
                        {"responder": r.responder, "decision": r.decision.value}
                        for r in self._responses.get(p.round_no, [])
                    ],
                }
                for p in self._proposals
            ],
        }
