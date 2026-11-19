"""Frontier session orchestrator.

Runs an ordered sequence of candidate admissions and records them
in a durable replay log. Candidate-only. No GPU, no weight loading.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .game_frontier_dynamics import PresentationClock
from .game_frontier_p1_worldmodel import WorldModelEvidence
from .game_frontier_milestone_compose import compose_frontier, FrontierAdmission, verify_admission
from .game_frontier_replay import ReplayLog


class SessionError(ValueError):
    pass


@dataclass
class FrontierSession:
    """One candidate session: ordered admissions plus a verified replay log."""

    session_id: str
    admissions: list[FrontierAdmission] = field(default_factory=list)
    replay: ReplayLog = field(init=False)

    def __post_init__(self) -> None:
        if type(self.session_id) is not str or not self.session_id or len(self.session_id) > 80:
            raise SessionError("session_id required and bounded")
        self.replay = ReplayLog(session_id=self.session_id)

    def step(
        self,
        *,
        clock: PresentationClock,
        lod_tier: int,
        weather_digest: str,
        evidence: WorldModelEvidence,
        percepts: Sequence[str],
        goal: str,
    ) -> FrontierAdmission:
        """Admit one step and append its digest to the replay chain."""
        admission = compose_frontier(
            clock=clock,
            lod_tier=lod_tier,
            weather_digest=weather_digest,
            evidence=evidence,
            percepts=tuple(percepts),
            goal=goal,
        )
        if not verify_admission(admission):
            raise SessionError("generated admission failed integrity verification")
        self.replay.append(admission.admission_digest)
        self.admissions.append(admission)
        return admission

    def verify(self) -> bool:
        """Confirm the replay chain matches the recorded admissions."""
        if (type(self.admissions) is not list or not self.admissions
                or not isinstance(self.replay, ReplayLog)
                or self.replay.session_id != self.session_id
                or not self.replay.verify()
                or len(self.replay.entries) != len(self.admissions)):
            return False
        return all(verify_admission(admission) and admission.admission_digest == recorded
                   for admission, recorded in zip(self.admissions, self.replay.entries, strict=True))

    @property
    def head(self) -> str:
        return self.replay.head
