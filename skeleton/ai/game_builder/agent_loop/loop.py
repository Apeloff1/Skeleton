"""Observe -> reason -> act -> verify loop. Agents only see snapshots and
return proposals; the loop owns the single write path into state."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from .detectors import Outcome, WinLossDetector
from .state import AuthoritativeGameState, GameSnapshot, Mutation, StateMutationError


class Agent(Protocol):
    def reason(self, observation: Mapping[str, Any]) -> Any: ...
    def act(self, plan: Any, snapshot: GameSnapshot) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class LoopStep:
    turn: int
    version_before: int
    version_after: int
    plan: Any
    proposal: Mapping[str, Any]
    accepted: bool
    verified: bool
    outcome: Outcome
    note: str = ""


Observer = Callable[[GameSnapshot], Mapping[str, Any]]
Verifier = Callable[[GameSnapshot, GameSnapshot, Mapping[str, Any]], bool]


def _default_observe(snap: GameSnapshot) -> Mapping[str, Any]:
    return snap.data


def _default_verify(before: GameSnapshot, after: GameSnapshot, proposal: Mapping[str, Any]) -> bool:
    return after.version == before.version + 1 and all(after.get(k) == v or isinstance(v, (list, dict))
                                                        for k, v in proposal.items())


@dataclass
class GameLoop:
    state: AuthoritativeGameState
    agent: Agent
    detector: WinLossDetector
    observe: Observer = _default_observe
    verify: Verifier = _default_verify
    turn_key: str = "turn"
    max_rejections: int = 3
    steps: list[LoopStep] = field(default_factory=list)

    def step(self) -> LoopStep:
        before = self.state.snapshot()
        outcome, why = self.detector.evaluate(before)
        turn = int(before.get(self.turn_key, 0))
        if outcome is not Outcome.ONGOING:
            rec = LoopStep(turn, before.version, before.version, None, {}, False, True, outcome, why)
            self.steps.append(rec)
            return rec
        plan = self.agent.reason(self.observe(before))
        proposal = dict(self.agent.act(plan, before) or {})
        proposal.setdefault(self.turn_key, turn + 1)
        try:
            after = self.state.apply(Mutation(before.version, proposal, "agent", str(plan)[:120]))
        except StateMutationError as exc:
            rec = LoopStep(turn, before.version, before.version, plan, proposal, False, False,
                           Outcome.ONGOING, f"rejected: {exc}")
            self.steps.append(rec)
            return rec
        verified = bool(self.verify(before, after, proposal))
        outcome, why = self.detector.evaluate(after)
        rec = LoopStep(turn, before.version, after.version, plan, proposal, True, verified, outcome,
                       why if verified else "verify failed")
        self.steps.append(rec)
        return rec

    def run(self, max_steps: int = 1000) -> Outcome:
        rejections = 0
        for _ in range(max_steps):
            rec = self.step()
            if rec.outcome is not Outcome.ONGOING:
                return rec.outcome
            if not rec.accepted or not rec.verified:
                rejections += 1
                if rejections >= self.max_rejections:
                    return Outcome.LOSS
            else:
                rejections = 0
        return Outcome.DRAW
