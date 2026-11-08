"""Observe -> reason -> act -> verify loop. Agents only see snapshots and
return proposals; the loop owns the single write path into state."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from .detectors import Outcome, WinLossDetector
from .state import AuthoritativeGameState, GameSnapshot, Mutation, StateMutationError, _freeze


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
    return (after.version == before.version + 1
            and all(k in after.data and after.get(k) == _freeze(v)
                    for k, v in proposal.items()))


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
    held: bool = False

    def __post_init__(self) -> None:
        if (type(self.max_rejections) is not int or not 1 <= self.max_rejections <= 1000
                or type(self.turn_key) is not str or not self.turn_key):
            raise StateMutationError("invalid finite game loop policy")

    def step(self) -> LoopStep:
        if self.held:
            before = self.state.snapshot()
            rec = LoopStep(before.get(self.turn_key, 0), before.version,
                           before.version, None, {}, False, False,
                           Outcome.LOSS, "game-agent-assurance-held")
            return rec
        if len(self.steps) >= 10000:
            self.held = True
            raise StateMutationError("bounded game loop history exhausted")
        before = self.state.snapshot()
        outcome, why = self.detector.evaluate(before)
        turn = before.get(self.turn_key, 0)
        if type(turn) is not int or turn < 0:
            self.held = True
            return LoopStep(0, before.version, before.version, None, {},
                            False, False, Outcome.LOSS, "invalid-turn-identity")
        if outcome is not Outcome.ONGOING:
            rec = LoopStep(turn, before.version, before.version, None, {}, False, True, outcome, why)
            self.steps.append(rec)
            return rec
        try:
            observation = self.observe(before)
            if not isinstance(observation, Mapping):
                raise StateMutationError("invalid observation")
            plan = self.agent.reason(observation)
            raw = self.agent.act(plan, before)
            if not isinstance(raw, Mapping):
                raise StateMutationError("invalid agent proposal")
            proposal = dict(raw)
            if self.turn_key in proposal and proposal[self.turn_key] != turn + 1:
                raise StateMutationError("agent attempted to forge turn advancement")
            proposal[self.turn_key] = turn + 1
            after = self.state.apply(Mutation(before.version, proposal, "agent", "bounded-agent-proposal"))
        except Exception:
            rec = LoopStep(turn, before.version, before.version, None, {}, False, False,
                           Outcome.ONGOING, "agent-proposal-rejected")
            self.steps.append(rec)
            return rec
        try:
            verified = self.verify(before, after, proposal) is True
        except Exception:
            verified = False
        if not verified:
            # The write was committed: stop further progress, never fabricate rollback.
            self.held = True
            rec = LoopStep(turn, before.version, after.version, None, {},
                           True, False, Outcome.LOSS, "postcommit-verification-held")
            self.steps.append(rec)
            return rec
        outcome, why = self.detector.evaluate(after)
        rec = LoopStep(turn, before.version, after.version, None,
                       {"changed_keys": tuple(sorted(proposal))}, True, True,
                       outcome, why)
        self.steps.append(rec)
        return rec

    def run(self, max_steps: int = 1000) -> Outcome:
        if type(max_steps) is not int or not 1 <= max_steps <= 10000:
            raise StateMutationError("invalid bounded game-loop duration")
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
